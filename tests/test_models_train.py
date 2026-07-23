"""v1/v2 train-predict round trips on synthetic data (core AVM paths)."""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def market_df():
    """400 synthetic sales: price = ppm(area, floor) × area + noise."""
    rng = np.random.default_rng(42)
    n = 400
    area = rng.uniform(40, 120, n)
    floor = rng.integers(1, 25, n)
    ppm = 8e6 + 2e4 * floor + rng.normal(0, 2e5, n)
    df = pd.DataFrame(
        {
            "price": ppm * area,
            "net_area_sqm": area,
            "log_net_area": np.log(area),
            "floor_number": floor,
            "floor_ratio": floor / 25,
            "age_years": rng.integers(0, 30, n),
            "age_bucket": "6-10",
            "admin_level_2": rng.choice(["강남구", "노원구"], n),
            "admin_level_3": "동",
            "heating_type": "DISTRICT",
            "complex_median_ppm_365d": ppm * rng.normal(1.0, 0.02, n),
            "complex_transaction_count_365d": rng.integers(1, 20, n),
            "complex_ppm_std_365d": rng.uniform(0, 1e5, n),
            "complex_last_transaction_days_ago": rng.integers(1, 300, n),
        }
    )
    return df


def test_v1_hedonic_roundtrip(market_df):
    from packages.avm.models.v1_hedonic import predict_v1, train_v1

    ms = train_v1(market_df, min_rows=50)
    assert len(ms.models) == 2  # both districts trained
    preds = predict_v1(ms, market_df)
    ape = ((preds - market_df["price"]).abs() / market_df["price"]).median()
    assert ape < 0.10  # near-linear synthetic market → hedonic fits well


def test_v2_lightgbm_roundtrip(tmp_path, market_df):
    from packages.avm.models.v2_lightgbm import load_v2, predict_v2, save_v2, train_v2

    small_params = {
        "objective": "regression",
        "n_estimators": 60,
        "learning_rate": 0.15,
        "num_leaves": 15,
        "min_data_in_leaf": 10,
        "random_state": 42,
        "verbosity": -1,
    }
    train, val = market_df.iloc[:300], market_df.iloc[300:]
    model = train_v2(train, val, params=small_params)
    preds = predict_v2(model, val)
    ape = ((preds - val["price"]).abs() / val["price"]).median()
    assert ape < 0.15

    # artifact round trip (docs/03 §4)
    save_v2(model, tmp_path, metrics={"mdape": float(ape)}, manifest={"seed": 42})
    restored = load_v2(tmp_path)
    preds2 = predict_v2(restored, val)
    assert np.allclose(preds.values, preds2.values, rtol=1e-6)


def test_core_config_and_adapter_interface():
    from packages.adapter_kr.adapter import KoreaAdapter
    from packages.core.config import Settings

    s = Settings(_env_file=None)  # defaults, no .env
    assert s.sui_clock_id == "0x6"

    adapter = KoreaAdapter.__new__(KoreaAdapter)  # no client construction
    assert adapter.normalize_local_id(" kr-11680 ") == "KR-11680"
    normalized, original = adapter.normalize_address("서울특별시 강남구 테헤란로 45")
    assert "Gangnam-gu" in normalized and original.startswith("서울")
