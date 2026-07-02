from pydantic import BaseModel, Field, HttpUrl


class PersonBox(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    x1: float
    y1: float
    x2: float
    y2: float
    area_ratio: float = Field(..., ge=0.0, le=1.0)


class PersonDetectResult(BaseModel):
    has_person: bool
    person_count: int = Field(..., ge=0)
    max_confidence: float = Field(0.0, ge=0.0, le=1.0)
    boxes: list[PersonBox] = Field(default_factory=list)
    latency_ms: int = Field(..., ge=0)
    image_width: int = Field(..., ge=0)
    image_height: int = Field(..., ge=0)


class PersonDetectByUrlRequest(BaseModel):
    image_url: HttpUrl
    alarm_id: str | None = None


class PersonDetectBatchRequest(BaseModel):
    image_urls: list[HttpUrl] = Field(..., min_length=1, max_length=10)
    alarm_id: str | None = None
    require_any: bool = True


class PersonDetectBatchResult(BaseModel):
    has_person: bool
    person_count: int = Field(..., ge=0)
    max_confidence: float = Field(0.0, ge=0.0, le=1.0)
    latency_ms: int = Field(..., ge=0)
    results: list[PersonDetectResult]
