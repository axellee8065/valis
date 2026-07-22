"""Initial schema — properties, transactions, valuations, attestations, POIs,
FX rates, model registry, Sui deployments. Adds PostGIS + geometry columns.

Revision ID: 0001
Revises:
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "properties",
        sa.Column("global_id", sa.String(66), primary_key=True),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("local_id", sa.String(128), nullable=False),
        sa.Column("local_id_canonical", sa.String(128), nullable=False),
        sa.Column("property_type", sa.String(32), nullable=False),
        sa.Column("property_subtype", sa.String(64)),
        sa.Column("latitude", sa.Numeric(10, 7)),
        sa.Column("longitude", sa.Numeric(10, 7)),
        sa.Column("address_normalized", sa.Text, nullable=False),
        sa.Column("address_original", sa.Text, nullable=False),
        sa.Column("postal_code", sa.String(16)),
        sa.Column("admin_level_1", sa.String(64)),
        sa.Column("admin_level_2", sa.String(64)),
        sa.Column("admin_level_3", sa.String(64)),
        sa.Column("admin_level_4", sa.String(64)),
        sa.Column("land_area_sqm", sa.Numeric(12, 2)),
        sa.Column("building_area_sqm", sa.Numeric(12, 2)),
        sa.Column("net_area_sqm", sa.Numeric(12, 2)),
        sa.Column("built_year", sa.SmallInteger),
        sa.Column("floors_total", sa.SmallInteger),
        sa.Column("floor_number", sa.SmallInteger),
        sa.Column("units_in_building", sa.Integer),
        sa.Column("parking_spaces", sa.SmallInteger),
        sa.Column("heating_type", sa.String(32)),
        sa.Column("ownership_type", sa.String(32)),
        sa.Column("complex_id", sa.String(128)),
        sa.Column("complex_name", sa.String(256)),
        sa.Column("developer", sa.String(128)),
        sa.Column("is_offplan", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("expected_handover_date", sa.Date),
        sa.Column("foreign_ownership_eligible", sa.Boolean),
        sa.Column("community_id", sa.String(128)),
        sa.Column("community_name", sa.String(256)),
        sa.Column("raw_source_uri", sa.Text),
        sa.Column("data_sources", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("country_code", "local_id_canonical", name="uq_property_local"),
    )
    op.create_index(
        "ix_property_admin", "properties", ["country_code", "admin_level_1", "admin_level_2"]
    )
    op.create_index(
        "ix_property_complex",
        "properties",
        ["complex_id"],
        postgresql_where=sa.text("complex_id IS NOT NULL"),
    )
    op.create_index("ix_property_type_country", "properties", ["property_type", "country_code"])
    # PostGIS point managed outside the ORM (docs/01 §2.1)
    op.execute("ALTER TABLE properties ADD COLUMN geom geometry(Point, 4326)")
    op.execute("CREATE INDEX ix_property_geom ON properties USING GIST (geom)")

    op.create_table(
        "transactions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("global_id", sa.String(66), nullable=False),
        sa.Column("transaction_type", sa.String(32), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("contract_date", sa.Date),
        sa.Column("registration_date", sa.Date),
        sa.Column("price_usd_cents", sa.BigInteger),
        sa.Column("price_original_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("price_original_currency", sa.String(3), nullable=False),
        sa.Column("fx_rate_at_date", sa.Numeric(20, 10)),
        sa.Column("monthly_rent_usd_cents", sa.BigInteger),
        sa.Column("lease_deposit_usd_cents", sa.BigInteger),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_cancelled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cancelled_at", sa.Date),
        sa.Column("is_related_party", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_record_id", name="uq_tx_source_record"),
    )
    op.create_index(
        "ix_tx_property_date", "transactions", ["global_id", sa.text("transaction_date DESC")]
    )
    op.create_index(
        "ix_tx_date_type",
        "transactions",
        ["transaction_date", "transaction_type"],
        postgresql_where=sa.text("is_cancelled = false"),
    )

    op.create_table(
        "government_valuations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("global_id", sa.String(66), nullable=False),
        sa.Column("valuation_type", sa.String(64), nullable=False),
        sa.Column("assessment_year", sa.SmallInteger, nullable=False),
        sa.Column("assessment_date", sa.Date, nullable=False),
        sa.Column("value_usd_cents", sa.BigInteger, nullable=False),
        sa.Column("value_original_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("value_original_currency", sa.String(3), nullable=False),
        sa.Column("fx_rate_at_date", sa.Numeric(20, 10), nullable=False),
        sa.Column("source_authority", sa.String(128), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("global_id", "valuation_type", "assessment_year", name="uq_gov_val"),
    )
    op.create_index("ix_gov_val_date", "government_valuations", [sa.text("assessment_date DESC")])

    op.create_table(
        "appraisal_attestations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("attestation_uid", sa.String(66), unique=True),
        sa.Column("global_id", sa.String(66), nullable=False),
        sa.Column("value_usd_cents", sa.BigInteger, nullable=False),
        sa.Column("confidence_score_bps", sa.SmallInteger, nullable=False),
        sa.Column("ci_lower_usd_cents", sa.BigInteger, nullable=False),
        sa.Column("ci_upper_usd_cents", sa.BigInteger, nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(64)),
        sa.Column("model_features_hash", sa.String(66)),
        sa.Column("report_uri", sa.Text),
        sa.Column("report_hash", sa.String(66)),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sui_tx_digest", sa.String(66)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_att_property_issued", "appraisal_attestations", ["global_id", sa.text("issued_at DESC")]
    )
    op.create_index(
        "ix_att_expires",
        "appraisal_attestations",
        ["expires_at"],
        postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "points_of_interest",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("poi_type", sa.String(32), nullable=False),
        sa.Column("name_normalized", sa.String(256), nullable=False),
        sa.Column("name_original", sa.String(256), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("metadata", JSONB),
    )
    op.create_index("ix_poi_country_type", "points_of_interest", ["country_code", "poi_type"])
    op.execute("ALTER TABLE points_of_interest ADD COLUMN geom geometry(Point, 4326)")
    op.execute("CREATE INDEX ix_poi_geom ON points_of_interest USING GIST (geom)")

    op.create_table(
        "fx_rates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rate_date", sa.Date, nullable=False),
        sa.Column("usd_per_unit", sa.Numeric(20, 10), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.UniqueConstraint("currency", "rate_date", name="uq_fx_ccy_date"),
    )

    op.create_table(
        "avm_models",
        sa.Column("model_id", sa.String(64), primary_key=True),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("region_scope", sa.String(64), nullable=False),
        sa.Column("property_type", sa.String(32), nullable=False),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_data_range", sa.String(64), nullable=False),
        sa.Column("feature_config_json", JSONB, nullable=False),
        sa.Column("metrics_json", JSONB, nullable=False),
        sa.Column("artifact_uri", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "sui_deployments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("package_id", sa.String(66), nullable=False),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_ids", JSONB, nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    for table in [
        "sui_deployments",
        "avm_models",
        "fx_rates",
        "points_of_interest",
        "appraisal_attestations",
        "government_valuations",
        "transactions",
        "properties",
    ]:
        op.drop_table(table)
