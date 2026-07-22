import numpy as np
import pandas as pd

from packages.avm.features.common import (
    add_complex_rolling_features,
    add_intrinsic_features,
    age_bucket,
    impute,
)


def test_age_bucket():
    assert age_bucket(3) == "0-5"
    assert age_bucket(8) == "6-10"
    assert age_bucket(25) == "21-30"
    assert age_bucket(50) == "31-+"
    assert age_bucket(None) == "__missing__"


def test_intrinsic_features():
    df = pd.DataFrame(
        {
            "net_area_sqm": [84.99, 59.84],
            "floor_number": [12, 1],
            "floors_total": [25, 25],
            "built_year": [2015, 2000],
            "transaction_date": ["2024-01-15", "2024-01-15"],
            "units_in_building": [1200, 300],
        }
    )
    out = add_intrinsic_features(df)
    assert out["floor_ratio"].iloc[0] == 12 / 25
    assert bool(out["is_ground_floor"].iloc[1]) is True
    assert out["age_years"].iloc[0] == 9
    assert out["age_bucket"].iloc[0] == "6-10"
    assert bool(out["is_large_complex"].iloc[0]) is True
    assert bool(out["is_large_complex"].iloc[1]) is False


def test_rolling_features_exclude_current_and_future():
    """Leakage guard: rolling stats must only see strictly-prior transactions."""
    df = pd.DataFrame(
        {
            "complex_id": ["C1"] * 3,
            "transaction_date": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "price": [100.0, 200.0, 300.0],
            "net_area_sqm": [1.0, 1.0, 1.0],
        }
    )
    out = add_complex_rolling_features(df)
    # First transaction: no priors
    assert out["complex_transaction_count_365d"].iloc[0] == 0
    assert np.isnan(out["complex_median_ppm_365d"].iloc[0])
    # Second: sees only the first
    assert out["complex_transaction_count_365d"].iloc[1] == 1
    assert out["complex_median_ppm_365d"].iloc[1] == 100.0
    # Third: sees first two (median 150), never its own price
    assert out["complex_transaction_count_365d"].iloc[2] == 2
    assert out["complex_median_ppm_365d"].iloc[2] == 150.0


def test_impute():
    df = pd.DataFrame({"x": [1.0, np.nan, 3.0], "cat": ["a", None, "b"]})
    out = impute(df, ["x"], ["cat"])
    assert out["x"].iloc[1] == 2.0
    assert bool(out["x__missing"].iloc[1]) is True
    assert out["cat"].iloc[1] == "__missing__"
