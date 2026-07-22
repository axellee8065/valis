from datetime import date
from decimal import Decimal

import pytest

from packages.adapter_kr.fx.ecos_client import EcosApiError, parse_ecos_rows
from packages.core.fx import FxProvider


class TestParseEcosRows:
    def test_parses_daily_rates(self):
        payload = {
            "StatisticSearch": {
                "list_total_count": 2,
                "row": [
                    {"TIME": "20240115", "DATA_VALUE": "1,320.5"},
                    {"TIME": "20240116", "DATA_VALUE": "1315.0"},
                ],
            }
        }
        rates = parse_ecos_rows(payload)
        assert len(rates) == 2
        assert rates[0].rate_date == date(2024, 1, 15)
        assert rates[0].krw_per_usd == Decimal("1320.5")
        # usd_per_krw is the reciprocal
        assert rates[0].usd_per_krw == pytest.approx(Decimal("0.000757289"), abs=1e-8)

    def test_skips_empty_values(self):
        payload = {
            "StatisticSearch": {
                "row": [
                    {"TIME": "20240113", "DATA_VALUE": ""},  # holiday
                    {"TIME": "20240115", "DATA_VALUE": "1320.5"},
                ]
            }
        }
        assert len(parse_ecos_rows(payload)) == 1

    def test_error_envelope_raises(self):
        with pytest.raises(EcosApiError, match="INFO-100"):
            parse_ecos_rows({"RESULT": {"CODE": "INFO-100", "MESSAGE": "인증키 오류"}})


class TestFxProvider:
    @pytest.fixture
    def provider(self):
        return FxProvider(
            {
                date(2024, 1, 12): Decimal("0.00076"),  # Friday
                date(2024, 1, 15): Decimal("0.00075"),  # Monday
            }
        )

    def test_exact_date(self, provider):
        assert provider.rate_at(date(2024, 1, 15)) == Decimal("0.00075")

    def test_weekend_falls_back_to_friday(self, provider):
        assert provider.rate_at(date(2024, 1, 13)) == Decimal("0.00076")
        assert provider.rate_at(date(2024, 1, 14)) == Decimal("0.00076")

    def test_never_uses_future_rate(self, provider):
        assert provider.rate_at(date(2024, 1, 11)) is None  # only future rates exist

    def test_stale_beyond_fallback_window(self, provider):
        assert provider.rate_at(date(2024, 2, 15)) is None  # > 7 days after last rate

    def test_accepts_iso_string(self, provider):
        assert provider.rate_at("2024-01-15") == Decimal("0.00075")

    def test_callable_form(self, provider):
        assert provider("2024-01-15") == Decimal("0.00075")

    def test_empty_provider(self):
        assert FxProvider({}).rate_at(date(2024, 1, 1)) is None
