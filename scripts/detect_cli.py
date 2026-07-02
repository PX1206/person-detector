"""本地命令行测试：python scripts/detect_cli.py path/to/image.jpg"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2

from app.config import get_settings
from app.detector import PersonDetector


def main() -> None:
    parser = argparse.ArgumentParser(description="YOLO11s 人形检测 CLI")
    parser.add_argument("image", type=Path, help="本地图片路径")
    args = parser.parse_args()

    if not args.image.exists():
        raise SystemExit(f"图片不存在: {args.image}")

    settings = get_settings()
    detector = PersonDetector(settings)
    detector.load()

    image = cv2.imread(str(args.image))
    if image is None:
        raise SystemExit(f"无法读取图片: {args.image}")

    result = detector.detect(image)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
