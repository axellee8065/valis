# Valis Protocol — Backtest Report v1 (Draft)

**On-chain real estate valuation infrastructure — Seoul apartment AVM**

Version 0.1 (draft) · 2026-07-23
Model: `avm-kr-seoul-apt-v3-20260723-14cf632` · Network: Sui Testnet

---

## Executive Summary

Valis publishes verifiable, continuously-updated apartment valuations on-chain.
This report documents the first full cycle: 352,523 government-registered Seoul
transactions (2020-01 – 2026-07) → an automated valuation model with strict
temporal validation → conformal 95% confidence intervals → attestations
consumable by any Sui protocol through a shared oracle feed.

**Headline results (sealed 12-month holdout, 2025-07 – 2026-06, n=69,301):**

| Metric | All predictions | AUTO_ISSUE tier (21.5%) | Target |
|---|---|---|---|
| MdAPE | 7.3% | **5.4%** | ≤ 7% (min) / ≤ 5% (stretch) |
| PPE10 | 63.9% | **78.9%** | ≥ 75% |
| PPE20 | 90%+ | — | ≥ 90% |
| 95% CI coverage | 91.3% | **93.0%** | 93–97% |
| Coverage (predictions made) | 100% | — | ≥ 85% |

The protocol only auto-issues attestations in the highest-confidence tier;
lower tiers are flagged for review or refused. All numbers above are
holdout-only — the holdout window was never touched during feature
engineering, model selection, or calibration.

**On-chain proof (Sui Testnet):**
- Package: `0x71fa1119d5cfdf3bf2faf8419c89ef3361f3d2ae35ac02e765f3e6aec37b4d74`
- Shared ValuationFeed: `0xe76f7031e20c49971819158dc7ccf4086353533be32af950b15ad0e2db6e3454`
- First attestation: 도봉구 아파트 59.25㎡ — predicted $409,191 vs. actual
  contract 3.9% apart; attestation `0x458cea53...b0f0` carries the value,
  95% CI, confidence score, model ID, and a sha256 anchor of this report.

---

## 1. Introduction

Real-world-asset (RWA) protocols tokenize property but import its valuation
from off-chain PDFs and stale appraisals. Valis is a valuation *infrastructure*
layer: government transaction data in, verifiable valuation attestations out —
versioned models, honest confidence, expiring attestations, one shared feed
any partner protocol can read.

Positioning note: Valis attestations are **valuation estimates / reference
values**, not statutory appraisals. The protocol is a tool for appraisers and
protocols, not a replacement for licensed appraisal (감정평가).

## 2. Data

| Item | Value |
|---|---|
| Source | MOLIT 실거래가 (Korean Ministry of Land — statutory transaction registry) |
| Window | 2020-01 – 2026-07 (79 months) |
| Scope | All 25 Seoul districts, apartments (아파트) |
| Transactions | 352,523 (359,924 fetched, re-report duplicates deduplicated) |
| Unique units | 242,400 |
| Complexes | 8,533 (MOLIT aptSeq identity) |
| Cancelled flagged | 15,990 (4.5%) — stored, excluded from training |
| Related-party flagged | 11,174 (직거래, 3.2%) — excluded from training |
| USD normalization | 99.98% (daily BOK KRW/USD rates, 1,614 trading days) |

Every record stores the normalized value **and** the raw payload; raw
snapshots are never mutated. Yearly volumes track the actual market cycle
(2020 boom 82k → 2022 crunch 12k → 2025 recovery 82k), a strong sanity check
against silent ingestion bias.

## 3. Methodology

### 3.1 Temporal discipline (non-negotiable)
- Train 2020-01–2024-06 · validation 2024-07–2025-06 · holdout 2025-07–2026-06
- Random splits forbidden; holdout used exactly once, for this report
- All rolling features exclude the current and any future transaction

### 3.2 Model evolution (measured, not assumed)

| Version | Method | Holdout MdAPE | Holdout bias |
|---|---|---|---|
| v2 | LightGBM, log-price, native categoricals | 7.22% | -4.4%, worsening -2.6→-5.8% by quarter |
| v3 | v2 + repeat-sales index detrending | 7.32% | **-2.2%**, quarters 1–3 ≈ 0 |

