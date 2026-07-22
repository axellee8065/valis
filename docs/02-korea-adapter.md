# 02 — Korea Adapter Implementation Plan

**Package:** `packages/adapter-kr`
**Owner:** MVP core
**Target:** 서울 아파트 (Phase 1), 서울 전체 → 수도권 (Phase 2)

---

## 1. Adapter Contract (모든 국가 어댑터의 공통 인터페이스)

```python
from abc import ABC, abstractmethod
from datetime import date
from typing import AsyncIterator
from packages.core.schemas import Property, Transaction, GovernmentValuation


class CountryAdapter(ABC):
    country_code: str  # "KR", "AE", ...
    
    @abstractmethod
    async def fetch_transactions(
        self, 
        region_code: str, 
        year_month: str
    ) -> AsyncIterator[Transaction]:
        """Fetch normalized transactions for a region+month."""
    
    @abstractmethod
    async def fetch_property(self, local_id: str) -> Property:
        """Fetch a single property by local ID."""
    
    @abstractmethod
    async def fetch_government_valuation(
        self, local_id: str, year: int
    ) -> GovernmentValuation:
        """Fetch government-assessed value."""
    
    @abstractmethod
    def normalize_local_id(self, raw_id: str) -> str:
        """Canonicalize local ID for global_id generation."""
    
    @abstractmethod
    def normalize_address(self, raw_address: str) -> tuple[str, str]:
        """Returns (normalized_english, original)."""
    
    @abstractmethod
    async def verify_property_exists(self, local_id: str) -> bool:
        """Check via government registry."""
```

---

## 2. Data Sources (Prioritized)

### 2.1 Priority 0 — Must have

#### A. MOLIT 실거래가 공개시스템 (아파트 매매)

- **Endpoint**: `http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev`
- **인증**: 공공데이터포털 API key (무료 발급)
- **Rate limit**: 개발계정 초당 30건, 일 10,000건 / 운영계정 신청 시 확대
- **비용**: 무료
- **응답 형식**: XML (JSON 미지원, 파싱 필요)
- **주요 필드** (원본):
  - `sggCd`: 시군구코드 (5자리)
  - `umdCd`: 읍면동코드
  - `landCd`: 지번코드
  - `bonbun`, `bubun`: 본번·부번
  - `roadNm`: 도로명
  - `aptDong`: 동
  - `floor`: 층
  - `excluUseAr`: 전용면적(㎡)
  - `dealAmount`: 거래금액(만원, 쉼표 포함 문자열)
  - `dealYear`, `dealMonth`, `dealDay`
  - `aptNm`: 아파트명
  - `buildYear`: 건축년도
  - `cdealType`: 해제여부 ("O"이면 취소)
  - `cdealDay`: 해제사유발생일
  - `dealingGbn`: 거래유형 (직거래/중개거래)
  - `rgstDate`: 등기일자
  - `estateAgentSggNm`: 중개사 소재지

- **호출 파라미터**:
  - `LAWD_CD`: 5자리 법정동 코드 (필수)
  - `DEAL_YMD`: YYYYMM (필수)
  - `numOfRows`: 페이지당 (최대 1000)
  - `pageNo`
  - `serviceKey`: URL-encoded API key

- **주의사항**:
  - XML 파싱 시 numeric 필드가 문자열로 옴 (`"12,500"` 형태). 정수 변환 필수
  - `cdealType == "O"`인 레코드는 `is_cancelled = true`로 저장하되 **삭제하지 않음** (분석 시 필터)
  - `dealingGbn`이 "직거래"인 경우 `is_related_party` 후보로 flag
  - 같은 물건이 여러 번 등장할 수 있음 (재신고). 최신 `rgstDate` 기준으로 dedup
  - 응답에 `resultCode`가 `00`이 아니면 재시도

#### B. 부동산공시가격알리미 (공동주택 공시가격)

- **Endpoint**: `https://www.realtyprice.kr:447/notice/gsstandard/openApiInfo.htm`
- **인증**: 공공데이터포털 API key
- **Rate limit**: 초당 10건 (권장), 일 5,000건
- **비용**: 무료
- **응답 형식**: JSON
- **주요 필드**:
  - `sggNm`, `bjdongNm`: 시군구·읍면동
  - `bldNm`, `dongNm`, `hoNm`: 단지·동·호
  - `pnu`: 필지번호 (19자리)
  - `spfcKndCd`: 공시가격 종별
  - `pblntfPc`: 공시가격 (원 단위)
  - `pblntfDe`: 공시일자
- **주의사항**:
  - PNU (Parcel Number Unit)가 부동산 유일 식별자로 유용. `local_id_canonical`의 base로 활용 추천
  - 연 1회 발표 (4월 경). 재조회 필요 시점 명확

#### C. 세움터 건축물대장 API

