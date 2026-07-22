# Valis Protocol — PRD (Product Requirements Document)

**Version:** 0.1.0
**Status:** Draft for MVP Build
**Target:** Claude Code vibe coding execution
**Timeline:** 6 months to backtest report

---

## 1. Product Vision

**"온체인 부동산 감정 인프라 — 모든 RWA 부동산 프로토콜의 신뢰 레이어."**

### 1.1 One-liner

실거래·정부 데이터·AI AVM을 결합해 부동산 가치를 **검증 가능·지속 갱신·크로스체인 소비 가능한 형태**로 온체인에 게시하는 프로토콜.

### 1.2 Long-term Positioning

- **단기 (6M)**: 서울 아파트 AVM MVP + 백테스트 리포트 공개
- **중기 (12M)**: 두바이·아부다비 확장, 첫 파트너 프로토콜 확보
- **장기 (24M+)**: 다국가 부동산 감정 오라클 표준

### 1.3 Non-goals (MVP 단계에서 명시적으로 하지 않는 것)

- ❌ 서울 외 지역 (부산·인천 등)
- ❌ 아파트 외 물건 (단독·빌라·상업용)
- ❌ 감정사 네트워크 (Consensus Appraisal)
- ❌ 토큰 발행·거버넌스
- ❌ 프론트엔드 대시보드 (API + 리포트만)
- ❌ 마케팅 활동 (백테스트 결과 확보 전)

---

## 2. Success Criteria (Definition of Done)

MVP 성공은 **오직 백테스트 정량 지표로 판정**한다.

| 지표 | 최소 목표 | 도전 목표 |
|---|---|---|
| MdAPE (Median Absolute % Error) | ≤ 7% | ≤ 5% |
| PPE10 (% within 10%) | ≥ 75% | ≥ 85% |
| PPE20 (% within 20%) | ≥ 90% | ≥ 95% |
| Coverage (서울 아파트 커버리지) | ≥ 85% | ≥ 90% |
| 95% CI half-width | ≤ ±10% | ≤ ±8% |
| End-to-end 파이프라인 지연 | ≤ 24h | ≤ 6h |

**부수 산출물:**
1. 공개 가능한 백테스트 백서 (PDF + Markdown)
2. Sui Testnet에 배포된 attestation 컨트랙트
3. Railway에 배포된 API 서비스
4. GitHub 오픈 리포지토리 (커밋 히스토리 정돈)
5. 두바이 어댑터 개발 착수 상태

---

## 3. System Architecture

### 3.1 상위 컴포넌트

```
┌─────────────────────────────────────────────────────────┐
│                   Client / Partner APIs                  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              API Gateway (FastAPI, Railway)              │
│         Valuation · Property · Attestation endpoints     │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  Universal Valuation Engine              │
│     ModelRouter · ConfidenceScorer · Attestation Issuer  │
└─────────────────────────────────────────────────────────┘
              ↓                            ↓
┌──────────────────────┐     ┌──────────────────────────┐
│ Country-Agnostic     │     │  On-chain Layer (Sui)    │
│ Normalized Storage   │     │  PropertyRegistry        │
│ (Postgres + S3)      │     │  AppraisalAttestation    │
└──────────────────────┘     │  OracleFeed              │
              ↑              └──────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│                    Country Adapters                      │
│  🇰🇷 KR Adapter  |  🇦🇪 AE Adapter (Phase 2)             │
└─────────────────────────────────────────────────────────┘
              ↑
┌─────────────────────────────────────────────────────────┐
│                  External Data Sources                   │
│  MOLIT · KB · Court · MOIS · Seoul Open Data · ...       │
└─────────────────────────────────────────────────────────┘
```

### 3.2 기술 스택 (확정)

- **Language**: Python 3.11 (백엔드·ML), Move (온체인)
- **Backend**: FastAPI, SQLAlchemy 2.0, Alembic
- **DB**: PostgreSQL 16 (Railway managed) + PostGIS extension
- **ML**: pandas 2.x, scikit-learn, LightGBM, XGBoost
- **Data pipeline**: Prefect 2 (or plain APScheduler for MVP)
- **Storage**: Cloudflare R2 (or Railway volume) — raw dumps
- **On-chain**: Sui Move, Sui Testnet, Sui TypeScript SDK
- **CI/CD**: GitHub Actions → Railway
- **Monitoring**: Railway logs + Sentry
- **Docs**: MkDocs Material (or plain markdown)

### 3.3 저장소 구조 (Monorepo)

```
valis/
├── README.md
├── PRD.md                           # this file
├── docs/
│   ├── 01-data-schema.md            # 국제 데이터 스키마 스펙
│   ├── 02-korea-adapter.md          # 한국 어댑터 구현 계획
│   ├── 03-avm-model.md              # AVM 피처·모델 설계
│   ├── 04-backtest-methodology.md   # 백테스트 방법론
│   ├── 05-sui-contracts.md          # Move 컨트랙트 설계
│   ├── 06-uae-expansion.md          # 두바이·아부다비 확장 이슈
│   └── adr/                         # Architecture Decision Records
├── packages/
│   ├── core/                        # 공통 스키마·타입
│   ├── adapter-kr/                  # 한국 어댑터
│   ├── adapter-ae/                  # 두바이 어댑터 (Phase 2)
│   ├── avm/                         # AVM 모델
│   ├── attestation/                 # 온체인 발행 로직
│   ├── api/                         # FastAPI 서비스
│   └── move/                        # Sui Move 컨트랙트
├── scripts/
│   ├── ingest_molit.py
│   ├── train_avm.py
│   ├── run_backtest.py
│   └── issue_attestations.py
├── migrations/                      # Alembic
├── tests/
├── .github/workflows/
│   ├── ci.yml
│   └── deploy-railway.yml
├── railway.json
├── pyproject.toml
└── docker-compose.yml               # local dev
```

