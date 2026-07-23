# 08 — Dubai Market + Sukuk Issuance Demo

**Purpose:** client-facing demo — Dubai listings first, Korea hidden (reversible),
full chain: DLD data → AVM → attestation → collateral gate → sukuk certificates.
**Status:** live on testnet. Phase 2 (docs/06) pulled forward as a pilot.

---

## 1. Data

| Item | Value |
|---|---|
| Source | DLD open transactions (Dubai Pulse mirror parquet, 1.28M rows) |
| Residential unit sales ingested | 569,551 tx / 128,910 unit classes / 3,296 buildings |
| Coverage | 2003-06 → **2024-08-22** (mirror snapshot end = value vintage) |
| Off-plan | `Sell - Pre registration` stored with `is_offplan=true`, excluded from analysis |
| Money | AED → USD via central-bank peg 3.6725 (fixed since 1997-11) |
| Live top-up | `packages/adapter_ae/dld/client.py` targets the DLD gateway API (reverse-engineered; gateway intermittently down as of 2026-07 — retry when recovered) |

DLD portal CSVs are free and keyless (dubailand.gov.ae → Open Data). Full
history mirror: `huggingface.co/datasets/viewit-ai/full-dubai-pulse`.

## 2. Identity — unit class (canonical rule, NEVER change)

```
AE-DXB-{AREA_SLUG}-{BUILDING_SLUG}-{BR_CODE}-{bua_sqm×100}
e.g. AE-DXB-BURJ-KHALIFA-BURJ-VISTA-1-2BR-11055
```

DLD open data publishes **no unit numbers** (privacy), so the finest
deterministic identity is the *unit class*: building × bedrooms × built-up
area. `slugify` (NFKD→ASCII→[A-Z0-9] runs joined by `-`) and `BEDROOM_CODES`
(`Studio→0BR`, `N B/R→NBR`, `PENTHOUSE→PH`, `Single Room→SR`, unknown→`X`)
are part of the rule. If a richer source appears later, it gets a NEW rule
version — this one never mutates (same principle as KR).

Dedup note: with no tx id, `source_record_id = {canonical}@{yyyymmdd}#{amount}`
collapses identical same-class/day/price sales — accepted, documented.

## 3. AVM (demo-grade, v1)

`scripts/train_avm_ae.py` — v3 lessons applied:
- City-wide monthly median-ppsqm index, 3-mo rolling, applied with **1-month
  lag** (valuing in month m uses data through m−1 — no leakage)
- Detrend BEFORE feature engineering; train-window-only target encodings
- LightGBM on detrended log price; split train ≤2023-06 / val 2023-07..12 /
  holdout 2024-01..08
- Conformal 95% CIs from val residuals, per-area segments
- Candidates: latest holdout tx per class + confidence (complex liquidity,
  segment rel_std/ppe10)

## 4. Demo mode (Korea hidden, reversibly)

- **Web**: `DEMO_MARKET=AE` env on `valis-web` → `app/dubai-demo.tsx` renders
  instead of the Korea page (which stays intact in the repo). Remove the env
  var to restore Korea. English copy; "Valuation Estimate" terminology
  (docs/06 §2.3 — never "appraisal" in Dubai).
- **API**: `/v1/stats?country=AE`, `/v1/attestations?country=AE` — no-param
  behavior unchanged (all markets).
- Optional web extras: `NEXT_PUBLIC_SUKUK_PACKAGE_ID`, `NEXT_PUBLIC_SUKUK_SPV_ID`.

## 5. On-chain objects (testnet)

| Object | ID |
|---|---|
| AE CountryAdapterCap | `0x16700830bb902c96f8833a73e40ab6c278d705253f2f8934169a45b3993e337c` |
| sukuk_demo package | `0x286459135e4a1fb6b2f6aae6b2b5b34e202c5766115545d50e92a470117a9fcf` |
| Demo SukukSPV (shared) | `0xb1892c02538523fc50e6291b5910513c51ad57bd899fda53b53953d3a475f7e5` |
| Valis package (v3) / feed | see docs/07 §4 |