- **Endpoint**: `http://apis.data.go.kr/1613000/BldRgstService_v2/getBrTitleInfo` 외 세부
- **인증**: 공공데이터포털 API key
- **Rate limit**: 초당 30건, 일 10,000건
- **비용**: 무료
- **주요 API**:
  - `getBrTitleInfo`: 표제부
  - `getBrExposPubuseAreaInfo`: 전유공용면적
  - `getBrFlrOulnInfo`: 층별개요
- **주요 필드**:
  - `platPlc`: 대지위치
  - `bldNm`: 건물명
  - `totArea`: 총면적
  - `useAprDay`: 사용승인일
  - `mainPurpsCd`: 주용도
  - `strctCd`: 구조
  - `hhldCnt`: 세대수
  - `grndFlrCnt`, `ugrndFlrCnt`: 지상·지하 층수
- **주의사항**:
  - PNU 기반 조회. MOLIT 실거래가와 조인 시 지번 → PNU 매핑 필요
  - `platPlc`는 원문 주소, 정규화 필요

### 2.2 Priority 1 — Nice to have

#### D. KB부동산 시세

- 공식 API 없음. **파트너십 필요** or 크롤링 (약관 확인 필수)
- 대안: `한국부동산원 R-ONE` (부동산정보 통합 플랫폼)
  - Endpoint: `https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do`
  - 통계 데이터 (지수·평균 시세), 개별 물건 시세는 아님
  - MVP 백테스트 검증용으로만 사용

#### E. 지하철역 데이터 (서울시 열린데이터광장)

- **Endpoint**: `http://openapi.seoul.go.kr:8088/{API_KEY}/json/SearchInfoBySubwayNameService/...`
- 무료, key 발급 필요
- 좌표 포함. POI 테이블 시딩용

#### F. 학교 데이터 (교육부 학교알리미)

- **Endpoint**: `https://www.schoolinfo.go.kr` (open API 제한적)
- 좌표는 별도 지오코딩 필요 (Kakao/Naver Geocoding)
- POI 테이블 시딩용

### 2.3 Priority 2 — Later

#### G. 등기부등본 (인터넷등기소)

- 건당 유료 (약 1,000원)
- API가 공식적으론 제한적. B2B 계약 필요
- 개별 물건 검증용, 대량 수집 불가
- MVP 단계에서는 제외, Attestation 이슈 시점에 개별 조회

#### H. 법원경매정보

- Endpoint: 공식 API 없음
- 크롤링 or 유료 데이터 벤더
- 이상치·극단 케이스 분석용, MVP 후반부

---

## 3. Implementation Structure

```
packages/adapter-kr/
├── src/adapter_kr/
│   ├── __init__.py
│   ├── adapter.py               # KoreaAdapter class
│   ├── molit/
│   │   ├── client.py            # HTTP client (httpx)
│   │   ├── apt_trade.py         # 아파트 매매
│   │   ├── apt_rent.py          # 전월세 (Phase 2)
│   │   ├── xml_parser.py
│   │   └── normalizer.py
│   ├── kongsi/
│   │   ├── client.py
│   │   └── normalizer.py
│   ├── seum/                    # 세움터
│   │   ├── client.py
│   │   └── normalizer.py
│   ├── geo/
│   │   ├── legal_dong_codes.py  # 법정동 코드 마스터
│   │   ├── pnu_parser.py
│   │   └── address_normalizer.py
│   └── config.py
├── tests/
│   ├── fixtures/                # 실제 API 응답 샘플 (redacted)
│   └── test_*.py
└── pyproject.toml
```

---

## 4. Ingestion Pipeline

### 4.1 Bulk Historical Ingestion (Month 1)

**Target**: 서울 25개 자치구 × 60개월 (2020.01 – 2024.12) = 1,500 API calls (아파트 매매만)

**Script**: `scripts/ingest_molit.py`

```python
# Pseudocode
for gu_code in SEOUL_GU_CODES:  # 25개
    for month in date_range("2020-01", "2024-12"):
        raw_transactions = await molit_client.fetch_apt_trades(
            lawd_cd=gu_code, deal_ymd=month
        )
        for raw in raw_transactions:
            tx = normalizer.to_transaction(raw)
            property_ref = normalizer.to_property_ref(raw)
            await db.upsert_property(property_ref)
            await db.upsert_transaction(tx)
        
        # rate limit
        await asyncio.sleep(0.05)  # 20 req/s (안전 마진)
```

**예상 실행 시간**: 1,500 calls × 평균 0.5s = 약 15분 (rate limit 여유 감안)
**예상 레코드 수**: 서울 아파트 매매 5년치 약 30만–50만 건

### 4.2 Incremental Sync (일일)

- 매일 새벽 04:00 KST: 전날 데이터 fetch
- 이번달·전달 재조회 (신고 지연 반영)
- APScheduler or Prefect

### 4.3 Government Valuation Backfill

- 연 1회 (4월경) 전량 재수집
- PNU 매칭 후 property record 업데이트

