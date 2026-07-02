# Person Detector

报警图片人形二次检测服务，基于 YOLO11s + FastAPI，运行在 CPU 环境。

## 环境要求

- Python 3.10+（Docker 部署时由镜像提供，无需宿主机升级 Python）
- 4 核 CPU 服务器（已针对 CPU 推理配置 `TORCH_THREADS=4`）

## 快速开始

```bash
cd person-detector
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux
```

首次启动会自动下载 `yolo11s.pt` 到 `models/` 目录。

## 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8090 --workers 1
```

## 本地 CLI 测试

```bash
python scripts/detect_cli.py test.jpg
```

## API

### 健康检查

```http
GET /health
GET /ready
```

### URL 检测

```http
POST /api/v1/detect/person
Content-Type: application/json

{
  "alarm_id": "optional-alarm-id",
  "image_url": "https://example.com/alarm.jpg"
}
```

响应示例：

```json
{
  "has_person": true,
  "person_count": 1,
  "max_confidence": 0.8721,
  "boxes": [
    {
      "confidence": 0.8721,
      "x1": 120.5,
      "y1": 80.2,
      "x2": 340.1,
      "y2": 520.8,
      "area_ratio": 0.045
    }
  ],
  "latency_ms": 680,
  "image_width": 1920,
  "image_height": 1080
}
```

### 上传图片检测

```http
POST /api/v1/detect/person/upload
Content-Type: multipart/form-data

file=<image>
alarm_id=optional
```

### 批量检测（多张抓拍）

```http
POST /api/v1/detect/person/batch
Content-Type: application/json

{
  "alarm_id": "xxx",
  "image_urls": [
    "https://example.com/alarm_1.jpg",
    "https://example.com/alarm_2.jpg"
  ],
  "require_any": true
}
```

`require_any=true` 表示任意一张有人即判定为有人。

## 配置项（.env）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| MODEL_NAME | yolo11s.pt | 模型文件名 |
| IMGSZ | 640 | 推理输入尺寸 |
| CONF_THRESHOLD | 0.35 | 置信度阈值 |
| MIN_BOX_AREA_RATIO | 0.001 | 最小框面积占比，过滤远处误检 |
| TORCH_THREADS | 4 | PyTorch CPU 线程数 |
| IMAGE_FETCH_TIMEOUT | 10 | 拉取图片超时（秒） |

## 部署

### 方式一：Docker（推荐，测试/生产环境一致）

**目录结构（上传到服务器）：**

```text
/data/person-detector/
├── app/
├── scripts/
├── models/yolo11s.pt    # 提前放好模型，避免容器内下载
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env                 # 从 .env.example 复制
```

**测试环境首次部署：**

```bash
cd /data/person-detector
cp .env.example .env
# 将 yolo11s.pt 放到 models/ 目录（可从开发机 person-detector/models/ 拷贝）

docker compose build
docker compose up -d
docker compose logs -f
```

**健康检查：**

```bash
curl http://127.0.0.1:8090/health
curl http://127.0.0.1:8090/ready    # ready=true 表示模型已加载
```

**迁移到生产环境（无镜像仓库时，导出/导入镜像）：**

```bash
# 测试机：构建并导出
cd /data/person-detector
docker compose build
docker save person-detector:0.1.0 | gzip > person-detector-0.1.0.tar.gz

# 生产机：上传 person-detector 目录 + tar.gz
gunzip -c person-detector-0.1.0.tar.gz | docker load
cd /data/person-detector
cp .env.example .env   # 按生产环境调整 TORCH_THREADS 等
docker compose up -d
```

**有私有镜像仓库时：**

```bash
# 测试机
docker tag person-detector:0.1.0 registry.example.com/person-detector:0.1.0
docker push registry.example.com/person-detector:0.1.0

# 生产机 docker-compose.yml 改为 image: registry.example.com/person-detector:0.1.0
docker compose pull && docker compose up -d
```

**日常更新 Python 代码（不用 rebuild）：**

`app/`、`scripts/` 已通过 volume 挂载，改代码后重启容器即可（模型加载通常 20–60 秒）：

```bash
cd /data/person-detector
chmod +x service.sh

# 改代码后
./service.sh restart

# 首次启动
./service.sh start

# 查看状态 / 日志
./service.sh status
./service.sh logs
```

`service.sh` 会在重启后自动轮询 `/ready`，直到服务可用或超时。

**只有以下情况才需要 build：**

- 修改了 `requirements.txt` 或 `Dockerfile`（依赖/基础镜像变更）
- 首次部署或升级 Python 依赖版本

```bash
./service.sh rebuild
```

仅改代码时若误执行 `build`，Docker 也会命中缓存，通常只重建 COPY 层（几十秒），不会重新下载 PyTorch。

**常用运维命令：**

```bash
./service.sh status
./service.sh logs
./service.sh stop
```

**Java 配置（配置中心 `web_report_conf`）：**

```properties
person_detector_enabled=1
person_detector_url=http://127.0.0.1:8090
person_detector_delay_ms=0
person_detector_min_images_before_none=2
person_detector_timeout_ms=30000
```

> 容器只监听 `127.0.0.1:8090`，不暴露公网。若 Python 与 Java 不在同一台机器，`person_detector_url` 改为内网 IP。

---

### 方式二：systemd + venv（同机无 Docker 时）

参考 `deploy/person-detector.service`，部署路径示例 `/data/person-detector/`（需 Python 3.10+）。

```bash
sudo cp deploy/person-detector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable person-detector
sudo systemctl start person-detector
```

### 卸载旧部署（从 /webdata 迁到 /data 时）

若之前在 `/webdata/person-detector` 或其它路径试过，先清理再在新目录部署：

```bash
# 1. 停 Docker 容器（在旧目录执行，若存在）
cd /webdata/person-detector 2>/dev/null && docker compose down || true

# 2. 停 systemd 服务（若装过）
sudo systemctl stop person-detector 2>/dev/null || true
sudo systemctl disable person-detector 2>/dev/null || true
sudo rm -f /etc/systemd/system/person-detector.service
sudo systemctl daemon-reload

# 3. 删除旧目录（确认里面没有要保留的文件）
sudo rm -rf /webdata/person-detector
```

> 仅卸载 person-detector，**不会**卸载 Docker 本身；Docker 可继续给其它服务用。

## 说明

- **gateway** 仅负责 OSS 上传与 MQ，不做 AI 推理。
- **web-report-controller** 消费 MQ 后异步调用本服务识别并入库。
