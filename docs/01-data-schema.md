# 01 — International Data Schema Specification

**Purpose:** 모든 국가의 부동산·거래·평가 데이터를 담을 정규화 스키마. 코어 프로토콜은 이 스키마만 알고, 국가별 원본은 어댑터가 변환.

**References:**
- RESO Data Dictionary 1.7 (미국 부동산 표준)
- INSPIRE Directive (EU 공간정보)
- ISO 3166-1 alpha-2 (country codes)
- ISO 4217 (currency codes)

---

## 1. 설계 원칙

1. **Immutable value objects**: 원본 스냅샷은 절대 mutate 안 함, 새 버전으로 append
2. **국제 표준 단위**: 면적 sqm, 통화 USD cents (int), 좌표 WGS84
3. **원본 병기 필수**: 정규화된 값 + 원본 값 함께 저장 (감사·디버깅)
4. **Enum은 문자열로**: DB migration 편의를 위해 SMALLINT 대신 문자열 enum
5. **JSON 필드는 최소화**: 검색·조인이 필요한 필드는 반드시 컬럼

---

## 2. Core Entities

### 2.1 `Property` — 부동산 마스터

| Field | Type | Nullable | Description |
|---|---|---|---|
| `global_id` | `VARCHAR(66)` | NO | Primary key. `sha256({country_code}:{local_id_canonical})` hex-prefixed with `0x` |
| `country_code` | `CHAR(2)` | NO | ISO 3166-1 alpha-2 (KR, AE, SG, ...) |
| `local_id` | `VARCHAR(128)` | NO | 원본 식별자 (예: 등기부번호, DLD ref) |
| `local_id_canonical` | `VARCHAR(128)` | NO | 어댑터가 정규화한 canonical form |
| `property_type` | `VARCHAR(32)` | NO | ENUM: `APARTMENT`, `HOUSE_DETACHED`, `HOUSE_TERRACED`, `VILLA`, `TOWNHOUSE`, `CONDO`, `OFFICE`, `RETAIL`, `INDUSTRIAL`, `LAND`, `MIXED_USE`, `OTHER` |
| `property_subtype` | `VARCHAR(64)` | YES | 국가별 서브타입 (예: 재건축·주상복합) |
| `latitude` | `DECIMAL(10,7)` | YES | WGS84 |
| `longitude` | `DECIMAL(10,7)` | YES | WGS84 |
| `geom` | `GEOMETRY(Point, 4326)` | YES | PostGIS point |
| `address_normalized` | `TEXT` | NO | Roman/English 표준화 주소 |
| `address_original` | `TEXT` | NO | 원문 (한글·아랍어 등) |
| `postal_code` | `VARCHAR(16)` | YES | |
| `admin_level_1` | `VARCHAR(64)` | YES | 시/도, Emirate |
| `admin_level_2` | `VARCHAR(64)` | YES | 구, District |
| `admin_level_3` | `VARCHAR(64)` | YES | 동/읍/면, Community |
| `admin_level_4` | `VARCHAR(64)` | YES | 리, Sub-community |
| `land_area_sqm` | `DECIMAL(12,2)` | YES | |
| `building_area_sqm` | `DECIMAL(12,2)` | YES | GFA |
| `net_area_sqm` | `DECIMAL(12,2)` | YES | 전용면적 |
| `built_year` | `SMALLINT` | YES | |
| `floors_total` | `SMALLINT` | YES | 건물 총 층수 |
| `floor_number` | `SMALLINT` | YES | 해당 세대 층 |
| `units_in_building` | `INTEGER` | YES | 세대수 |
| `parking_spaces` | `SMALLINT` | YES | |
| `heating_type` | `VARCHAR(32)` | YES | ENUM: `DISTRICT`, `INDIVIDUAL_GAS`, `CENTRAL`, `ELECTRIC`, `OTHER` |
| `ownership_type` | `VARCHAR(32)` | YES | ENUM: `FREEHOLD`, `LEASEHOLD`, `STRATA`, `USUFRUCT`, `MUSATAHA`, `OTHER` |
| `complex_id` | `VARCHAR(128)` | YES | 단지 ID (같은 단지는 같은 값) |
| `complex_name` | `VARCHAR(256)` | YES | 단지명 |
| `developer` | `VARCHAR(128)` | YES | 시공사·개발사 |
| `raw_source_uri` | `TEXT` | YES | 원본 스냅샷 저장 위치 (R2/S3) |
| `data_sources` | `JSONB` | NO | 이 레코드가 참조한 소스 리스트 (아래 스키마) |
| `created_at` | `TIMESTAMP` | NO | |
| `updated_at` | `TIMESTAMP` | NO | |
| `version` | `INTEGER` | NO | Optimistic locking |

