import numpy as np
import pandas as pd
import pytest

from packages.avm.models.v3_time_adjust import (
    RepeatSalesIndex,
    build_repeat_pairs,
    compute_expanding_index,
    detrend_prices,
    rescale_predictions,
)


def synthetic_market(monthly_growth: float = 0.01, n_units: int = 300, seed: int = 42):
    """Units sold 2-3 times over 2020-2023 with prices following a known index."""
    rng = np.random.default_rng(seed)
    months = pd.period_range("2020-01", "2023-12", freq="M")
    rows = []
    for u in range(n_units):
        base = rng.uniform(3e8, 15e8)
        n_sales = rng.integers(2, 4)
        sale_months = np.sort(rng.choice(len(months), size=n_sales, replace=False))
        for m in sale_months:
            price = base * (1 + monthly_growth) ** m * rng.normal(1.0, 0.02)
            rows.append(
                {
                    "global_id": f"0x{u:064x}",
                    "transaction_date": months[m].to_timestamp() + pd.Timedelta(days=14),
                    "price": price,
                }
            )
    return pd.DataFrame(rows)


class TestRepeatPairs:
    def test_pairs_built_from_consecutive_sales(self):
        df = synthetic_market()
        pairs = build_repeat_pairs(df)
        assert len(pairs) > 100
        assert (pairs["m2"] > pairs["m1"]).all()

    def test_flips_filtered(self):
        df = pd.DataFrame(
            {
                "global_id": ["0x" + "0" * 64] * 2,
                "transaction_date": ["2023-01-01", "2023-01-20"],  # 19-day flip
                "price": [1e9, 1.1e9],
            }
        )
        assert build_repeat_pairs(df).empty

    def test_extreme_ratios_filtered(self):
        df = pd.DataFrame(
            {
                "global_id": ["0x" + "0" * 64] * 2,
                "transaction_date": ["2020-01-01", "2023-01-01"],
                "price": [1e8, 1e9],  # 10x — data error
            }
        )
        assert build_repeat_pairs(df).empty


class TestExpandingIndex:
    def test_recovers_known_growth(self):
        """+1%/month synthetic market → final index ≈ 1.01^47 within 5%."""
        df = synthetic_market(monthly_growth=0.01)
        index = compute_expanding_index(df)
        final = index.at("2023-12")
        expected = 1.01**47
        assert final == pytest.approx(expected, rel=0.05)

    def test_monotone_under_steady_growth(self):
        df = synthetic_market(monthly_growth=0.01)
        index = compute_expanding_index(df)
        vals = [index.at(str(m)) for m in pd.period_range("2021-01", "2023-12", freq="M")]
        # Steadily rising market → late index clearly above early index
        assert vals[-1] > vals[0] * 1.2

    def test_no_future_information(self):
        """index[m] must not change when future transactions are added."""
        df = synthetic_market()
        cutoff = pd.Timestamp("2022-01-01")
        early = df[pd.to_datetime(df["transaction_date"]) < cutoff]
        full_index = compute_expanding_index(df)
        early_index = compute_expanding_index(early)
        # compare a mid-2021 month estimated by both
        assert full_index.at("2021-06") == pytest.approx(early_index.at("2021-06"), rel=1e-9)

    def test_out_of_range_clamps(self):
        index = RepeatSalesIndex(values={"2020-01": 1.0, "2020-02": 1.02})
        assert index.at("2019-01") == 1.0  # before range → first
        assert index.at("2025-01") == 1.02  # after range → last known


class TestDetrendRoundtrip:
    def test_detrend_then_rescale_is_identity(self):
        df = synthetic_market()
        index = compute_expanding_index(df)
        detrended = detrend_prices(df, index)
        restored = rescale_predictions(detrended, df, index)
        assert np.allclose(restored.values, df["price"].astype(float).values)
