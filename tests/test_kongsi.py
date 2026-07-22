from datetime import date
from decimal import Decimal
from typing import ClassVar

import pytest

from packages.adapter_kr.kongsi.client import KongsiApiError, extract_items
from packages.adapter_kr.kongsi.normalizer import (
    KongsiRecordError,
    parse_pnu,
    to_government_valuation,
)
from packages.core.ids import make_global_id

GID = make_global_id("KR", "KR-11680-10800-1-0045-0000-A-12-8499")


class TestExtractItems:
    def test_vworld_style(self):
        payload = {
            "apartHousingPrices": {
                "totalCount": "2",
                "field": [{"pnu": "x"}, {"pnu": "y"}],
            }
        }
        assert extract_items(payload) == [{"pnu": "x"}, {"pnu": "y"}]

    def test_vworld_single_item_dict(self):
        payload = {"apartHousingPrices": {"totalCount": "1", "field": {"pnu": "x"}}}
        assert extract_items(payload) == [{"pnu": "x"}]

    def test_vworld_error_raises(self):
        with pytest.raises(KongsiApiError, match="INVALID_KEY"):
            extract_items({"error": {"code": "INVALID_KEY", "text": "인증키 오류"}})

    def test_odcloud_style(self):
        assert extract_items({"data": [{"a": 1}], "currentCount": 1}) == [{"a": 1}]

    def test_datago_envelope(self):
        payload = {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "OK"},
                "body": {"items": {"item": [{"pnu": "x"}]}},
            }
        }
        assert extract_items(payload) == [{"pnu": "x"}]

    def test_single_item_wrapped_dict(self):
        payload = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {"items": {"item": {"pnu": "x"}}},
            }
        }
        assert extract_items(payload) == [{"pnu": "x"}]

    def test_error_code_raises(self):
        payload = {"response": {"header": {"resultCode": "22", "resultMsg": "limit"}}}
        with pytest.raises(KongsiApiError, match="22"):
            extract_items(payload)


class TestParsePnu:
    def test_valid_pnu(self):
        parts = parse_pnu("1168010800100450000")
        assert parts == {
            "sgg_cd": "11680",
            "umd_cd": "10800",
            "land_cd": "1",
            "bonbun": "0045",
            "bubun": "0000",
        }

    def test_invalid_pnu_rejected(self):
        with pytest.raises(KongsiRecordError):
            parse_pnu("123")


class TestToGovernmentValuation:
    RAW: ClassVar[dict] = {
        "pnu": "1168010800100450000",
        "stdrYear": "2024",
        "pblntfPc": "980,000,000",
        "pblntfDe": "2024-04-30",
        "sggNm": "강남구",
        "bjdongNm": "역삼동",
        "bldNm": "역삼래미안",
        "dongNm": "A",
        "hoNm": "1201",
    }

    def test_normalization(self):
        gv = to_government_valuation(self.RAW, GID, fx_krw_usd=Decimal("0.00072"))
        assert gv.valuation_type == "KR_APT_KONGSI"
        assert gv.assessment_year == 2024
        assert gv.assessment_date == date(2024, 4, 30)
        assert gv.value_original_amount == Decimal(980_000_000)
        assert gv.value_original_currency == "KRW"
        assert gv.value_usd_cents == 70_560_000  # $705,600
        assert gv.raw_payload["hoNm"] == "1201"

    def test_missing_price_dead_letters(self):
        raw = {**self.RAW, "pblntfPc": None}
        with pytest.raises(KongsiRecordError):
            to_government_valuation(raw, GID, fx_krw_usd=Decimal("0.00072"))

    def test_bad_date_dead_letters(self):
        raw = {**self.RAW, "pblntfDe": "not-a-date"}
        with pytest.raises(KongsiRecordError):
            to_government_valuation(raw, GID, fx_krw_usd=Decimal("0.00072"))

    def test_vworld_record_without_pblntf_de(self):
        """VWorld 속성조회 has stdrYear only → assessment_date = Jan 1 (기준일)."""
        raw = {
            "pnu": "1168010800100450000",
            "stdrYear": "2024",
            "pblntfPc": "980000000",
            "dongNm": "A",
            "hoNm": "1201",
            "prvuseAr": "84.99",
        }
        gv = to_government_valuation(raw, GID, fx_krw_usd=Decimal("0.00072"))
        assert gv.assessment_year == 2024
        assert gv.assessment_date == date(2024, 1, 1)
        assert gv.value_original_amount == Decimal(980_000_000)

    def test_record_without_any_year_dead_letters(self):
        raw = {"pnu": "1168010800100450000", "pblntfPc": "980000000"}
        with pytest.raises(KongsiRecordError):
            to_government_valuation(raw, GID, fx_krw_usd=Decimal("0.00072"))
