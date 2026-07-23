"""DLD open-data transaction → normalized Transaction / Property.

Canonical local ID rule (NEVER change — global_id depends on it):
    AE-DXB-{AREA_SLUG}-{BUILDING_SLUG}-{BR_CODE}-{bua_sqm×100}
Example: AE-DXB-BURJ-KHALIFA-BURJ-VISTA-1-2BR-11056

Identity note (docs/08): DLD open data carries no unit numbers (privacy), so an
AE "property" is a *unit class* — building × bedroom count × built-up area.
This is the finest deterministic identity the public record supports; the rule
is fixed even if richer identities become available later (a new source would
introduce a new rule version, never mutate this one).

Money: AED is USD-pegged (3.6725 since 1997-11) — the peg is the FX rate.
Area: DLD publishes built-up area in sqft → sqm (×0.09290304).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from packages.core.ids import make_global_id
from packages.core.money import to_usd_cents
from packages.core.schemas import (
    DataSourceRef,
    Property,
    PropertyType,
    Transaction,
    TransactionType,
)

SOURCE_DLD_TRANSACTIONS = "DLD_OPEN_TRANSACTIONS"

SQFT_TO_SQM = Decimal("0.09290304")
# AED/USD peg, fixed by the UAE Central Bank since November 1997.
AED_USD_PEG = Decimal("1") / Decimal("3.6725")

# procedure_name → (TransactionType, is_offplan)
PROCEDURE_MAP = {
    "Sell": (TransactionType.SALE, False),
    "Delayed Sell": (TransactionType.SALE, False),
    "Sell - Pre registration": (TransactionType.SALE, True),  # off-plan resale
    "Grant": (TransactionType.GIFT, False),
}

# bedrooms label → canonical BR code (append-only; NEVER remap existing keys)
BEDROOM_CODES = {
    "Studio": "0BR",
    "PENTHOUSE": "PH",
    "Single Room": "SR",
}
_BR_PATTERN = re.compile(r"^(\d+)\s*B/R$")


@dataclass(frozen=True)
class RawDldTransaction:
    """One row of the DLD open transactions dataset (mirror parquet or gateway)."""

    procedure_name: str
    instance_date: str  # DD-MM-YYYY
    property_type: str
    property_sub_type: str
    property_usage: str
    area_name: str
    building_name: str
    master_project: str
    bedrooms: str
    parkings: str
    built_up_area_sqft: str
    selling_price_aed: str
    raw: dict = field(default_factory=dict)


def slugify(text: str) -> str:
    """Deterministic ASCII slug: NFKD → uppercase → [A-Z0-9] runs joined by '-'.

    Part of the canonical ID rule — NEVER change.
    """
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    parts = re.findall(r"[A-Z0-9]+", text.upper())
    return "-".join(parts)


def bedroom_code(label: str) -> str:
    """'1 B/R' → '1BR', 'Studio' → '0BR', 'PENTHOUSE' → 'PH', unknown → 'X'."""
    label = (label or "").strip()
    if label in BEDROOM_CODES:
        return BEDROOM_CODES[label]
    m = _BR_PATTERN.match(label)
    return f"{m.group(1)}BR" if m else "X"


def bua_sqm(raw: RawDldTransaction) -> Decimal:
    return (Decimal(str(raw.built_up_area_sqft)) * SQFT_TO_SQM).quantize(Decimal("0.01"))


def canonical_local_id(raw: RawDldTransaction) -> str:
    """Deterministic canonical ID for a Dubai unit class."""
    sqm_x100 = int(bua_sqm(raw) * 100)
    return (
        f"AE-DXB-{slugify(raw.area_name)}-{slugify(raw.building_name)}"
        f"-{bedroom_code(raw.bedrooms)}-{sqm_x100}"
    )


def _instance_date(raw: RawDldTransaction) -> date:
    d, m, y = raw.instance_date.strip().split("-")
    return date(int(y), int(m), int(d))


def source_record_id(raw: RawDldTransaction) -> str:
    """Idempotency key: unit class + deal date + amount (open data has no tx id)."""
    dt = _instance_date(raw)
    amount = str(int(Decimal(str(raw.selling_price_aed))))
    return f"{canonical_local_id(raw)}@{dt:%Y%m%d}#{amount}"


def to_transaction(raw: RawDldTransaction, ingested_at: datetime | None = None) -> Transaction:
    """Normalize one DLD sale record. AED→USD via the peg."""
    tx_type, _ = PROCEDURE_MAP[raw.procedure_name.strip()]
    aed = Decimal(str(raw.selling_price_aed))
    return Transaction(
        global_id=make_global_id("AE", canonical_local_id(raw)),
        transaction_type=tx_type,
        transaction_date=_instance_date(raw),
        contract_date=_instance_date(raw),
        price_usd_cents=to_usd_cents(aed, AED_USD_PEG),
        price_original_amount=aed,
        price_original_currency="AED",
        fx_rate_at_date=AED_USD_PEG,
        is_verified=True,
        # off-plan sales are stored but excluded from analysis (docs/06 §9)
        is_cancelled=False,
        source=SOURCE_DLD_TRANSACTIONS,
        source_record_id=source_record_id(raw),
        raw_payload=raw.raw,
        ingested_at=ingested_at or datetime.now(UTC),
    )


def to_property(raw: RawDldTransaction, ingested_at: datetime | None = None) -> Property:
    now = ingested_at or datetime.now(UTC)
    canonical = canonical_local_id(raw)
    _, is_offplan = PROCEDURE_MAP[raw.procedure_name.strip()]
    address = ", ".join(p for p in [raw.building_name.strip(), raw.area_name.strip(), "Dubai"] if p)
    parkings = raw.parkings.strip() if isinstance(raw.parkings, str) else str(raw.parkings)
    return Property(
        global_id=make_global_id("AE", canonical),
        country_code="AE",
        local_id=f"{slugify(raw.area_name)}/{slugify(raw.building_name)}",
        local_id_canonical=canonical,
        property_type=PropertyType.APARTMENT,
        property_subtype=raw.property_sub_type.strip() or None,
        address_normalized=address,
        address_original=address,
        admin_level_1="Dubai",
        admin_level_2=raw.area_name.strip() or None,
        net_area_sqm=bua_sqm(raw),  # DLD built-up area (unit gross) — documented
        parking_spaces=int(parkings) if parkings.isdigit() else None,
        complex_id=f"AE-DXB-{slugify(raw.area_name)}-{slugify(raw.building_name)}",
        complex_name=raw.building_name.strip() or None,
        is_offplan=is_offplan,
        community_id=slugify(raw.master_project) or None,
        community_name=raw.master_project.strip() or None,
        data_sources=[
            DataSourceRef(
                source=SOURCE_DLD_TRANSACTIONS,
                fetched_at=now,
                raw_id=source_record_id(raw),
            )
        ],
        created_at=now,
        updated_at=now,
    )
