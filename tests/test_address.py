from packages.adapter_kr.geo.address_normalizer import normalize_address


def test_normalize_teheran_ro():
    normalized, original = normalize_address("서울특별시 강남구 테헤란로 45")
    assert normalized == "45, Teheran-ro, Gangnam-gu, Seoul"
    assert original == "서울특별시 강남구 테헤란로 45"


def test_normalize_unknown_road_kept():
    normalized, _ = normalize_address("서울특별시 송파구 위례성대로 12")
    assert "Songpa-gu" in normalized
    assert "12" in normalized


def test_normalize_passthrough_when_unparseable():
    raw = "somewhere unrecognizable"
    normalized, original = normalize_address(raw)
    assert original == raw
    assert normalized  # never empty
