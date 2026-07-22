# Valis Protocol — Claude Code Guide

On-chain real estate valuation infrastructure. Seoul apartment AVM MVP → Sui testnet attestations → UAE expansion.

## Read first (in order)
1. [PRD.md](PRD.md) — vision, success criteria (MdAPE ≤ 7%/5%), milestones M1–M6
2. [docs/01-data-schema.md](docs/01-data-schema.md) — normalized international schema
3. [docs/02-korea-adapter.md](docs/02-korea-adapter.md) — MOLIT/공시가격/세움터 sources
4. [docs/03-avm-model.md](docs/03-avm-model.md) — v0→v4 model roadmap
5. [docs/04-backtest-methodology.md](docs/04-backtest-methodology.md) — temporal split rules
6. [docs/05-sui-contracts.md](docs/05-sui-contracts.md) — Move contract design
7. [docs/06-uae-expansion.md](docs/06-uae-expansion.md) — pre-emptive UAE design

## Non-negotiable rules
- **Never break temporal split** — no random splits, no holdout leakage, rolling features exclude current/future transactions
- **Never mutate raw ingestion snapshots** — append new versions
- **Never change `local_id_canonical` rules** — global_id (= sha256) links to on-chain attestations
- Country-agnostic core (`packages/core`); country-specific logic in adapters only
- Money: USD cents (int) + original amount + FX rate; area: sqm; coords: WGS84
- Cancelled trades (`cdealType == "O"`): store with `is_cancelled=true`, filter at analysis
- Conventional Commits; CI green before merge; no AI tool traces in commit messages (public repo)

## Layout
```
packages/core         # schemas.py (pydantic), ids.py, money.py, adapter.py (ABC), db/
packages/adapter_kr   # molit/ (client, xml_parser, normalizer), geo/ — NOTE: underscore, not adapter-kr
packages/avm          # features/, models/ (v0_median, v1_hedonic, v2_lightgbm), confidence.py, backtest/
packages/api          # FastAPI: main.py, routes/ (health, valuation, properties, attestations)
packages/attestation  # issuer.py (pysui wrapper)
packages/move/valis   # Sui Move: country_adapter, property_registry, attestation, oracle_feed, errors
scripts/              # ingest_molit, train_avm, run_backtest, seed_*, smoke_molit, issue_attestations
migrations/           # Alembic; 0001 creates all tables + PostGIS geometry
tests/                # pytest; fixtures/molit/*.xml are the parser contract
```

## Commands
```bash
docker compose up -d               # Postgres+PostGIS (5432), MinIO (9000)
pip install -e ".[dev]"
alembic upgrade head
python -m pytest tests/ -q         # unit tests (no DB needed)
ruff check packages scripts tests migrations && ruff format --check .
mypy packages/core packages/avm    # strict
python scripts/ingest_molit.py --region seoul --from 2020-01 --to 2024-12
cd packages/move/valis && sui move build && sui move test
```

## Design decisions made during implementation (deltas from docs)
- Package dirs use underscores (`adapter_kr`) for Python importability; imports are `packages.core.*` style with a single root `pyproject.toml`
- Move contracts: `i64` in docs/05 doesn't exist in Move → lat/lng are offset-encoded u64 (`(deg+90)*1e7`, `(deg+180)*1e7`); doc's undefined `attestation_helper` replaced by public accessors on `valis::attestation`; adapter deactivation enforced via registry lookup (owned caps can't be mutated by admin)
- Adapter cap "active" check = registry contains (country → this cap's ID); `property_registry::register` takes `&AdapterRegistry`
- ORM keeps lat/lng as Numeric; PostGIS `geom` columns + GIST indexes are migration-managed (keeps geoalchemy2 out of import path)
- `source_record_id` idempotency key = `{canonical}@{yyyymmdd}#{amount}` — re-ingestion upserts cancellation/registration fields
- FX: `FxProvider` (packages/core/fx.py) falls back ≤7 days to the prior business day, never forward; `ingest_molit` loads it from fx_rates and stores KRW-only (`price_usd_cents` NULL) when rates are missing
- KoreaAdapter's `fetch_property`/`fetch_government_valuation` intentionally raise NotImplementedError — unit-level PNU matching needs the property master, so use `fetch_building_register`/`fetch_official_prices` + the ingestion layer

## Current state (M1 code complete, data pending)
Done: core schemas+DB, MOLIT adapter, FX (BOK ECOS client + provider, wired into ingest), 공시가격 client+normalizer (PNU parsing), 세움터 client+normalizer (property enrichment), AVM v0/v1/v2 + confidence scorer, backtest framework, FastAPI service, Move contracts, Alembic migration, 76 passing tests.
Next (M1 exit — needs API keys + Docker): fill `.env`, `docker compose up -d`, `alembic upgrade head`, `python scripts/ingest_fx.py`, `python scripts/ingest_molit.py --region seoul --from 2020-01 --to 2024-12`, POI seeding; then M2 backtest on real data. Kongsi/seum bulk-ingestion scripts (PNU cross-matching) still to write.
