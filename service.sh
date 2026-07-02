#!/bin/bash
# person-detector Docker 运维脚本（在 person-detector 目录下执行）
# 必须用 bash 运行；若误用 sh 调用则自动切换
if [ -z "${BASH_VERSION:-}" ]; then
  exec /bin/bash "$0" "$@"
fi
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SERVICE_URL="${PERSON_DETECTOR_URL:-http://127.0.0.1:8090}"
READY_TIMEOUT="${READY_TIMEOUT:-120}"
READY_INTERVAL="${READY_INTERVAL:-2}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "未找到 docker 命令"
  docker compose version >/dev/null 2>&1 || die "未找到 docker compose（需 Docker Compose V2）"
}

image_name() {
  echo "person-detector:${IMAGE_TAG:-0.1.0}"
}

# 首次部署：本地无镜像时自动 build；生产机 docker load 后已有镜像则跳过
ensure_image() {
  local img
  img="$(image_name)"
  if docker image inspect "$img" >/dev/null 2>&1; then
    log "镜像已存在: $img"
    return 0
  fi
  log "未找到镜像 $img，开始首次构建（约数分钟，仅第一次需要）..."
  docker compose build
  log "构建完成"
}

wait_ready() {
  local start=$SECONDS
  local deadline=$((start + READY_TIMEOUT))
  local last_log=0
  log "等待服务就绪: ${SERVICE_URL}/ready （最多 ${READY_TIMEOUT}s，yolo11m 加载约 1~3 分钟）"

  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 3 "${SERVICE_URL}/ready" >/dev/null 2>&1; then
      log "服务已就绪（耗时约 $((SECONDS - start))s）"
      curl -fsS "${SERVICE_URL}/ready" 2>/dev/null || true
      echo
      return 0
    fi
    local waited=$((SECONDS - start))
    if (( waited - last_log >= 10 )); then
      log "仍在加载模型... 已等待 ${waited}s"
      docker compose ps --format '{{.Status}}' person-detector 2>/dev/null | head -1 || true
      last_log=$waited
    fi
    sleep "$READY_INTERVAL"
  done

  log "WARN: 在 ${READY_TIMEOUT}s 内未就绪"
  show_recent_logs
  return 1
}

show_recent_logs() {
  log "最近容器日志（排查 Restarting / 崩溃）:"
  docker compose logs --tail="${LOG_TAIL:-80}" person-detector 2>/dev/null || true
}

preflight() {
  local ok=true

  if [ ! -f .env ]; then
    log "WARN: 缺少 .env，请执行: cp .env.example .env"
    ok=false
  fi

  local model_name="yolo11m.pt"
  if [ -f .env ]; then
    model_name="$(grep -E '^MODEL_NAME=' .env | tail -1 | cut -d= -f2- | tr -d '\r' || true)"
    model_name="${model_name:-yolo11m.pt}"
  fi
  if [ ! -f "models/${model_name}" ]; then
    log "ERROR: 缺少模型文件 models/${model_name}，请执行: python scripts/download_model.py ${model_name}"
    ok=false
  fi

  for f in app/main.py app/detector.py app/config.py app/verdict.py; do
    if [ ! -f "$f" ]; then
      log "ERROR: 缺少 $f（检查 app/ 目录是否完整上传）"
      ok=false
    fi
  done

  if [ "$ok" = false ]; then
    die "启动前检查未通过，请修复上述问题后重试"
  fi
}

cmd_start() {
  require_docker
  preflight
  ensure_image
  if ! docker compose ps --status running --services 2>/dev/null | grep -qx person-detector; then
    log "启动容器..."
    docker compose up -d
  else
    log "容器已在运行"
  fi
  wait_ready || true
  if ! curl -fsS --max-time 3 "${SERVICE_URL}/ready" >/dev/null 2>&1; then
    local status
    status="$(docker compose ps --format '{{.Status}}' person-detector 2>/dev/null || true)"
    if echo "$status" | grep -qi restarting; then
      log "ERROR: 容器反复重启，通常是启动崩溃（见上方日志）"
    fi
  fi
  cmd_status
}

cmd_stop() {
  require_docker
  log "停止容器..."
  docker compose down
  log "已停止"
}

cmd_restart() {
  require_docker
  log "重启容器（改 Python 代码后执行此命令，无需 rebuild）..."
  docker compose restart
  wait_ready || true
  cmd_status
}

cmd_build() {
  require_docker
  log "构建镜像（仅 requirements.txt / Dockerfile 变更时需要）..."
  docker compose build
  log "构建完成"
}

cmd_rebuild() {
  require_docker
  cmd_build
  log "重新创建并启动容器..."
  docker compose up -d --force-recreate
  wait_ready || true
  cmd_status
}

cmd_status() {
  require_docker
  echo
  docker compose ps
  echo
  if curl -fsS --max-time 3 "${SERVICE_URL}/health" >/dev/null 2>&1; then
    log "health: $(curl -fsS "${SERVICE_URL}/health")"
  else
    log "health: 不可达"
  fi
  if curl -fsS --max-time 3 "${SERVICE_URL}/ready" >/dev/null 2>&1; then
    log "ready:  $(curl -fsS "${SERVICE_URL}/ready")"
  else
    log "ready:  未就绪（可能仍在加载模型）"
  fi
}

cmd_logs() {
  require_docker
  docker compose logs -f --tail="${TAIL:-100}" person-detector
}

usage() {
  cat <<EOF
用法: $0 <命令>

命令:
  start     启动服务（无镜像时自动 build，首次约数分钟）
  stop      停止服务
  restart   重启服务（日常改 Python 代码后用这个）
  status    查看容器与健康检查状态
  logs      查看日志（实时跟踪，Ctrl+C 退出）
  build     仅构建镜像（改依赖时用）
  rebuild   构建镜像并强制重建容器（改 Dockerfile/requirements 后用）

示例:
  cd /data/person-detector
  chmod +x service.sh
  ./service.sh start
  ./service.sh restart
  ./service.sh status

环境变量:
  PERSON_DETECTOR_URL  默认 http://127.0.0.1:8090
  READY_TIMEOUT        等待就绪秒数，默认 120
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    restart) cmd_restart ;;
    status) cmd_status ;;
    logs) cmd_logs ;;
    build) cmd_build ;;
    rebuild) cmd_rebuild ;;
    -h|--help|help|"") usage ;;
    *) die "未知命令: $cmd（执行 $0 help 查看帮助）" ;;
  esac
}

main "$@"
