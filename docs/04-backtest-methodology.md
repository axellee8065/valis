# 04 — Backtest Methodology & Report Template

**Package:** `packages/avm/backtest`
**Deliverable:** 공개 가능한 백테스트 백서 (Markdown + PDF)

---

## 1. 절대 원칙 (Non-negotiable)

1. **Temporal split only** — 랜덤 스플릿 금지
2. **홀드아웃은 학습에 절대 노출 금지** — feature engineering, hyperparameter tuning, model selection 어디에도
3. **Look-ahead bias 방지** — 학습 시점 이후 정보 사용 불가 (rolling feature 계산 시점 엄격)
4. **모든 지표는 세그먼트별 리포트** — 전체 평균 뒤에 편차 숨기지 않음
5. **재현 가능성** — 데이터 스냅샷 hash + 모델 seed + 코드 커밋 SHA를 리포트에 명시

---

## 2. Data Split

### 2.1 3-way Temporal Split

```
[Training]      2020-01-01 ~ 2024-06-30   (54 months)
[Validation]    2024-07-01 ~ 2025-06-30   (12 months)
[Holdout]       2025-07-01 ~ 2026-06-30   (12 months)
```

- Training: 모델 학습
- Validation: hyperparameter tuning, model selection, early stopping
- Holdout: **최종 리포트 지표만 산출**. 이 데이터로 튜닝 절대 금지

### 2.2 Walk-forward Extension (v3-v4)

시계열 모델 검증 강화를 위해:
- 6개월 단위로 학습·평가 창을 이동시키며 반복 백테스트
- 최근 시장 변동 대응 능력 평가

### 2.3 Cold-start Scenarios (별도 리포트)

- **신축 단지**: 첫 거래 시점 예측 (같은 단지 참조 불가)
- **저유동성 지역**: 90일 내 거래 없는 물건

---

## 3. Evaluation Metrics

### 3.1 Primary metrics

| Metric | Formula | 목표 |
|---|---|---|
| **MdAPE** | `median(|pred - actual| / actual)` | ≤ 5% |
| **MAPE** | `mean(|pred - actual| / actual)` | ≤ 8% |
| **PPE10** | `% within ±10%` | ≥ 85% |
| **PPE20** | `% within ±20%` | ≥ 95% |
| **RMSE (log-price)** | `sqrt(mean((log(pred) - log(actual))^2))` | reference |
| **Coverage** | `% of transactions where model predicted` | ≥ 90% |

### 3.2 Bias metrics

| Metric | Formula | 목표 |
|---|---|---|
| **Median relative error** | `median((pred - actual) / actual)` | |0| ≤ 1% |
| **Skew** | 예측 오차 분포의 skewness | reference |

편향이 크면 특정 방향으로 계속 틀린다는 뜻. 절대값보다 방향성이 문제.

### 3.3 Confidence interval metrics

| Metric | Formula | 목표 |
|---|---|---|
| **Coverage-95** | `% of actual within predicted CI` | 93–97% |
| **Interval width (median)** | `median(CI_upper - CI_lower) / prediction` | ≤ 20% |

Coverage-95는 정확히 95%에 수렴해야 CI가 정직. 낮으면 과확신, 높으면 과보수.

### 3.4 Operational metrics

| Metric | 목표 |
|---|---|
| 평균 예측 latency | < 200ms |
| 배치 처리량 (건/시간) | ≥ 100,000 |
| 학습 시간 (v2 full training) | ≤ 30분 |

---

## 4. Segment-level Reporting

### 4.1 필수 세그먼트

리포트는 다음 축을 **각각 별도로** 표시. 축 간 조합(교차)은 부록으로:

- 자치구 (25개)
- 가격대 (5개 bucket)
- 면적대 (4개 bucket)
- 연식 (4개 bucket)
- 단지 규모 (3개 bucket)
- 거래 시점 quarter (홀드아웃 4개 분기)

### 4.2 표 형식 예시

| 자치구 | N | Coverage | MdAPE | PPE10 | PPE20 | Bias |
|---|---|---|---|---|---|---|
| 강남구 | 12,340 | 94.2% | 3.8% | 89.1% | 97.3% | +0.5% |
| 서초구 | 8,910 | 93.7% | 4.1% | 87.6% | 96.8% | +0.2% |
| ... | | | | | | |

---

## 5. Comparison Baselines

우리 모델만 봐서는 신뢰 못 얻음. 반드시 baseline과 비교:

| Baseline | 설명 |
|---|---|
| **B1: 공시가격 × 시장 배율** | 공시가격에 지역별 실거래/공시 비율 곱 |
| **B2: 최근 동일단지 median** | v0 모델 |
| **B3: KB시세** (가능한 경우) | 파트너십·크롤링으로 확보 시 |
| **B4: 부동산원 시세** | R-ONE 지역 지수 기반 추정 |

우리 v2/v3/v4가 baseline 대비 얼마나 개선되는지 표로.

---

## 6. Backtest Code Structure

```
packages/avm/backtest/
├── __init__.py
├── splits.py               # temporal split logic
├── metrics.py              # MdAPE, PPE10, coverage 등
├── segmentation.py         # 세그먼트 정의·계산
├── baselines.py            # B1–B4 구현
├── runner.py               # end-to-end 백테스트 실행
├── report_generator.py     # 결과 → Markdown/HTML/PDF
└── plots.py                # 시각화 (matplotlib/plotly)

scripts/run_backtest.py     # CLI entry point
```

