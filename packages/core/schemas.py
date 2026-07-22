"""International normalized schemas (docs/01-data-schema.md).

Design principles:
- Immutable value objects (frozen pydantic models); new versions are appended, never mutated.
- International units: area in sqm, money in USD cents (int), coordinates in WGS84.
- Normalized value + original value stored together for audit/debugging.
- Enums as strings for migration friendliness.
- UAE-required fields are pre-included per docs/06-uae-expansion.md §3.1.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

GLOBAL_ID_PATTERN = r"^0x[0-9a-f]{64}$"


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
    MUSATAHA = "MUSATAHA"  # UAE 50-year development right
    OFFPLAN = "OFFPLAN"  # 분양권
    OTHER = "OTHER"


class HeatingType(StrEnum):
    DISTRICT = "DISTRICT"
    INDIVIDUAL_GAS = "INDIVIDUAL_GAS"
    CENTRAL = "CENTRAL"
    ELECTRIC = "ELECTRIC"
    OTHER = "OTHER"


class ValuationMethod(StrEnum):
    AVM = "AVM"
    CONSENSUS = "CONSENSUS"
    HYBRID = "HYBRID"


class PoiType(StrEnum):
    SUBWAY_STATION = "SUBWAY_STATION"
    SCHOOL_ELEM = "SCHOOL_ELEM"
    SCHOOL_MIDDLE = "SCHOOL_MIDDLE"
    SCHOOL_HIGH = "SCHOOL_HIGH"
    HOSPITAL = "HOSPITAL"
    SHOPPING_MALL = "SHOPPING_MALL"
    PARK = "PARK"
    UNIVERSITY = "UNIVERSITY"


class EncumbranceType(StrEnum):
    MORTGAGE = "MORTGAGE"
    LIEN = "LIEN"
    SEIZURE = "SEIZURE"
    TAX_LIEN = "TAX_LIEN"
    RIGHT_OF_WAY = "RIGHT_OF_WAY"


class DataSourceRef(BaseModel):
    """One entry of Property.data_sources."""

    model_config = ConfigDict(frozen=True)

    source: str
    fetched_at: datetime
    raw_id: str
    checksum: str | None = None


class Property(BaseModel):
    model_config = ConfigDict(frozen=True)

    global_id: str = Field(..., pattern=GLOBAL_ID_PATTERN)
    country_code: str = Field(..., min_length=2, max_length=2)
    local_id: str
    local_id_canonical: str
    property_type: PropertyType
    property_subtype: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    address_normalized: str
    address_original: str
    postal_code: str | None = None
    admin_level_1: str | None = None
    admin_level_2: str | None = None
    admin_level_3: str | None = None
    admin_level_4: str | None = None
    land_area_sqm: Decimal | None = None
    building_area_sqm: Decimal | None = None
    net_area_sqm: Decimal | None = None
    built_year: int | None = None
    floors_total: int | None = None
    floor_number: int | None = None
    units_in_building: int | None = None
    parking_spaces: int | None = None
    heating_type: HeatingType | None = None
    ownership_type: OwnershipType | None = None
    complex_id: str | None = None
    complex_name: str | None = None
    developer: str | None = None
    # --- UAE pre-emptive fields (docs/06 §3.1) ---
    is_offplan: bool = False
    expected_handover_date: date | None = None
    foreign_ownership_eligible: bool | None = None
    community_id: str | None = None
    community_name: str | None = None
    # ---
    raw_source_uri: str | None = None
    data_sources: list[DataSourceRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    version: int = 1


class Transaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    global_id: str = Field(..., pattern=GLOBAL_ID_PATTERN)
    transaction_type: TransactionType
    transaction_date: date
    contract_date: date | None = None
    registration_date: date | None = None
    price_usd_cents: int | None = None
    price_original_amount: Decimal
    price_original_currency: str = Field(..., min_length=3, max_length=3)
    fx_rate_at_date: Decimal | None = None
    monthly_rent_usd_cents: int | None = None
    lease_deposit_usd_cents: int | None = None
    is_verified: bool = True
    is_cancelled: bool = False
    cancelled_at: date | None = None
    is_related_party: bool = False
    source: str
    source_record_id: str
    raw_payload: dict
    ingested_at: datetime


class GovernmentValuation(BaseModel):
    model_config = ConfigDict(frozen=True)

    global_id: str = Field(..., pattern=GLOBAL_ID_PATTERN)
    valuation_type: str  # e.g. KR_APT_KONGSI, KR_LAND_KONGSI, AE_DLD_ESTIMATE
    assessment_year: int
    assessment_date: date
    value_usd_cents: int
    value_original_amount: Decimal
    value_original_currency: str = Field(..., min_length=3, max_length=3)
    fx_rate_at_date: Decimal
    source_authority: str
    raw_payload: dict
    ingested_at: datetime


class AppraisalAttestationRecord(BaseModel):
    """Off-chain record of an attestation issued by the protocol."""

    model_config = ConfigDict(frozen=True)

    attestation_uid: str | None = None  # Sui Object UID, filled after on-chain issue
    global_id: str = Field(..., pattern=GLOBAL_ID_PATTERN)
    value_usd_cents: int = Field(..., gt=0)
    confidence_score_bps: int = Field(..., ge=0, le=10_000)
    ci_lower_usd_cents: int
    ci_upper_usd_cents: int
    method: ValuationMethod
    model_id: str | None = None
    model_features_hash: str | None = None
    report_uri: str | None = None
    report_hash: str | None = None
    issued_at: datetime
    expires_at: datetime
    sui_tx_digest: str | None = None
    is_active: bool = True


class PointOfInterest(BaseModel):
    model_config = ConfigDict(frozen=True)

    country_code: str = Field(..., min_length=2, max_length=2)
    poi_type: PoiType
    name_normalized: str
    name_original: str
    latitude: Decimal
    longitude: Decimal
    metadata: dict | None = None


class AVMPrediction(BaseModel):
    """Output of any AVM model version."""

    model_config = ConfigDict(frozen=True)

    global_id: str
    model_id: str
    value_usd_cents: int
    ci_lower_usd_cents: int | None = None
    ci_upper_usd_cents: int | None = None
    confidence_score_bps: int | None = None
    predicted_at: datetime
    features_hash: str | None = None
