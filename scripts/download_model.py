#!/usr/bin/env python3
"""下载 YOLO 权重到 models/ 目录。用法: python scripts/download_model.py [yolo11m.pt]"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"


def main() -> None:
    model_name = sys.argv[1] if len(sys.argv) > 1 else "yolo11m.pt"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / model_name

    if target.exists():
        print(f"已存在: {target}")
        return

    from ultralytics import YOLO

    print(f"正在下载 {model_name} -> {target} ...")
    YOLO(model_name)
    downloaded = MODELS_DIR / model_name
    if not downloaded.exists():
        # ultralytics 可能下载到 cwd，再挪到 models/
        cwd_file = Path(model_name)
        if cwd_file.exists():
            cwd_file.replace(target)
    if target.exists():
        print(f"完成: {target} ({target.stat().st_size // (1024 * 1024)} MB)")
    else:
        raise SystemExit(f"下载失败，未找到 {target}")


if __name__ == "__main__":
    main()
