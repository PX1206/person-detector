FROM python:3.10-slim-bookworm

WORKDIR /app

# 换 Debian 国内源并安装 OpenCV 运行时依赖（slim 镜像默认不含 libxcb 等）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
    /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        libxcb1 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 无 GPU：PyTorch CPU 轮子走阿里云镜像（勿用 download.pytorch.org，境内极慢）
# ultralytics 会拉 opencv-python（带 GUI），装完后卸掉并强制重装 headless
RUN python -m pip install --no-cache-dir -U pip \
    && python -m pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --find-links https://mirrors.aliyun.com/pytorch-wheels/cpu/ \
    torch==2.5.1 torchvision==0.20.1 \
    && python -m pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements.txt \
    && python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless \
    && python -m pip install --no-cache-dir --force-reinstall \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    opencv-python-headless \
    && python -c "import cv2; print('opencv', cv2.__version__)"

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /app/models

ENV HOST=0.0.0.0 \
    PORT=8090 \
    MODEL_NAME=yolo11m.pt \
    IMGSZ=640 \
    CONF_THRESHOLD=0.35 \
    MIN_BOX_AREA_RATIO=0.001 \
    TORCH_THREADS=4 \
    IMAGE_FETCH_TIMEOUT=10 \
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    PYTHONUNBUFFERED=1

EXPOSE 8090

# 首次启动需加载模型，预留较长启动时间
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/ready', timeout=8)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]