**Indexes:**
- `PRIMARY KEY (global_id)`
- `UNIQUE (country_code, local_id_canonical)`
- `INDEX (country_code, admin_level_1, admin_level_2)`
- `INDEX (complex_id)` WHERE complex_id IS NOT NULL
- `SPATIAL INDEX (geom)`
- `INDEX (property_type, country_code)`

**`data_sources` JSON schema:**
```json
[
  {
    "source": "MOLIT_APT_TRADE",
    "fetched_at": "2026-07-23T00:00:00Z",
    "raw_id": "202607_11680_...",
    "checksum": "sha256:..."
  }
]
```

### 2.2 `Transaction` — 거래 이벤트

| Field | Type | Nullable | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | NO | PK |
| `global_id` | `VARCHAR(66)` | NO | Property FK |
| `transaction_type` | `VARCHAR(32)` | NO | ENUM: `SALE`, `LEASE_JEONSE`, `LEASE_MONTHLY`, `AUCTION`, `INHERITANCE`, `GIFT`, `EXCHANGE`, `OTHER` |
| `transaction_date` | `DATE` | NO | |
| `contract_date` | `DATE` | YES | 계약일 (실거래가는 계약일 기준) |
| `registration_date` | `DATE` | YES | 소유권 이전 등기일 |
| `price_usd_cents` | `BIGINT` | YES | 정규화 가격 (매매·전세보증금) |
| `price_original_amount` | `NUMERIC(20,2)` | NO | 원본 통화 액수 |
| `price_original_currency` | `CHAR(3)` | NO | ISO 4217 (KRW, AED, USD) |
| `fx_rate_at_date` | `NUMERIC(20,10)` | YES | 거래일 기준 환율 (원본→USD) |
| `monthly_rent_usd_cents` | `BIGINT` | YES | 월세인 경우 |
| `lease_deposit_usd_cents` | `BIGINT` | YES | 보증금 |
| `is_verified` | `BOOLEAN` | NO | 정부 등록 여부 |
| `is_cancelled` | `BOOLEAN` | NO | 취소된 거래 (분석에서 제외) |
| `cancelled_at` | `DATE` | YES | |
| `is_related_party` | `BOOLEAN` | NO | 특수관계자 거래 (직계·법인) |
| `source` | `VARCHAR(64)` | NO | e.g. `MOLIT_APT_TRADE` |
| `source_record_id` | `VARCHAR(128)` | NO | 원본 시스템 ID |
| `raw_payload` | `JSONB` | NO | 원본 필드 전체 보관 |
| `ingested_at` | `TIMESTAMP` | NO | |

**Indexes:**
- `PRIMARY KEY (id)`
- `INDEX (global_id, transaction_date DESC)`
- `INDEX (transaction_date, transaction_type)` WHERE is_cancelled = false
- `INDEX (source, source_record_id)` UNIQUE

### 2.3 `GovernmentValuation` — 정부 공식 가치 (공시가격 등)

| Field | Type | Nullable | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | NO | PK |
| `global_id` | `VARCHAR(66)` | NO | Property FK |
| `valuation_type` | `VARCHAR(64)` | NO | ENUM: `KR_APT_KONGSI`, `KR_LAND_KONGSI`, `KR_INDIV_HOUSE`, `AE_DLD_ESTIMATE`, ... |
| `assessment_year` | `SMALLINT` | NO | |
| `assessment_date` | `DATE` | NO | |
| `value_usd_cents` | `BIGINT` | NO | |
| `value_original_amount` | `NUMERIC(20,2)` | NO | |
| `value_original_currency` | `CHAR(3)` | NO | |
| `fx_rate_at_date` | `NUMERIC(20,10)` | NO | |
| `source_authority` | `VARCHAR(128)` | NO | 발표 기관 |
| `raw_payload` | `JSONB` | NO | |
| `ingested_at` | `TIMESTAMP` | NO | |

**Indexes:**
- `UNIQUE (global_id, valuation_type, assessment_year)`
- `INDEX (assessment_date DESC)`

### 2.4 `AppraisalAttestation` — 우리 프로토콜이 발행한 감정 결과