v2's drift is structural: gradient-boosted trees cannot extrapolate beyond the
training price range, so predictions anchor to the training-era market level.
v3 removes this by detrending **both the target and the comparable-price
features** with a Bailey-Muth-Nourse repeat-sales index (73k+ sale pairs),
estimated *expandingly* (index at month m uses only pairs closing ≤ m) and
*per region* (강남3구 vs. others — a citywide index left -8.6% bias in premium
districts; regional indices cut it to -0.7%).

A negative result we report honestly: detrending only the target while leaving
nominal comparable features intact **double-counts** the market level (+5%
bias). The ordering — detrend first, engineer features second — matters.

### 3.3 Confidence and intervals
- **Conformal prediction** on validation residuals per district — 95% CI with
  distribution-free guarantees
- **Adaptive calibration**: rolling 6-month residual window (1-month embargo)
  + ACI online α adjustment (Gibbs & Candès). Static validation-only
  calibration under-covered badly (84.6%) as the error regime shifted —
  adaptive calibration restored AUTO_ISSUE coverage to 93.0%
- **Confidence score** = liquidity + freshness + model certainty + segment
  accuracy → three tiers: AUTO_ISSUE (≥0.85) / REVIEW (0.60–0.85) / REFUSE

## 4. Results

### 4.1 Tier performance (holdout)

| Tier | Share | MdAPE | PPE10 | CI-95 |
|---|---|---|---|---|
| AUTO_ISSUE | 21.5% | 5.4% | 78.9% | 93.0% |
| REVIEW_RECOMMENDED | 60.8% | 8.0% | 60.1% | 91.7% |
| REFUSE | 17.7% | 8.4% | 58.9% | — |

The confidence score is decision-grade: refused cases are measurably the worst,
and the auto-issue tier meets every protocol target.

### 4.2 Segment robustness
Full per-district, price-band, size, age, and complex-size tables are in the
appendix (`summary.json`). Regional index adjustment closed the premium-district
gap: 강남3구 MdAPE 10.9% → 7.7%, bias -8.6% → -0.7%.

## 5. Failure Analysis & Limitations

1. **Repeat-sales index end-point lag** — the newest quarter (2026Q2) retains
   -6% bias: too few closed pairs identify the most recent months, a known
   limitation shared by Case-Shiller-style indices (which revise endpoints).
   Mitigations under evaluation: regularized RS estimation, revision-aware
   backtesting. Confidence tiering already routes part of this risk to REVIEW.
2. **No geocoding yet** — subway/school distance features are seeded but not
   joined; property coordinates land in M6.
3. **Single building-type, single city** — Seoul apartments only by design
   (docs/06 covers the UAE expansion path).
4. **CI width** (median ~30%) is wider than the 20% aspiration; tightening
   without sacrificing coverage is v5 work.

## 6. On-chain Architecture (Sui)

- `country_adapter` — capability-gated adapters per country; revocation via
  registry lookup (an owned cap cannot be silently reused after removal)
- `property_registry` — deterministic identity: `global_id = sha256(country:canonical_id)`;
  duplicate registration impossible (shared index)
- `attestation` — value, 95% CI, confidence (bps), method, model ID, report
  sha256, expiry; revocable by issuer capability
- `oracle_feed` — shared object holding the latest attestation per property;
  partners read without holding the attestation
- `batch::register_and_attest` — register + mint + feed-publish in one
  programmable transaction (batch issuance at scale)

## 7. Reproducibility

- Deterministic model IDs: `avm-kr-seoul-apt-v3-{date}-{git_sha}`
- Every backtest emits `manifest.json`: data checksum, split boundaries, seed
  (42), library versions; predictions parquet retained for audit
- Attestations anchor the report hash on-chain: `sha256(report.md)` =
  `7cfe210430519478b6705382603cdaf16420205b6c22c6ea868aa94f0b0cbc9a`
- Full pipeline reruns from public APIs: MOLIT + BOK ECOS + VWorld (keys free)

## 8. Roadmap

- v5: index end-point correction, geospatial features, CI tightening
- KB시세 cross-validation + licensed-appraiser dual-check (100 properties)
- Dubai adapter (DLD open data) — schema and registry already country-agnostic
- Mainnet after external review of contracts and methodology

---

*Draft — numbers final for the cited model; prose and appendices in progress.
Contact: Valis Protocol.*
