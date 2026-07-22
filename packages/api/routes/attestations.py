"""GET /v1/attestations — attestation records issued by the protocol."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import AttestationRow
from packages.core.db.session import get_session

router = APIRouter(tags=["attestations"])


def _row_to_dict(r: AttestationRow) -> dict:
    return {c.name: getattr(r, c.name) for c in AttestationRow.__table__.columns}


@router.get("/attestations/{attestation_uid}")
async def get_attestation(
    attestation_uid: str, session: AsyncSession = Depends(get_session)
) -> dict:
    stmt = select(AttestationRow).where(AttestationRow.attestation_uid == attestation_uid)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="attestation not found")
    return _row_to_dict(row)


@router.get("/properties/{global_id}/attestations")
async def list_property_attestations(
    global_id: str,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = (
        select(AttestationRow)
        .where(AttestationRow.global_id == global_id)
        .order_by(AttestationRow.issued_at.desc())
    )
    if active_only:
        stmt = stmt.where(AttestationRow.is_active.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]
