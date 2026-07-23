"""GET /v1/stats — live protocol aggregates for the public site."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import (
    AttestationRow,
    PropertyRow,
    TransactionRow,
)
from packages.core.db.session import get_session

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_session)) -> dict:
    tx = await session.scalar(select(func.count()).select_from(TransactionRow))
    units = await session.scalar(select(func.count()).select_from(PropertyRow))
    complexes = await session.scalar(select(func.count(func.distinct(PropertyRow.complex_id))))
    atts = await session.scalar(
        select(func.count()).select_from(AttestationRow).where(AttestationRow.is_active)
    )
    latest = await session.scalar(
        select(AttestationRow.model_id).order_by(AttestationRow.issued_at.desc()).limit(1)
    )
    first_date = await session.scalar(select(func.min(TransactionRow.transaction_date)))
    last_date = await session.scalar(select(func.max(TransactionRow.transaction_date)))
    return {
        "transactions": tx,
        "properties": units,
        "complexes": complexes,
        "active_attestations": atts,
        "latest_model_id": latest,
        "data_range": {"from": str(first_date), "to": str(last_date)},
        "network": "sui:testnet",
    }


@router.get("/attestations")
async def list_attestations(
    limit: int = 12, session: AsyncSession = Depends(get_session)
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
    rows = (await session.execute(stmt)).all()
    return [dict(r._mapping) for r in rows]
