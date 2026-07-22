"""Korean address normalization (docs/02-korea-adapter.md §5.2).

원본: `서울특별시 강남구 테헤란로 45`
정규화: `45, Teheran-ro, Gangnam-gu, Seoul`

Unicode-safe by design so the interface extends to Arabic for UAE (docs/06 §8).
"""

import re

# 시/도 → English (MOFA romanization for major cities)
SIDO_EN: dict[str, str] = {
    "서울특별시": "Seoul",
    "서울시": "Seoul",
    "서울": "Seoul",
    "부산광역시": "Busan",
    "인천광역시": "Incheon",
    "경기도": "Gyeonggi-do",
}

# 서울 25개 자치구 romanization
GU_EN: dict[str, str] = {
    "종로구": "Jongno-gu",
    "중구": "Jung-gu",
    "용산구": "Yongsan-gu",
    "성동구": "Seongdong-gu",
    "광진구": "Gwangjin-gu",
    "동대문구": "Dongdaemun-gu",
    "중랑구": "Jungnang-gu",
    "성북구": "Seongbuk-gu",
    "강북구": "Gangbuk-gu",
    "도봉구": "Dobong-gu",
    "노원구": "Nowon-gu",
    "은평구": "Eunpyeong-gu",
    "서대문구": "Seodaemun-gu",
    "마포구": "Mapo-gu",
    "양천구": "Yangcheon-gu",
    "강서구": "Gangseo-gu",
    "구로구": "Guro-gu",
    "금천구": "Geumcheon-gu",
    "영등포구": "Yeongdeungpo-gu",
    "동작구": "Dongjak-gu",
    "관악구": "Gwanak-gu",
    "서초구": "Seocho-gu",
    "강남구": "Gangnam-gu",
    "송파구": "Songpa-gu",
    "강동구": "Gangdong-gu",
}

# Common road-name romanizations (extended as needed; fallback keeps hangul)
ROAD_EN: dict[str, str] = {
    "테헤란로": "Teheran-ro",
    "강남대로": "Gangnam-daero",
    "올림픽로": "Olympic-ro",
    "세종대로": "Sejong-daero",
    "종로": "Jong-ro",
    "을지로": "Eulji-ro",
}

_ROAD_SUFFIX = re.compile(r"(로|길|대로)$")


def romanize_road(road: str) -> str:
    """Best-effort road-name romanization; known names via table, else keep original."""
    return ROAD_EN.get(road, road)


def normalize_address(raw_address: str) -> tuple[str, str]:
    """Returns (normalized_english, original).

    Rule: `{building_no}, {road_en}, {gu_en}, {city_en}`.
    Unknown tokens are passed through unchanged (never lossy).
    """
    original = raw_address.strip()
    tokens = original.split()

    city = None
    gu = None
    road = None
    building_no = None
    extras: list[str] = []

    for tok in tokens:
        if tok in SIDO_EN and city is None:
            city = SIDO_EN[tok]
        elif tok in GU_EN and gu is None:
            gu = GU_EN[tok]
        elif _ROAD_SUFFIX.search(tok) and road is None:
            road = romanize_road(tok)
        elif re.fullmatch(r"\d+(-\d+)?", tok) and building_no is None:
            building_no = tok
        else:
            extras.append(tok)

    parts = [p for p in [building_no, road, gu, city] if p]
    normalized = ", ".join(parts) if parts else original
    if extras:
        normalized = f"{normalized} ({' '.join(extras)})" if parts else original
    return normalized, original
