from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8090

    model_name: str = "yolo11m.pt"
    model_dir: Path = BASE_DIR / "models"
    imgsz: int = 640
    conf_threshold: float = 0.35
    min_box_area_ratio: float = 0.001

    torch_threads: int = 4
    image_fetch_timeout: float = 10.0
    image_fetch_prefer_ipv4: bool = True

    @property
    def model_path(self) -> Path:
        return self.model_dir / self.model_name


@lru_cache
def get_settings() -> Settings:
    return Settings()
