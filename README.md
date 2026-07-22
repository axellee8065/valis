# Valis Protocol

**On-chain real estate valuation infrastructure — the trust layer for every RWA property protocol.**

- On-chain: Sui (Move)
- Backend: Python 3.11, FastAPI, PostgreSQL 16 (+ PostGIS)
- ML: LightGBM
- Deploy: Railway
- CI/CD: GitHub Actions

---

## For Claude Code — Quick Orientation

Read documents in this order before touching any code:

1. **[PRD.md](PRD.md)** — Product vision, success criteria, milestones, principles
2. **[docs/01-data-schema.md](docs/01-data-schema.md)** — International normalized schema
3. **[docs/02-korea-adapter.md](docs/02-korea-adapter.md)** — Korea data sources & normalization
4. **[docs/03-avm-model.md](docs/03-avm-model.md)** — AVM feature catalog & model roadmap
5. **[docs/04-backtest-methodology.md](docs/04-backtest-methodology.md)** — Backtest rules & report template
6. **[docs/05-sui-contracts.md](docs/05-sui-contracts.md)** — Move contract skeleton
7. **[docs/06-uae-expansion.md](docs/06-uae-expansion.md)** — Pre-emptive design for UAE

**Non-negotiable principles when coding:**
- Never break temporal split in backtests
- Never mutate raw ingestion snapshots
- Every commit uses Conventional Commits
- CI must pass before merge; failed commits get reverted
- Country-agnostic core; country-specific in adapters only
- USD cents (int) for money; sqm for area; WGS84 for coordinates

---

## Repository Layout

```
valis/
├── PRD.md                           # Master PRD
├── docs/                            # Design docs (read these first)
├── packages/
│   ├── core/                        # Shared schemas, types, utils
│   ├── adapter-kr/                  # Korea data adapter
│   ├── adapter-ae/                  # UAE data adapter (Phase 2)
│   ├── avm/                         # Automated Valuation Model
│   ├── attestation/                 # On-chain attestation issuer
│   ├── api/                         # FastAPI service
│   └── move/                        # Sui Move contracts
├── scripts/                         # CLI entry points
├── migrations/                      # Alembic DB migrations
├── tests/
├── .github/workflows/               # CI + Railway deploy
├── railway.json
├── pyproject.toml
└── docker-compose.yml               # Local dev stack
```

---

## Local Development

```bash
# Prereqs: Python 3.11, Docker, Sui CLI

# 1. Setup env
cp .env.example .env
# fill in API keys

# 2. Start local Postgres + PostGIS
docker compose up -d

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Run migrations
alembic upgrade head

# 5. Seed initial data
python scripts/seed_seoul_legal_codes.py
python scripts/seed_seoul_pois.py

# 6. Backfill historical MOLIT data (~15 minutes)
python scripts/ingest_molit.py --region seoul --from 2020-01 --to 2024-12

# 7. Train AVM
python scripts/train_avm.py --model v1

# 8. Run backtest
python scripts/run_backtest.py --model-id avm-kr-seoul-apt-v1-...

# 9. Serve API
uvicorn packages.api.main:app --reload

# 10. Deploy Move contracts (Sui testnet)
cd packages/move/valis
sui move build
sui client publish --gas-budget 100000000
```

---

## Deployment (Railway)

- `main` branch → production
- `staging` branch → staging
- Services:
  - `valis-api` (FastAPI, autoscaled)
  - `valis-ingest` (scheduler)
  - `valis-db` (Postgres, managed)
- Secrets managed in Railway dashboard
- Migrations run automatically on deploy

Deploy trigger:
```bash
git push origin main
```

GitHub Actions runs `ci.yml` (lint + test + move test) then `deploy-railway.yml` on green.

---

## Milestones

| Month | Milestone | Exit Criteria |
|---|---|---|
| M1 | Foundation, KR ingestion | Seoul apt 5yr data ingested |
| M2 | AVM v0-v1 | v1 backtest report auto-generated |
| M3 | AVM v2 | MdAPE ≤ 7% |
| M4 | AVM v3-v4 + confidence | MdAPE ≤ 5%, CI provided |
| M5 | On-chain integration | 10k attestations on Sui testnet |
| M6 | Whitepaper + UAE prep | Public backtest report + UAE roadmap |

---

## License

TBD — planned Apache-2.0 for backend / MIT for Move
