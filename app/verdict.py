"""与 Java AlarmAiVerdict 一致的判定阈值。"""

HIGH_CONFIDENCE = 0.60
SUSPECT_CONFIDENCE = 0.30


def has_actionable_person(person_count: int, max_confidence: float) -> bool:
    """有人或疑似有人（≥30%）；误报（无检出或 <30%）返回 False。"""
    if person_count <= 0:
        return False
    return max_confidence >= SUSPECT_CONFIDENCE
