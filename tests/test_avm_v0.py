from datetime import date

import pandas as pd
import pytest

from packages.avm.models.v0_median import predict_v0


@pytest.fixture
def transactions():
    return pd.DataFrame(
        {
            "complex_id": ["C1"] * 5 + ["C2"] * 2,
            "transaction_date": [
                "2024-01-10",
                "2024-02-15",
                "2024-03-01",
                "2024-05-20",
                "2024-08-01",  # AFTER target date — must be ignored
                "2024-03-05",
                "2024-04-10",
            ],
            "price": [
                850_000_000,
                900_000_000,
                880_000_000,
                910_000_000,
                2_000_000_000,
                500_000_000,
                520_000_000,
            ],
            "net_area_sqm": [84.99, 84.99, 84.99, 84.99, 84.99, 59.84, 59.84],
        }
    )


def test_v0_uses_median_ppm(transactions):
    pred = predict_v0("C1", 84.99, date(2024, 6, 1), transactions)
    # window 2023-12-04..2024-05-31 → 4 C1 trades; median price = 890M (even count)
    assert pred == pytest.approx(890_000_000, rel=1e-6)


def test_v0_excludes_future_transactions(transactions):
    """The 2024-08-01 trade at 2B must never leak into a 2024-06-01 prediction."""
    pred = predict_v0("C1", 84.99, date(2024, 6, 1), transactions)
    assert pred < 1_000_000_000


def test_v0_refuses_below_min_comparables(transactions):
    # C2 has only 2 trades in window → refuse
    assert predict_v0("C2", 59.84, date(2024, 6, 1), transactions) is None


def test_v0_refuses_unknown_complex(transactions):
    assert predict_v0("NOPE", 84.99, date(2024, 6, 1), transactions) is None


def test_v0_scales_by_area(transactions):
    small = predict_v0("C1", 59.0, date(2024, 6, 1), transactions)
    large = predict_v0("C1", 114.0, date(2024, 6, 1), transactions)
    assert small is not None and large is not None
    assert large / small == pytest.approx(114.0 / 59.0)
