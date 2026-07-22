# 03 — AVM Model Design (Automated Valuation Model)

**Package:** `packages/avm`
**Target:** 서울 아파트 MdAPE ≤ 5% (도전 목표), ≤ 7% (최소 목표)

---

## 1. Model Evolution Roadmap

각 버전은 이전 버전의 baseline에 대비해 개선을 정량 증명해야 함.

| Version | Method | 목표 MdAPE | Effort |
|---|---|---|---|
| v0 | 동일 단지 최근 N건 median | 15–20% | 1주 |
| v1 | Hedonic Linear Regression (구별) | 8–12% | 2주 |
| v2 | LightGBM + rich features | 5–7% | 3주 |
| v3 | v2 + repeat-sales index + time adjustment | 3–5% | 2주 |
| v4 | v3 + anomaly detection · confidence scoring | 3–5% + 신뢰구간 | 2주 |

**원칙**: v4까지 안 가도 v2에서 이미 사용 가능한 프로덕션. 뒤로 갈수록 marginal gain 감소, 시간·복잡도 증가.

---

## 2. Feature Catalog

### 2.1 Property intrinsic features

| Feature | Type | Source | Notes |
|---|---|---|---|
| `net_area_sqm` | float | MOLIT | log-transform 고려 |
| `building_area_sqm` | float | MOLIT/세움터 | |
| `floor_number` | int | MOLIT | |
| `floors_total` | int | 세움터 | |
| `floor_ratio` | float | derived | `floor_number / floors_total` |
| `is_top_floor` | bool | derived | `floor_number == floors_total` |
| `is_ground_floor` | bool | derived | `floor_number == 1` |
| `age_years` | int | derived | `transaction_year - built_year` |
| `age_bucket` | cat | derived | `[0-5, 6-10, 11-20, 21-30, 30+]` |
| `units_in_building` | int | 세움터 | 대단지 프리미엄 |
| `is_large_complex` | bool | derived | `units >= 1000` |
| `heating_type` | cat | 세움터 | |
| `structure_code` | cat | 세움터 | RC/SRC 등 |
| `parking_ratio` | float | 세움터 | `parking / units` |

### 2.2 Location features

| Feature | Type | Source | Notes |
|---|---|---|---|
| `admin_level_1` | cat | derived | 서울 (MVP는 상수) |
| `admin_level_2` | cat | derived | 25개 구 |
| `admin_level_3` | cat | derived | 동 (약 400개) |
| `latitude` | float | geocoding | |
| `longitude` | float | geocoding | |
| `dist_to_nearest_subway_m` | float | PostGIS | 최근접 지하철역 거리 |
| `nearest_subway_lines_count` | int | POI | 환승역 여부 |
| `subway_stations_within_500m` | int | PostGIS | |
| `subway_stations_within_1km` | int | PostGIS | |
| `dist_to_gangnam_station_m` | float | derived | 강남역까지 거리 (도심 접근성) |
| `dist_to_ces_m` | float | derived | 여의도까지 거리 |
| `is_gangnam_3gu` | bool | derived | 강남·서초·송파 |
| `dist_to_elem_school_m` | float | PostGIS | |
| `dist_to_middle_school_m` | float | PostGIS | |
| `school_district_score` | float | 학군 지수 (커스텀) | Phase 2 |
| `dist_to_park_m` | float | PostGIS | |
| `dist_to_hospital_m` | float | PostGIS | |
| `dist_to_mall_m` | float | PostGIS | |

### 2.3 Complex-level features (같은 단지 공유)

| Feature | Type | Method | Notes |
|---|---|---|---|
| `complex_median_price_per_sqm_365d` | float | rolling | 최근 365일 동일 단지 실거래 |
| `complex_transaction_count_365d` | int | rolling | 유동성 지표 |
| `complex_price_std_365d` | float | rolling | 단지 내 가격 분산 |
| `complex_last_transaction_days_ago` | int | derived | 정보 신선도 |
| `complex_ppm_yoy_change` | float | derived | 단지 가격 YoY 변화율 |

### 2.4 Market context features