### 5.1 AVM result → pilot parameters (honest tiering)

Hybrid model `avm-ae-dubai-apt-v1-20260723-926e876`:
- Hedonic (all classes): holdout MdAPE 15.8% — illiquid fallback, NOT attested
- **Comp track** (same-class trailing median × city index, n≥5/730d), holdout:
  T04 (comp_std≤0.04) **MdAPE 5.1% / PPE10 76.4%**, T06 6.2%/71.9%,
  T08 6.9%/66.7%; CI-95 coverage **94.3%** ✅

Unit-class identity (no unit numbers/floors in DLD open data) caps confidence
at **0.74 = REVIEW tier** — honestly computed, not overridden. The demo
therefore uses **pilot scholar parameters**: `min_confidence 7000 bps`,
`LTV 5000 bps` (vs KR 8500/6000), i.e. lower confidence is compensated by a
deeper LTV cut on top of the confidence haircut. Anything below 70% is still
refused. Production AUTO_ISSUE in Dubai requires unit-level data (DLD
partnership — docs/06 §6).

### 5.2 Live demo transactions (2026-07-23)

4 attestations issued (TOPAZ AVENUE, HAMILTON RESIDENCY, SOBHA CREEK VISTAS A,
ORCHID RESIDENCE; 0.065 SUI). Sukuk flow against TOPAZ AVENUE 2BR-14545
(estimate $392,595, confidence 73.87%):

| Scenario | Result | Tx |
|---|---|---|
| create_spv, target $140M (over limit) | ❌ abort `E_OVER_ISSUANCE` | `v4eEkxA3khrXbt5opmQSst47vHrrAypC4Qxh8FqaYLp` |
| create_spv, target $140,000 ≤ max $145,005 | ✅ `CollateralChecked` + `SpvCreated` | `C47q4b1EE9AaENiiV4m6kvhQVkXZm6XmQWhsxwPKWJge` |
| subscribe $50,000 | ✅ certificate serial 1 | `Ge3TvDZxwxXtxkiptxW448JX4NiDwrm8xRz5isHTDh8a` |
| subscribe $90,000 (raise = target) | ✅ certificate serial 2 | `GeTraLpzjoU8MSSXGZq7ycrwWqiga12pcBZxznagYTT` |
| subscribe $9.999M after sell-out | ❌ abort `E_SOLD_OUT` | `HmRBxtPLhX7Uvt9ADdbB9M9PyJYfrzK19cTiPDf86dVX` |

Chain math visible in `CollateralChecked`: $392,595 × 0.7387 = haircut
$290,010 → × 50% LTV = **max issuance $145,005**.

`sukuk_demo::spv` — minimal ijarah SPV consuming the Valis gate:
`create_spv` aborts unless target_raise ≤ LTV-bounded max issuance from
`collateral::check_and_log`; every `subscribe` re-checks the gate, so a stale
or degraded valuation halts issuance automatically. SukukCertificate objects
carry spv_id / asset global_id / face value / serial.

## 6. Demo runbook

```bash
set PYTHONPATH=.
python scripts/ingest_dld.py --parquet data/raw/ae/dld_transactions_mirror.parquet
python scripts/train_avm_ae.py                      # prints MODEL_ID
python scripts/issue_attestations_ae.py --model-id <MODEL_ID> --limit 5
# sukuk: create_spv + subscribe via sui client call (see docs/07 §3 arg shapes)
# web: railway variables --set DEMO_MARKET=AE --service valis-web && redeploy
```

## 7. Honest limits (say these to the client)

1. Mirror vintage 2024-08 — estimates are "as of data end"; live top-up
   pending DLD gateway recovery. Freshness gate (90d) applies to attestation
   issuance time, not data vintage — production requires current data.
2. Unit-class identity ≠ legal unit; title/physical checks stay off-chain.
3. Demo AVM is v1 — Phase 2 target MdAPE ≤8% needs the full model roadmap.
4. Not RERA appraisals — "Valuation Estimate" only.