| Field | Type | Nullable | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | NO | PK |
| `attestation_uid` | `VARCHAR(66)` | NO | Sui Object UID (온체인 발행 후 채움) |
| `global_id` | `VARCHAR(66)` | NO | Property FK |
| `value_usd_cents` | `BIGINT` | NO | 감정 결과 |
| `confidence_score_bps` | `SMALLINT` | NO | 0-10000 (0.00 - 100.00%) |
| `ci_lower_usd_cents` | `BIGINT` | NO | 95% 신뢰구간 하단 |
| `ci_upper_usd_cents` | `BIGINT` | NO | 95% 신뢰구간 상단 |
| `method` | `VARCHAR(32)` | NO | ENUM: `AVM`, `CONSENSUS`, `HYBRID` |
| `model_id` | `VARCHAR(64)` | YES | 사용된 AVM 모델 버전 |
| `model_features_hash` | `VARCHAR(66)` | YES | 입력 피처 해시 (재현성) |
| `report_uri` | `TEXT` | YES | 상세 리포트 저장 위치 (Walrus/R2) |
| `report_hash` | `VARCHAR(66)` | YES | 리포트 sha256 |
| `issued_at` | `TIMESTAMP` | NO | |
| `expires_at` | `TIMESTAMP` | NO | |
| `sui_tx_digest` | `VARCHAR(66)` | YES | 온체인 발행 트랜잭션 |
| `is_active` | `BOOLEAN` | NO | 만료·revoke 여부 |

**Indexes:**
- `INDEX (global_id, issued_at DESC)`
- `INDEX (attestation_uid)` UNIQUE
- `INDEX (expires_at)` WHERE is_active = true

### 2.5 `PointOfInterest` — 지리적 참조점

| Field | Type | Nullable | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | NO | PK |
| `country_code` | `CHAR(2)` | NO | |
| `poi_type` | `VARCHAR(32)` | NO | ENUM: `SUBWAY_STATION`, `SCHOOL_ELEM`, `SCHOOL_MIDDLE`, `SCHOOL_HIGH`, `HOSPITAL`, `SHOPPING_MALL`, `PARK`, `UNIVERSITY` |
| `name_normalized` | `VARCHAR(256)` | NO | |
| `name_original` | `VARCHAR(256)` | NO | |
| `latitude` | `DECIMAL(10,7)` | NO | |
| `longitude` | `DECIMAL(10,7)` | NO | |
| `geom` | `GEOMETRY(Point, 4326)` | NO | |
| `metadata` | `JSONB` | YES | 학군 점수·역 노선 등 |

**Indexes:**
- `SPATIAL INDEX (geom)`
- `INDEX (country_code, poi_type)`

### 2.6 `Encumbrance` — 담보·저당·제한 이력

| Field | Type | Nullable | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | NO | PK |
| `global_id` | `VARCHAR(66)` | NO | Property FK |
| `encumbrance_type` | `VARCHAR(32)` | NO | ENUM: `MORTGAGE`, `LIEN`, `SEIZURE`, `TAX_LIEN`, `RIGHT_OF_WAY` |
| `holder_name` | `VARCHAR(256)` | YES | 저당권자 |
| `principal_usd_cents` | `BIGINT` | YES | |
| `registered_at` | `DATE` | NO | |
| `discharged_at` | `DATE` | YES | 해지일 |
| `is_active` | `BOOLEAN` | NO | |
| `source` | `VARCHAR(64)` | NO | |
| `raw_payload` | `JSONB` | NO | |

---

## 3. Enum Reference

### 3.1 `property_type`
```
APARTMENT       - 아파트 (공동주택)
HOUSE_DETACHED  - 단독주택
HOUSE_TERRACED  - 연립·다세대
VILLA           - 빌라 (UAE 기준)
TOWNHOUSE       - 타운하우스
CONDO           - 콘도
OFFICE          - 오피스
RETAIL          - 리테일
INDUSTRIAL      - 산업용
LAND            - 나대지
MIXED_USE       - 주상복합
OTHER
```

### 3.2 `transaction_type`
```
SALE            - 매매
LEASE_JEONSE    - 전세
LEASE_MONTHLY   - 월세
AUCTION         - 경매
INHERITANCE     - 상속
GIFT            - 증여
EXCHANGE        - 교환
OTHER
```

### 3.3 `ownership_type`
```
FREEHOLD        - 완전소유
LEASEHOLD       - 임차권
STRATA          - 구분소유 (아파트 표준)
USUFRUCK        - 용익권
MUSATAHA        - UAE 무사타하 (50년 개발권)
OTHER
```

---

## 4. Python Type Definitions (`packages/core/schemas.py`)