| Feature | Type | Source | Notes |
|---|---|---|---|
| `gu_median_ppm_365d` | float | rolling | 구 단위 중앙값 |
| `gu_transaction_count_90d` | int | rolling | 거래량 |
| `national_apt_index` | float | 한국부동산원 | 아파트 매매지수 |
| `seoul_apt_index` | float | 한국부동산원 | 서울 아파트 지수 |
| `base_rate` | float | 한국은행 | 기준금리 |
| `mortgage_rate` | float | KB통계 | 주택담보대출 평균 |
| `month_of_year` | int | derived | 계절성 |
| `quarter` | cat | derived | |

### 2.5 Temporal features (시계열 조정)

| Feature | Type | Source | Notes |
|---|---|---|---|
| `time_since_reference_date_days` | int | derived | 학습 reference 대비 |
| `repeat_sales_index_at_date` | float | v3 | 자체 계산 반복매매지수 |

### 2.6 Feature engineering rules

- **Never** transaction date 이후 정보를 피처로 사용 (target leakage)
- Rolling window는 반드시 exclude-current-transaction
- Categorical은 target encoding 대신 one-hot or LGBM native cat
- 결측치 처리:
  - Numeric: 세그먼트별 median imputation, missing flag 추가
  - Categorical: `"__missing__"` 값

---

## 3. Model Architecture

### 3.1 v0 — Simple Median

```python
def predict_v0(property_ref, target_date, transactions_df):
    same_complex = transactions_df[
        (transactions_df.complex_id == property_ref.complex_id) &
        (transactions_df.transaction_date < target_date) &
        (transactions_df.transaction_date >= target_date - timedelta(days=180))
    ]
    if len(same_complex) < 3:
        return None  # 신뢰불가
    ppm = same_complex.price / same_complex.net_area_sqm
    predicted_ppm = ppm.median()
    return predicted_ppm * property_ref.net_area_sqm
```

목적: 파이프라인 검증, baseline 확립.

### 3.2 v1 — Hedonic Regression (per-district)

- 구별로 별도 모델 학습 (25개)
- Features: intrinsic + location (subway, distance)
- Target: `log(price_per_sqm)` (선형관계 개선 + 이분산 완화)
- 검증: 구 내 홀드아웃

### 3.3 v2 — LightGBM Global Model

- 전체 서울 단일 모델 (구 정보는 categorical feature로)
- Target: `log(price)` 직접
- 하이퍼파라미터 초기값:
  - `n_estimators=2000`, early stopping on val loss
  - `learning_rate=0.03`
  - `num_leaves=63`
  - `min_data_in_leaf=100`
  - `feature_fraction=0.8`
  - `bagging_fraction=0.8`
  - `objective="regression"`, `metric="mae"`
- Categorical features: `admin_level_2`, `admin_level_3`, `heating_type`, `structure_code`, `age_bucket`

### 3.4 v3 — Time Adjustment

**문제**: 최근 거래가 부족한 물건은 오래된 실거래에 의존 → 시장 변동 반영 실패.

**해결**:
1. 서울 아파트 반복매매지수 자체 계산 (Case-Shiller 방법론)
2. 학습 시 target을 `log(price / index_at_date)`로 detrend
3. 예측 시 `predicted × index_at_target_date`로 rescale

### 3.5 v4 — Confidence + Anomaly

**Confidence score** (0.0–1.0):
```
confidence = weighted_avg([
    normalize(same_complex_transactions_365d, [0, 20]),   # 유동성
    1.0 - normalize(days_since_last_complex_tx, [0, 365]),  # 신선도
    1.0 - normalize(model_prediction_std, [0.05, 0.30]),   # 모델 확신
    normalize(segment_backtest_accuracy, [0.70, 0.95])     # 세그먼트 신뢰도
])
```

Weight는 백테스트로 튜닝.

**Confidence tiers**:
- ≥ 0.85: 자동 발행
- 0.60–0.85: 발행하되 "review recommended" 플래그
- < 0.60: consensus 경로 라우팅 (MVP에서는 발행 거부)

**Anomaly detection**:
- Isolation Forest on features
- 최근 5년 이내 첫 거래인 신축 단지
- 실거래가 대비 공시가격 편차 극단
- 이 flag된 케이스는 confidence 자동 하향

