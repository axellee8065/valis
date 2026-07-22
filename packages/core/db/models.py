"""SQLAlchemy ORM models mirroring docs/01-data-schema.md.

PostGIS geometry columns are managed in Alembic migrations; the ORM keeps
lat/lng decimals so the package imports without geoalchemy2 at runtime.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PropertyRow(Base):
    __tablename__ = "properties"

    global_id: Mapped[str] = mapped_column(String(66), primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2))
    local_id: Mapped[str] = mapped_column(String(128))
    local_id_canonical: Mapped[str] = mapped_column(String(128))
    property_type: Mapped[str] = mapped_column(String(32))
    property_subtype: Mapped[str | None] = mapped_column(String(64))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    address_normalized: Mapped[str] = mapped_column(Text)
    address_original: Mapped[str] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(String(16))
    admin_level_1: Mapped[str | None] = mapped_column(String(64))
    admin_level_2: Mapped[str | None] = mapped_column(String(64))
    admin_level_3: Mapped[str | None] = mapped_column(String(64))
    admin_level_4: Mapped[str | None] = mapped_column(String(64))
    land_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    building_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    net_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    built_year: Mapped[int | None] = mapped_column(SmallInteger)
    floors_total: Mapped[int | None] = mapped_column(SmallInteger)
    floor_number: Mapped[int | None] = mapped_column(SmallInteger)
    units_in_building: Mapped[int | None] = mapped_column(Integer)
    parking_spaces: Mapped[int | None] = mapped_column(SmallInteger)
    heating_type: Mapped[str | None] = mapped_column(String(32))
    ownership_type: Mapped[str | None] = mapped_column(String(32))
    complex_id: Mapped[str | None] = mapped_column(String(128))
    complex_name: Mapped[str | None] = mapped_column(String(256))
    developer: Mapped[str | None] = mapped_column(String(128))
    # UAE pre-emptive fields (docs/06 §3.1)
    is_offplan: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_handover_date: Mapped[date | None] = mapped_column(Date)
    foreign_ownership_eligible: Mapped[bool | None] = mapped_column(Boolean)
    community_id: Mapped[str | None] = mapped_column(String(128))
    community_name: Mapped[str | None] = mapped_column(String(256))
    raw_source_uri: Mapped[str | None] = mapped_column(Text)
    data_sources: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("country_code", "local_id_canonical", name="uq_property_local"),
        Index("ix_property_admin", "country_code", "admin_level_1", "admin_level_2"),
        Index("ix_property_complex", "complex_id"),
        Index("ix_property_type_country", "property_type", "country_code"),
    )


class TransactionRow(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_id: Mapped[str] = mapped_column(String(66))
    transaction_type: Mapped[str] = mapped_column(String(32))
    transaction_date: Mapped[date] = mapped_column(Date)
    contract_date: Mapped[date | None] = mapped_column(Date)
    registration_date: Mapped[date | None] = mapped_column(Date)
    price_usd_cents: Mapped[int | None] = mapped_column(BigInteger)
    price_original_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    price_original_currency: Mapped[str] = mapped_column(String(3))
    fx_rate_at_date: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    monthly_rent_usd_cents: Mapped[int | None] = mapped_column(BigInteger)
    lease_deposit_usd_cents: Mapped[int | None] = mapped_column(BigInteger)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled_at: Mapped[date | None] = mapped_column(Date)
    is_related_party: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(64))
    source_record_id: Mapped[str] = mapped_column(String(128))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("source", "source_record_id", name="uq_tx_source_record"),
        Index("ix_tx_property_date", "global_id", "transaction_date"),
        Index("ix_tx_date_type", "transaction_date", "transaction_type"),
    )


class GovernmentValuationRow(Base):
    __tablename__ = "government_valuations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_id: Mapped[str] = mapped_column(String(66))
    valuation_type: Mapped[str] = mapped_column(String(64))
    assessment_year: Mapped[int] = mapped_column(SmallInteger)
    assessment_date: Mapped[date] = mapped_column(Date)
    value_usd_cents: Mapped[int] = mapped_column(BigInteger)
    value_original_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    value_original_currency: Mapped[str] = mapped_column(String(3))
    fx_rate_at_date: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    source_authority: Mapped[str] = mapped_column(String(128))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("global_id", "valuation_type", "assessment_year", name="uq_gov_val"),
        Index("ix_gov_val_date", "assessment_date"),
    )


class AttestationRow(Base):
    __tablename__ = "appraisal_attestations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    attestation_uid: Mapped[str | None] = mapped_column(String(66), unique=True)
    global_id: Mapped[str] = mapped_column(String(66))
    value_usd_cents: Mapped[int] = mapped_column(BigInteger)
    confidence_score_bps: Mapped[int] = mapped_column(SmallInteger)
    ci_lower_usd_cents: Mapped[int] = mapped_column(BigInteger)
    ci_upper_usd_cents: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str | None] = mapped_column(String(64))
    model_features_hash: Mapped[str | None] = mapped_column(String(66))
    report_uri: Mapped[str | None] = mapped_column(Text)
    report_hash: Mapped[str | None] = mapped_column(String(66))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sui_tx_digest: Mapped[str | None] = mapped_column(String(66))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_att_property_issued", "global_id", "issued_at"),
        Index("ix_att_expires", "expires_at"),
    )


class PointOfInterestRow(Base):
    __tablename__ = "points_of_interest"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(String(2))
    poi_type: Mapped[str] = mapped_column(String(32))
    name_normalized: Mapped[str] = mapped_column(String(256))
    name_original: Mapped[str] = mapped_column(String(256))
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    __table_args__ = (Index("ix_poi_country_type", "country_code", "poi_type"),)


class FxRateRow(Base):
    """Daily FX rates to USD (source: BOK ECOS for KRW). AED pre-supported (docs/06)."""

    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    currency: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[date] = mapped_column(Date)
    usd_per_unit: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    source: Mapped[str] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("currency", "rate_date", name="uq_fx_ccy_date"),)


class AvmModelRow(Base):
    """Model registry (docs/03-avm-model.md §8)."""

    __tablename__ = "avm_models"

    model_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2))
    region_scope: Mapped[str] = mapped_column(String(64))
    property_type: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(16))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    training_data_range: Mapped[str] = mapped_column(String(64))
    feature_config_json: Mapped[dict] = mapped_column(JSONB)
    metrics_json: Mapped[dict] = mapped_column(JSONB)
    artifact_uri: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class SuiDeploymentRow(Base):
    """Testnet-reset resilience (docs/05 §5.3)."""

    __tablename__ = "sui_deployments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[str] = mapped_column(String(66))
    network: Mapped[str] = mapped_column(String(16))
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    object_ids: Mapped[dict] = mapped_column(JSONB)  # registry/index/feed/cap ids
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
