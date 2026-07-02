#!/bin/bash
# 下载 YOLO 权重到 models/（无需宿主机安装 ultralytics）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODEL_NAME="${1:-yolo11m.pt}"
TARGET="models/${MODEL_NAME}"

mkdir -p models

if [ -f "$TARGET" ]; then
  echo "已存在: $TARGET ($(du -h "$TARGET" | cut -f1))"
  exit 0
fi

# ultralytics 官方权重（按常见 release 依次尝试）
URLS=(
  "https://github.com/ultralytics/assets/releases/download/v8.3.0/${MODEL_NAME}"
  "https://github.com/ultralytics/assets/releases/download/v8.4.0/${MODEL_NAME}"
  "https://github.com/ultralytics/assets/releases/download/v8.5.0/${MODEL_NAME}"
)

for url in "${URLS[@]}"; do
  echo "尝试下载: $url"
  if curl -fL --connect-timeout 15 --max-time 600 -o "$TARGET" "$url"; then
    size="$(du -h "$TARGET" | cut -f1)"
    echo "完成: $TARGET ($size)"
    exit 0
  fi
  rm -f "$TARGET"
done

echo "wget/curl 下载失败。若已部署 Docker，可改用:"
echo "  docker compose run --rm person-detector python scripts/download_model.py ${MODEL_NAME}"
exit 1
