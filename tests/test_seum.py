from pathlib import Path

import pytest

from packages.adapter_kr.seum.client import SeumApiError, parse_title_info
from packages.adapter_kr.seum.normalizer import is_apartment, to_property_enrichment

FIXTURES = Path(__file__).parent / "fixtures" / "seum"


@pytest.fixture
def title_info():
    return parse_title_info((FIXTURES / "title_info_normal.xml").read_bytes())


def test_parse_title_info(title_info):
    assert len(title_info) == 1
    raw = title_info[0]
    assert raw["bldNm"] == "역삼래미안"
    assert raw["hhldCnt"] == "320"
    assert raw["mainPurpsCdNm"] == "아파트"


def test_parse_error_response():
    with pytest.raises(SeumApiError) as exc_info:
        parse_title_info((FIXTURES / "title_info_error.xml").read_bytes())
    assert exc_info.value.result_code == "30"


def test_enrichment_mapping(title_info):
    e = to_property_enrichment(title_info[0])
    assert e["units_in_building"] == 320
    assert e["floors_total"] == 25
    assert e["building_area_sqm"] == 45230.55
    assert e["built_year"] == 2015
    assert e["parking_spaces"] == 400  # 350 + 50
    assert e["property_subtype"] == "철근콘크리트구조"


def test_enrichment_skips_missing_fields():
    e = to_property_enrichment({"bldNm": "x"})
    assert e == {}


def test_is_apartment(title_info):
    assert is_apartment(title_info[0]) is True
    assert is_apartment({"mainPurpsCd": "01000"}) is False
    assert is_apartment({"mainPurpsCdNm": "아파트"}) is True
    assert is_apartment({}) is False
    # live API combines code+name in one field (observed 2026-07-23)
    assert is_apartment({"mainPurpsCd": "02000 공동주택"}) is True
    assert is_apartment({"mainPurpsCd": "01000 단독주택"}) is False
