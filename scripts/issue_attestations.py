"""Batch attestation issuance (docs/05 §4.2).

Flow: query properties needing attestation → predict → upload report →
register (if needed) → issue → publish to feed → store digests in DB.

Requires a trained active model and Sui env vars (SUI_PACKAGE_ID etc.).
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update

from packages.attestation.issuer import TX_PER_SECOND, AttestationIssuer
from packages.core.config import get_settings
from packages.core.db.models import AttestationRow
from packages.core.db.session import get_session_factory

log = structlog.get_logger()

VALIDITY_DAYS = 90


async def find_expiring(session, within_days: int = 7) -> list[AttestationRow]:
    cutoff = datetime.now(UTC) + timedelta(days=within_days)
    stmt = select(AttestationRow).where(
        AttestationRow.is_active.is_(True),
        AttestationRow.expires_at <= cutoff,
    )
    return list((await session.execute(stmt)).scalars())


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.sui_package_id and not args.dry_run:
        raise SystemExit("SUI_PACKAGE_ID not configured — deploy contracts first (docs/05 §5)")

    issuer = AttestationIssuer(settings)  # noqa: F841 — used once model loader lands (M5)
    session_factory = get_session_factory()

    async with session_factory() as session:
        expiring = await find_expiring(session)
        log.info("attestations_expiring", count=len(expiring))

        issued = 0
        for row in expiring[: args.limit]:
            if args.dry_run:
                log.info("dry_run_skip", global_id=row.global_id)
                continue
            # Re-prediction + report upload wiring lands with the active-model
            # loader (M5). Until then this marks expired rows inactive.
            if row.expires_at <= datetime.now(UTC):
                await session.execute(
                    update(AttestationRow)
                    .where(AttestationRow.id == row.id)
                    .values(is_active=False)
                )
            issued += 1
            await asyncio.sleep(1 / TX_PER_SECOND)
        await session.commit()
    log.info("attestation_batch_done", processed=issued)


if __name__ == "__main__":
    asyncio.run(main())
