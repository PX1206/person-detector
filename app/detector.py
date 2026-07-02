import logging
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from app.config import Settings
from app.schemas import PersonBox, PersonDetectResult

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0


class PersonDetector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: YOLO | None = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def load(self) -> None:
        torch.set_num_threads(self.settings.torch_threads)

        model_path = self._resolve_model_path()
        logger.info(
            "加载模型 %s, imgsz=%s, conf=%s, torch_threads=%s",
            model_path,
            self.settings.imgsz,
            self.settings.conf_threshold,
            self.settings.torch_threads,
        )

        self._model = YOLO(str(model_path))
        self._warmup()
        self._ready = True
        logger.info("模型加载完成")

    def _resolve_model_path(self) -> str:
        self.settings.model_dir.mkdir(parents=True, exist_ok=True)
        local_path = self.settings.model_path
        if local_path.exists():
            return str(local_path)
        raise FileNotFoundError(
            f"模型文件不存在: {local_path}，请将 {self.settings.model_name} 放到宿主机 models/ 目录后重启"
        )

    def _warmup(self) -> None:
        assert self._model is not None
        dummy = np.zeros((self.settings.imgsz, self.settings.imgsz, 3), dtype=np.uint8)
        self._model.predict(
            source=dummy,
            classes=[PERSON_CLASS_ID],
            conf=self.settings.conf_threshold,
            imgsz=self.settings.imgsz,
            verbose=False,
        )

    def detect(self, image: np.ndarray) -> PersonDetectResult:
        if not self._ready or self._model is None:
            raise RuntimeError("模型尚未加载")

        start = time.perf_counter()
        height, width = image.shape[:2]
        image_area = float(width * height)

        results = self._model.predict(
            source=image,
            classes=[PERSON_CLASS_ID],
            conf=self.settings.conf_threshold,
            imgsz=self.settings.imgsz,
            verbose=False,
        )

        boxes: list[PersonBox] = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                confidence = float(box.conf[0])
                box_width = max(0.0, x2 - x1)
                box_height = max(0.0, y2 - y1)
                area_ratio = (box_width * box_height) / image_area if image_area else 0.0
                if area_ratio < self.settings.min_box_area_ratio:
                    continue
                boxes.append(
                    PersonBox(
                        confidence=round(confidence, 4),
                        x1=round(x1, 2),
                        y1=round(y1, 2),
                        x2=round(x2, 2),
                        y2=round(y2, 2),
                        area_ratio=round(area_ratio, 6),
                    )
                )

        boxes.sort(key=lambda item: item.confidence, reverse=True)
        latency_ms = int((time.perf_counter() - start) * 1000)

        return PersonDetectResult(
            has_person=len(boxes) > 0,
            person_count=1 if boxes else 0,
            max_confidence=boxes[0].confidence if boxes else 0.0,
            boxes=boxes,
            latency_ms=latency_ms,
            image_width=width,
            image_height=height,
        )

    @staticmethod
    def decode_upload(data: bytes) -> np.ndarray:
        buffer = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("无法解码上传图片")
        return image