---

## 4. Training Pipeline

```
scripts/train_avm.py --model v2 --target-date 2025-06-30 --output models/v2_20260101/
```

Steps:
1. Load transactions from DB (with train/val/test cutoff)
2. Feature engineering (materialize rolling features per-transaction)
3. Handle categorical, missing
4. Fit model
5. Save:
   - `model.txt` (LightGBM)
   - `feature_config.json`
   - `metrics.json`
   - `training_data_manifest.json` (재현성)

**Reproducibility**:
- `random_state=42` 고정
- 학습 데이터의 min/max transaction date 명시
- pandas version, sklearn version, lightgbm version 기록
- Data snapshot hash

---

## 5. Serving

### 5.1 Batch Prediction

`scripts/predict_batch.py`:
- 대상: 서울 아파트 마스터 전체
- 매일 야간 실행
- Attestation 발급 대상 선정 → attestation 파이프라인 넘김

### 5.2 Online API

`packages/api/routes/valuation.py`:
- `POST /v1/valuation` — request property_ref → return prediction + CI + confidence
- P95 latency < 200ms
- 모델은 프로세스 메모리 상주

---

## 6. Confidence Interval Estimation

두 가지 방법 병행:

### 6.1 LightGBM Quantile Regression
- 별도 모델 3개: `objective="quantile"`, alpha in `[0.025, 0.5, 0.975]`
- 예측 시 세 모델 모두 호출 → CI 산출

### 6.2 Conformal Prediction (권장)
- 학습 완료 모델의 validation set residual을 empirical distribution으로 사용
- 세그먼트별 residual quantile로 CI 계산
- 이론적 커버리지 보장

---

## 7. Segmentation for Reporting

성능·신뢰도는 반드시 세그먼트별로 보고:

| Segment axis | Buckets |
|---|---|
| 지역 | 강남 3구 / 강북 / 강남 외 강남권 / 강북 외 |
| 가격대 | ~5억 / 5–10억 / 10–20억 / 20억+ |
| 면적 | ~59㎡ / 60–84 / 85–114 / 115+ |
| 연식 | 신축 (~5년) / 준신축 (6–15) / 중고 (16–30) / 노후 (30+) |
| 단지 규모 | 소단지 (~300) / 중단지 (300–1000) / 대단지 (1000+) |
| 거래 시기 | quarter별 |

세그먼트별 MdAPE 편차가 프로덕트 신뢰도의 핵심.

---

## 8. Model Registry & Versioning

- 모델 파일 = `models/{model_id}/` 디렉터리
- `model_id` 규칙: `avm-kr-seoul-apt-v{major}-{yyyymmdd}-{git_short_sha}`
- 예: `avm-kr-seoul-apt-v2-20260315-a3f8c2`
- Registry table (`avm_models`):
  - `model_id` (PK)
  - `country_code`
  - `region_scope`
  - `property_type`
  - `version`
  - `trained_at`
  - `training_data_range`
  - `feature_config_json`
  - `metrics_json`
  - `artifact_uri`
  - `is_active`

Attestation 발행 시 `model_id`를 attestation record와 온체인에 기록.

---

## 9. Retraining Cadence

- 정기: 월 1회 (매월 첫째 주 일요일)
- 트리거 기반:
  - 실시간 MdAPE (30일 rolling) > 목표치 × 1.5
  - 시장 지수 급변 (월 5% 이상)
- 이전 모델과 shadow test 후 promotion

---

## 10. Deliverables (M3-M4)

- [ ] Feature engineering 라이브러리 (`packages/avm/features/`)
- [ ] Baseline v0 결과 리포트
- [ ] Hedonic v1 결과 리포트
- [ ] LightGBM v2 학습·백테스트 완료
- [ ] Repeat-sales index v3 구현
- [ ] Confidence scorer v4 구현
- [ ] Model registry table + migration
- [ ] Batch prediction script
- [ ] Online prediction API endpoint
- [ ] 세그먼트별 성능 대시보드 (Jupyter → HTML export)