### 6.1 CLI

```bash
python scripts/run_backtest.py \
  --model-id avm-kr-seoul-apt-v3-20260315-a3f8c2 \
  --split-config configs/split_holdout_2025h2.yaml \
  --output-dir reports/backtest_v3_20260315/ \
  --include-baselines B1,B2,B4
```

### 6.2 Output artifacts

```
reports/backtest_v3_20260315/
├── report.md                       # 백서 본문
├── report.pdf                      # PDF export
├── summary.json                    # 지표 원본
├── predictions.parquet             # 전 홀드아웃 예측 (감사용)
├── plots/
│   ├── error_distribution.png
│   ├── pred_vs_actual.png
│   ├── ppe10_by_district.png
│   ├── mdape_over_time.png
│   ├── ci_coverage.png
│   └── segment_heatmap.png
└── manifest.json                   # 재현 정보
```

`manifest.json`:
```json
{
  "backtest_id": "bt-20260315-a3f8c2",
  "run_at": "2026-03-15T02:15:00Z",
  "model_id": "avm-kr-seoul-apt-v3-20260315-a3f8c2",
  "code_git_sha": "a3f8c2d...",
  "data_snapshot": {
    "database": "valis-prod",
    "as_of": "2026-03-14T00:00:00Z",
    "transaction_count": 342100,
    "checksum": "sha256:..."
  },
  "split_config_hash": "...",
  "python_env": {
    "python": "3.11.7",
    "lightgbm": "4.3.0",
    "pandas": "2.2.0"
  }
}
```

---

## 7. Public Whitepaper Template

`reports/whitepaper_v1.md` 구조:

```markdown
# Valis Protocol Backtest Report v1
## Executive Summary
- 한 페이지 요약: 목표, 결과, 시사점

## 1. Introduction
- 왜 온체인 부동산 감정 인프라인가
- 프로토콜 개요 (1페이지)

## 2. Data
- 데이터 소스 (MOLIT 실거래가 등)
- 정규화 프로세스
- 데이터 통계 (총 거래건수, 기간, 지역 분포)
- Cancellation·related-party 처리

## 3. Methodology
- Temporal split 원칙
- Feature engineering 요약
- Model architecture (v1/v2/v3/v4)
- 세그먼트 정의

## 4. Results
### 4.1 Overall performance
- 헤드라인 지표 표
- Baseline 비교
### 4.2 Segment performance
- 자치구별
- 가격대별
- 연식별
- 단지 규모별
### 4.3 Temporal robustness
- Walk-forward 결과
- 시장 변동 시기 성능
### 4.4 Confidence intervals
- Coverage-95
- CI width 분포

## 5. Failure Analysis
- 예측 오차 상위 5% 케이스 분석
- 실패 유형 분류

## 6. Comparison with Prior Art
- Zillow Zestimate (US)
- Redfin Estimate
- 국내 KB시세·부동산원
- 학술 논문 (hedonic model 국내 연구 등)

## 7. Limitations
- 커버리지 한계
- 시장 급변 시 대응
- 이상 거래 필터의 한계

## 8. Roadmap
- v5 이후 개선 방향
- 다국가 확장

## Appendix
- 상세 metric 표
- Reproducibility manifest
- 데이터 스키마
- 코드 저장소 링크
```

---

## 8. Validation Against Real Market

백테스트만으론 부족. 다음 외부 검증 필수:

### 8.1 KB시세 대조
- 우리 예측 vs 같은 물건 KB 시세
- KB시세와 실거래가 편차를 baseline으로 삼아 상대 성능 비교

### 8.2 Real appraiser dual-check
- 파트너 감정법인 1–2곳에 물건 100건 감정 요청
- 우리 AVM 예측과 편차 분석
- MVP 후반부 (M6)에 실시

### 8.3 시장 지수 정합성
- 우리 예측의 월별 평균 변화율 vs 부동산원/KB 지수
- 시스템 편향 감지용

---

## 9. Publication Strategy

백서 공개는 프로토콜 신뢰의 시작. 원칙:

- **GitHub public repo에 원본 데이터·모델·백테스트 코드 포함**
- 재현 가능한 형태로 배포 (`docker compose up` 한 방에 검증 실행)
- 리포트에는 실패 케이스도 정직하게 (은폐하면 발각 시 신뢰 붕괴)
- 이해충돌 없음을 명시 (특정 프로토콜 홍보 아님)
- 초기 배포 채널:
  - GitHub Releases
  - Twitter/X
  - Sui Foundation 커뮤니티
  - RWA 관련 뉴스레터 (RWA World, Ondo blog 등)
  - 한국어 버전 병기 (한국 부동산 커뮤니티 접근)

---

## 10. Deliverables Checklist (M6)

- [ ] Backtest runner 자동화
- [ ] 5개 baseline (B1–B4 + v0) 구현
- [ ] 세그먼트별 지표 자동 계산
- [ ] Report generator (Markdown → PDF)
- [ ] Plots 라이브러리
- [ ] 최종 v3/v4 모델 홀드아웃 백테스트 완료
- [ ] KB시세 대조 리포트 (파트너십 확보 시)
- [ ] 공개 백서 초안 (한글·영문)
- [ ] GitHub Release
- [ ] 재현성 검증 (외부인이 docker compose로 재현 가능)
