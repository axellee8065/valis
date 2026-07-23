"""GET /v1/stats — live protocol aggregates for the public site.

Both endpoints accept ?country=KR|AE (ISO alpha-2). Without it they aggregate
across all markets — the demo site pins country=AE (docs/08 demo mode).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import (
    AttestationRow,
    PropertyRow,
    TransactionRow,
)
from packages.core.db.session import get_session

router = APIRouter(tags=["stats"])


def _country(country: str | None) -> str | None:
    return country.upper() if country and len(country) == 2 else None


@router.get("/stats")
async def get_stats(
    country: str | None = Query(default=None, max_length=2),
    session: AsyncSession = Depends(get_session),
) -> dict:
    cc = _country(country)

    tx_q = select(func.count()).select_from(TransactionRow)
    prop_q = select(func.count()).select_from(PropertyRow)
    cx_q = select(func.count(func.distinct(PropertyRow.complex_id)))
    att_q = select(func.count()).select_from(AttestationRow).where(AttestationRow.is_active)
    model_q = select(AttestationRow.model_id).order_by(AttestationRow.issued_at.desc())
    from_q = select(func.min(TransactionRow.transaction_date))
    to_q = select(func.max(TransactionRow.transaction_date))

    if cc:
        prop_ids = select(PropertyRow.global_id).where(PropertyRow.country_code == cc)
        tx_q = tx_q.where(TransactionRow.global_id.in_(prop_ids))
        prop_q = prop_q.where(PropertyRow.country_code == cc)
        cx_q = cx_q.where(PropertyRow.country_code == cc)
        att_q = att_q.where(AttestationRow.global_id.in_(prop_ids))
        model_q = model_q.where(AttestationRow.global_id.in_(prop_ids))
        from_q = from_q.where(TransactionRow.global_id.in_(prop_ids))
        to_q = to_q.where(TransactionRow.global_id.in_(prop_ids))

    return {
        "country": cc or "ALL",
        "transactions": await session.scalar(tx_q),
        "properties": await session.scalar(prop_q),
        "complexes": await session.scalar(cx_q),
        "active_attestations": await session.scalar(att_q),
        "latest_model_id": await session.scalar(model_q.limit(1)),
        "data_range": {
            "from": str(await session.scalar(from_q)),
            "to": str(await session.scalar(to_q)),
        },
        "network": "sui:testnet",
    }


@router.get("/attestations")
async def list_attestations(
    limit: int = 12,
    country: str | None = Query(default=None, max_length=2),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Most recent active attestations (for the public site's live table)."""
    stmt = (
        select(
            AttestationRow.attestation_uid,
            AttestationRow.global_id,
            AttestationRow.value_usd_cents,
            AttestationRow.confidence_score_bps,
            AttestationRow.ci_lower_usd_cents,
            AttestationRow.ci_upper_usd_cents,
            AttestationRow.model_id,
            AttestationRow.issued_at,
            AttestationRow.sui_tx_digest,
            PropertyRow.admin_level_2,
            PropertyRow.net_area_sqm,
            PropertyRow.complex_name,
        )
        .join(PropertyRow, PropertyRow.global_id == AttestationRow.global_id)
        .where(AttestationRow.is_active)
        .order_by(AttestationRow.issued_at.desc())
        .limit(min(limit, 50))
    )
    cc = _country(country)
    if cc:
        stmt = stmt.where(PropertyRow.country_code == cc)
    rows = (await session.execute(stmt)).all()
    return [dict(r._mapping) for r in rows]
