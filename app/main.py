import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.verdict import has_actionable_person
from app.detector import PersonDetector
from app.image_loader import close_http_client, decode_image_bytes, fetch_image_from_url, init_http_client
from app.schemas import (
    PersonDetectBatchRequest,
    PersonDetectBatchResult,
    PersonDetectByUrlRequest,
    PersonDetectResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
detector = PersonDetector(settings)
inference_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_http_client(settings.image_fetch_timeout, trust_env=False)
    detector.load()
    yield
    await close_http_client()


app = FastAPI(
    title="Person Detector",
    description="报警图片人形检测服务（YOLO11s）",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str | bool]:
    if not detector.ready:
        raise HTTPException(status_code=503, detail="模型尚未就绪")
    return {"status": "ready", "model": settings.model_name}


@app.post("/api/v1/detect/person", response_model=PersonDetectResult)
async def detect_person_by_url(body: PersonDetectByUrlRequest) -> PersonDetectResult:
    try:
        image = await fetch_image_from_url(
            str(body.image_url),
            settings.image_fetch_timeout,
            prefer_ipv4=settings.image_fetch_prefer_ipv4,
        )
    except Exception as exc:
        logger.exception("拉取图片失败 alarm_id=%s url=%s", body.alarm_id, body.image_url)
        raise HTTPException(status_code=400, detail=f"拉取图片失败: {exc}") from exc

    async with inference_lock:
        try:
            result = await asyncio.to_thread(detector.detect, image)
        except Exception as exc:
            logger.exception("推理失败 alarm_id=%s", body.alarm_id)
            raise HTTPException(status_code=500, detail=f"推理失败: {exc}") from exc

    logger.info(
        "检测完成 alarm_id=%s has_person=%s count=%s latency_ms=%s",
        body.alarm_id,
        result.has_person,
        result.person_count,
        result.latency_ms,
    )
    return result


@app.post("/api/v1/detect/person/upload", response_model=PersonDetectResult)
async def detect_person_by_upload(
    file: UploadFile = File(...),
    alarm_id: str | None = None,
) -> PersonDetectResult:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    try:
        image = decode_image_bytes(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with inference_lock:
        try:
            result = await asyncio.to_thread(detector.detect, image)
        except Exception as exc:
            logger.exception("推理失败 alarm_id=%s", alarm_id)
            raise HTTPException(status_code=500, detail=f"推理失败: {exc}") from exc

    logger.info(
        "上传检测完成 alarm_id=%s has_person=%s count=%s latency_ms=%s",
        alarm_id,
        result.has_person,
        result.person_count,
        result.latency_ms,
    )
    return result


@app.post("/api/v1/detect/person/batch", response_model=PersonDetectBatchResult)
async def detect_person_batch(body: PersonDetectBatchRequest) -> PersonDetectBatchResult:
    import time

    start = time.perf_counter()
    results: list[PersonDetectResult] = []

    for index, image_url in enumerate(body.image_urls):
        try:
            image = await fetch_image_from_url(
                str(image_url),
                settings.image_fetch_timeout,
                prefer_ipv4=settings.image_fetch_prefer_ipv4,
            )
        except Exception as exc:
            logger.exception("批量拉取图片失败 alarm_id=%s url=%s", body.alarm_id, image_url)
            raise HTTPException(status_code=400, detail=f"拉取图片失败: {exc}") from exc

        async with inference_lock:
            try:
                result = await asyncio.to_thread(detector.detect, image)
            except Exception as exc:
                logger.exception("批量推理失败 alarm_id=%s", body.alarm_id)
                raise HTTPException(status_code=500, detail=f"推理失败: {exc}") from exc
        results.append(result)

        # 有人(≥60%)或疑似(≥30%)则不再识别后续抓拍；仅误报才继续下一张
        if has_actionable_person(result.person_count, result.max_confidence):
            skipped = len(body.image_urls) - index - 1
            if skipped > 0:
                logger.info(
                    "已判定有人/疑似 alarm_id=%s index=%s person_count=%s max_confidence=%s skipped=%s",
                    body.alarm_id,
                    index,
                    result.person_count,
                    result.max_confidence,
                    skipped,
                )
            break

    has_person = any(item.has_person for item in results) if body.require_any else all(
        item.has_person for item in results
    )
    max_confidence = max((item.max_confidence for item in results), default=0.0)
    person_count = 1 if has_person else 0
    latency_ms = int((time.perf_counter() - start) * 1000)

    logger.info(
        "批量检测完成 alarm_id=%s images=%s/%s has_person=%s person_count=%s latency_ms=%s",
        body.alarm_id,
        len(results),
        len(body.image_urls),
        has_person,
        person_count,
        latency_ms,
    )

    return PersonDetectBatchResult(
        has_person=has_person,
        person_count=person_count,
        max_confidence=max_confidence,
        latency_ms=latency_ms,
        results=results,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception):
    logger.exception("未处理异常")
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=1,
        reload=False,
    )


if __name__ == "__main__":
    run()
