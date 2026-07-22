"""GET /v1/properties — normalized property lookup."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import PropertyRow, TransactionRow
from packages.core.db.session import get_session

router = APIRouter(tags=["properties"])


@router.get("/properties/{global_id}")
async def get_property(global_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    row = await session.get(PropertyRow, global_id)
    if row is None:
        raise HTTPException(status_code=404, detail="property not found")
    return {c.name: getattr(row, c.name) for c in PropertyRow.__table__.columns}


@router.get("/properties/{global_id}/transactions")
async def get_property_transactions(
    global_id: str,
    include_cancelled: bool = False,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = (
        select(TransactionRow)
        .where(TransactionRow.global_id == global_id)
        .order_by(TransactionRow.transaction_date.desc())
        .limit(min(limit, 1000))
    )
    if not include_cancelled:
        stmt = stmt.where(TransactionRow.is_cancelled.is_(False))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            c.name: getattr(r, c.name)
            for c in TransactionRow.__table__.columns
            if c.name != "raw_payload"
        }
        for r in rows
    ]
