from __future__ import annotations

MBTI_TYPES = (
    "INTJ", "INTP", "ENTJ", "ENTP",
    "INFJ", "INFP", "ENFJ", "ENFP",
    "ISTJ", "ISFJ", "ESTJ", "ESFJ",
    "ISTP", "ISFP", "ESTP", "ESFP",
)

def normalize_mbti(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if value not in MBTI_TYPES:
        raise ValueError(f"Unsupported MBTI type: {value}")
    return value