---

## 5. Normalization Rules

### 5.1 `local_id_canonical` for KR

한국 부동산은 PNU (필지번호 19자리)가 이상적이지만, MOLIT 실거래가에는 PNU가 직접 안 옴. 다음 규칙으로 canonical form 생성:

```
KR-{sggCd(5)}-{umdCd(5)}-{landCd(1)}-{bonbun(4)}-{bubun(4)}-{aptDong or ""}-{floor}-{net_area_sqm×100}
```

예: `KR-11680-10800-1-0045-0000-A-12-8499`

**주의**:
- 같은 아파트 동일 세대는 같은 `local_id_canonical`이 나와야 함
- 여러 거래가 이 canonical에 붙어 여러 Transaction으로 저장됨
- `aptDong` 결측인 경우 빈 문자열 (문서화)
- 층은 로얄층 프리미엄 반영 위해 유지

**최적 시나리오**: 세움터·공시가격 API에서 PNU 크로스매칭 성공 시 PNU 기반 canonical로 교체 (v2). 마이그레이션 시 `global_id` alias 테이블 유지.

### 5.2 Address Normalization

- 원본: `서울특별시 강남구 테헤란로 45`
- 정규화 규칙:
  1. 시/도명 영문 표준 매핑 (서울특별시 → Seoul)
  2. 구/동명 로마자 표기 (외교부 로마자 표기법)
  3. 도로명 뒤에 (Road) 표기 생략, `-ro`, `-gil` 표준화
  4. 결과: `45, Teheran-ro, Gangnam-gu, Seoul`
- 우편번호는 별도 필드

### 5.3 Currency

- 원본 `dealAmount`: `"12,500"` (단위: 만원)
- 정규화:
  ```
  KRW = int(dealAmount.replace(",", "")) * 10_000
  USD_cents = KRW * fx_rate_at_date * 100
  ```
- `fx_rate_at_date`: 한국은행 매매기준율 (거래일 기준). 별도 FX 테이블 필요
  - Source: 한국은행 ECOS OpenAPI

### 5.4 Cancelled Transactions

- `cdealType == "O"`: `is_cancelled = true`, `cancelled_at = cdealDay`
- **분석에서 제외하되 저장은 유지**
- 취소율 자체가 시장 지표

---

## 6. Error Handling & Resilience

- **HTTP retry**: 5xx는 exponential backoff (3회), 4xx는 즉시 로깅 후 skip
- **XML parse fail**: raw payload 저장 후 dead-letter queue에 push
- **Rate limit hit**: `429` 응답 시 60초 대기
- **API 스펙 변경 감지**: 알려진 필드가 3회 연속 결측이면 alert
- **Idempotency**: `(source, source_record_id)` unique constraint → 재실행 안전

---

## 7. Testing Strategy

- **Unit**: 파서·정규화기 (실제 XML fixture 기반)
- **Integration**: mock HTTP 서버로 rate limit·에러 시나리오
- **Contract**: adapter 인터페이스 준수 여부
- **Live smoke**: CI에서 하루 1회 실제 API 1건 호출 (스펙 변경 감지)

**Fixtures 예시**:
```
tests/fixtures/molit/
├── apt_trade_11680_202401.xml           # 정상 응답
├── apt_trade_empty.xml                  # 빈 응답
├── apt_trade_cancelled.xml              # 취소 거래 포함
├── apt_trade_related_party.xml          # 직거래
├── apt_trade_pagination.xml             # 페이징
└── apt_trade_malformed.xml              # 파싱 에러 케이스
```

---

## 8. Secrets & Config

`.env.example`:
```
# 공공데이터포털 API
MOLIT_API_KEY=your_key_here
KONGSI_API_KEY=your_key_here
SEUM_API_KEY=your_key_here

# 서울시 열린데이터
SEOUL_OPEN_DATA_KEY=your_key_here

# 한국은행 ECOS
BOK_ECOS_KEY=your_key_here

# DB
DATABASE_URL=postgresql+asyncpg://...

# Storage
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=valis-raw-kr
```

Railway secrets 등록 필수 항목:
- 모든 `*_API_KEY`
- `DATABASE_URL`
- R2 credentials

---

## 9. Deliverables Checklist

M1 종료 시:

- [ ] `KoreaAdapter` 클래스 구현
- [ ] MOLIT `getRTMSDataSvcAptTradeDev` fetch + parse + normalize
- [ ] 공시가격 fetch + normalize
- [ ] 세움터 표제부 fetch + normalize
- [ ] 지하철역·학교 POI 시딩 스크립트
- [ ] `scripts/ingest_molit.py` 배치 실행 가능
- [ ] 서울 25개 구 × 60개월 데이터 DB 적재 완료
- [ ] 이상치·중복·취소 통계 리포트 (Jupyter notebook)
- [ ] Unit test coverage ≥ 80% for normalizer
- [ ] Live smoke test CI 통과
