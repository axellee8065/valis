from datetime import date

import pytest

from packages.avm.registry import make_model_id, parse_model_id


def test_make_and_parse_roundtrip():
    mid = make_model_id("KR", "seoul", "apt", 2, trained_on=date(2026, 3, 15), sha="a3f8c2")
    assert mid == "avm-kr-seoul-apt-v2-20260315-a3f8c2"
    parsed = parse_model_id(mid)
    assert parsed["country"] == "kr"
    assert parsed["version"] == "2"
    assert parsed["sha"] == "a3f8c2"


def test_uae_scoped_ids_supported():
    """docs/06 §3.3 — registry must support property_type-scoped UAE models."""
    for mid in [
        "avm-ae-dubai-apt-v1-20260901-b7c1d3",
        "avm-ae-dubai-villa-v1-20260901-b7c1d3",
    ]:
        assert parse_model_id(mid)["country"] == "ae"


def test_invalid_model_id_rejected():
    with pytest.raises(ValueError):
        parse_model_id("not-a-model-id")