```python
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class PropertyType(StrEnum):
    APARTMENT = "APARTMENT"
    HOUSE_DETACHED = "HOUSE_DETACHED"
    HOUSE_TERRACED = "HOUSE_TERRACED"
    VILLA = "VILLA"
    TOWNHOUSE = "TOWNHOUSE"
    CONDO = "CONDO"
    OFFICE = "OFFICE"
    RETAIL = "RETAIL"
    INDUSTRIAL = "INDUSTRIAL"
    LAND = "LAND"
    MIXED_USE = "MIXED_USE"
    OTHER = "OTHER"


class TransactionType(StrEnum):
    SALE = "SALE"
    LEASE_JEONSE = "LEASE_JEONSE"
    LEASE_MONTHLY = "LEASE_MONTHLY"
    AUCTION = "AUCTION"
    INHERITANCE = "INHERITANCE"
    GIFT = "GIFT"
    EXCHANGE = "EXCHANGE"
    OTHER = "OTHER"


class OwnershipType(StrEnum):
    FREEHOLD = "FREEHOLD"
    LEASEHOLD = "LEASEHOLD"
    STRATA = "STRATA"
    USUFRUCT = "USUFRUCT"
    MUSATAHA = "MUSATAHA"
    OTHER = "OTHER"


class Property(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    global_id: str = Field(..., pattern=r"^0x[0-9a-f]{64}$")
    country_code: str = Field(..., min_length=2, max_length=2)
    local_id: str
    local_id_canonical: str
    property_type: PropertyType
    property_subtype: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    address_normalized: str
    address_original: str
    postal_code: Optional[str] = None
    admin_level_1: Optional[str] = None
    admin_level_2: Optional[str] = None
    admin_level_3: Optional[str] = None
    admin_level_4: Optional[str] = None
    land_area_sqm: Optional[Decimal] = None
    building_area_sqm: Optional[Decimal] = None
    net_area_sqm: Optional[Decimal] = None
    built_year: Optional[int] = None
    floors_total: Optional[int] = None
    floor_number: Optional[int] = None
    units_in_building: Optional[int] = None
    parking_spaces: Optional[int] = None
    heating_type: Optional[str] = None
    ownership_type: Optional[OwnershipType] = None
    complex_id: Optional[str] = None
    complex_name: Optional[str] = None
    developer: Optional[str] = None
    raw_source_uri: Optional[str] = None
    data_sources: list[dict]
    created_at: datetime
    updated_at: datetime
    version: int = 1


class Transaction(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    global_id: str
    transaction_type: TransactionType
    transaction_date: date
    contract_date: Optional[date] = None
    registration_date: Optional[date] = None
    price_usd_cents: Optional[int] = None
    price_original_amount: Decimal
    price_original_currency: str = Field(..., min_length=3, max_length=3)
    fx_rate_at_date: Optional[Decimal] = None
    monthly_rent_usd_cents: Optional[int] = None
    lease_deposit_usd_cents: Optional[int] = None
    is_verified: bool = True
    is_cancelled: bool = False
    cancelled_at: Optional[date] = None
    is_related_party: bool = False
    source: str
    source_record_id: str
    raw_payload: dict
    ingested_at: datetime
```

---

## 5. Global ID Generation

`global_id`는 다음 방식으로 결정론적 생성:

```python
import hashlib

def make_global_id(country_code: str, local_id_canonical: str) -> str:
    """
    - country_code: uppercase ISO 3166-1 alpha-2
    - local_id_canonical: 어댑터가 정규화한 canonical form
      (whitespace strip, uppercase, delimiter normalized)
    """
    payload = f"{country_code.upper()}:{local_id_canonical}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"0x{digest}"
```

**중요**: `local_id_canonical` 규칙은 국가별 어댑터가 정의하고 절대 변경 금지. 변경 시 모든 `global_id`가 바뀌므로 온체인 attestation과 연결이 끊어짐.

---

## 6. Migration Strategy

- Alembic 사용
- 스키마 변경 시 **하위 호환 우선**: 컬럼 추가 O, 삭제·타입 변경은 2단계 배포 (add → migrate data → remove)
- Enum 값 추가는 자유, 제거·rename은 금지
- 마이그레이션 파일은 `migrations/versions/`, 파일명에 티켓번호 포함

---

## 7. Sample Records

### Korean 아파트 예시

```json
{
  "global_id": "0x3f2a...",
  "country_code": "KR",
  "local_id": "1168010800-1-45-1201",
  "local_id_canonical": "KR-1168010800-1-45-1201",
  "property_type": "APARTMENT",
  "latitude": 37.5010,
  "longitude": 127.0396,
  "address_normalized": "45, Teheran-ro, Gangnam-gu, Seoul",
  "address_original": "서울특별시 강남구 테헤란로 45",
  "postal_code": "06134",
  "admin_level_1": "서울특별시",
  "admin_level_2": "강남구",
  "admin_level_3": "역삼동",
  "net_area_sqm": 84.99,
  "building_area_sqm": 112.30,
  "built_year": 2015,
  "floors_total": 25,
  "floor_number": 12,
  "units_in_building": 320,
  "complex_id": "KR-SEOUL-YS-XXX",
  "complex_name": "역삼래미안",
  "ownership_type": "STRATA"
}
```