---

## 4. Development Principles (바이브코딩 원칙)

### 4.1 Git 커밋 원칙

- **Conventional Commits** 강제: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `perf:`
- **커밋 단위**: 하나의 논리적 변경 = 하나의 커밋
- **PR 없이 main에 직접 커밋 금지** (혼자여도 PR 열어서 셀프리뷰)
- **커밋 메시지에 Claude Code 흔적 남기지 않음** (외부 공개 리포이므로)
- **CI 실패한 커밋은 즉시 revert**

### 4.2 Railway 배포 원칙

- **main 브랜치 = production**
- **staging 브랜치 = staging 환경**
- **모든 환경변수는 Railway secret으로**, `.env`는 로컬에만
- **Railway service 분리**:
  - `valis-api` (FastAPI)
  - `valis-ingest` (스케줄러)
  - `valis-db` (Postgres, managed)
- **DB migration은 배포 파이프라인에서 자동 실행**
- **Health check endpoint 필수**: `/health`, `/ready`

### 4.3 코드 품질

- **Ruff**: linting + formatting
- **Mypy strict** on `packages/core`, `packages/avm`
- **Pytest coverage ≥ 70%** on core paths (adapter fetch·normalize, AVM predict, attestation issuer)
- **Move 컨트랙트는 100% 함수 커버리지 목표**

### 4.4 Claude Code 활용 규칙

- **작업 시작 전 반드시 관련 docs/*.md 참조 명시**
- **큰 작업은 sub-task로 분해**해서 순차 실행
- **테스트를 먼저** 짜고 구현 (특히 스키마·어댑터·AVM)
- **모델 학습·백테스트는 재현 가능하게** (seed 고정, 데이터 버전 명시)

---

## 5. Documentation Index

| 문서 | 내용 | 상태 |
|---|---|---|
| [docs/01-data-schema.md](docs/01-data-schema.md) | 국제 정규화 데이터 스키마 (RESO/INSPIRE 기반) | ✅ |
| [docs/02-korea-adapter.md](docs/02-korea-adapter.md) | 한국 데이터 소스별 어댑터 구현 계획 | ✅ |
| [docs/03-avm-model.md](docs/03-avm-model.md) | AVM 피처·모델·학습·서빙 | ✅ |
| [docs/04-backtest-methodology.md](docs/04-backtest-methodology.md) | 백테스트 방법론·리포트 템플릿 | ✅ |
| [docs/05-sui-contracts.md](docs/05-sui-contracts.md) | Move 컨트랙트 설계·배포 | ✅ |
| [docs/06-uae-expansion.md](docs/06-uae-expansion.md) | 두바이·아부다비 확장 이슈 리스트 | ✅ |

---

## 6. Milestones

### M1 (Weeks 1-4) — Foundation
- 저장소 셋업, Railway·GitHub 연결
- 국제 스키마 확정 및 core 패키지 구현
- 한국 어댑터 v1 (MOLIT 실거래가 + 공시가격)
- 서울 아파트 5년치 데이터 수집·정규화·저장
- **Exit criteria**: `python scripts/ingest_molit.py` 실행 시 정규화된 거래 데이터 DB 적재

### M2 (Weeks 5-8) — AVM v0-v1
- AVM baseline (동일 단지 최근 거래 중앙값)
- Hedonic Regression 모델
- 백테스트 프레임워크 (temporal split, 지표 자동 계산)
- **Exit criteria**: v1 백테스트 리포트 자동 생성, MdAPE 측정

### M3 (Weeks 9-12) — AVM v2
- 피처 엔지니어링 (지하철·학군·주변 시세)
- LightGBM 모델
- 세그먼트별 성능 분석
- **Exit criteria**: MdAPE ≤ 7%

### M4 (Weeks 13-16) — AVM v3 + Confidence
- 시계열 조정 (반복매매지수)
- 신뢰도 스코어 구현
- 이상치 감지 라우팅
- **Exit criteria**: MdAPE ≤ 5%, 신뢰구간 제공

### M5 (Weeks 17-20) — On-chain Integration
- Sui Move 모듈 구현·배포 (Testnet)
- Attestation 발급 파이프라인
- API 서비스 Railway 배포
- **Exit criteria**: 서울 아파트 10,000건 온체인 attestation

### M6 (Weeks 21-24) — Report + UAE Prep
- 백테스트 백서 작성 (공개 버전)
- KB 시세 대조 검증
- 두바이 DLD 데이터 조사, 어댑터 skeleton
- **Exit criteria**: 공개 가능한 백서, 두바이 확장 로드맵 확정

---

## 7. Risk Register

| 리스크 | 완화 |
|---|---|
| MOLIT API rate limit / 스펙 변경 | 로컬 캐시 우선, 스냅샷 저장, 변경 감지 alert |
| 실거래가 특유의 noise (허위·취소·특수관계) | 이상치 필터·중앙값 사용, 취소 거래 별도 추적 |
| 서울 데이터에 과적합 | 지역·시기 홀드아웃 엄격, 세그먼트별 리포팅 |
| Sui Testnet 리셋 | Attestation 재발급 스크립트 상시 유지 |
| 감정평가법인 협회 반발 | "감정사 대체" 아닌 "감정사 도구" 포지셔닝 견지 |
| 두바이 확장 시 API 접근 지연 | Month 6부터 병행 착수, 파트너십 접촉 조기 개시 |
