import logging
import socket
import time
from contextlib import contextmanager

import cv2
import httpx
import numpy as np

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None
_original_getaddrinfo = socket.getaddrinfo


@contextmanager
def _force_ipv4_dns():
    """仅解析 IPv4，保留 URL 域名供 HTTPS SNI/证书校验（避免 IP 直连证书报错）。"""

    def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
        try:
            return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        except OSError:
            return _original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = getaddrinfo_ipv4
    try:
        yield
    finally:
        socket.getaddrinfo = _original_getaddrinfo


def init_http_client(timeout: float, trust_env: bool) -> None:
    global _http_client
    if _http_client is not None:
        return
    _http_client = httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        trust_env=trust_env,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def decode_image_bytes(data: bytes) -> np.ndarray:
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("无法解码图片，请确认文件为有效的 JPEG/PNG 格式")
    return image


async def fetch_image_from_url(
    url: str,
    timeout: float,
    *,
    prefer_ipv4: bool = True,
) -> np.ndarray:
    if _http_client is None:
        init_http_client(timeout, trust_env=False)

    start = time.perf_counter()
    if prefer_ipv4:
        with _force_ipv4_dns():
            response = await _http_client.get(url, timeout=timeout)
    else:
        response = await _http_client.get(url, timeout=timeout)
    fetch_ms = int((time.perf_counter() - start) * 1000)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if content_type and not content_type.startswith("image/"):
        logger.warning("URL 返回非 image 类型: %s content-type=%s", url, content_type)

    logger.info("拉图完成 fetch_ms=%s bytes=%s url=%s", fetch_ms, len(response.content), url)
    return decode_image_bytes(response.content)
