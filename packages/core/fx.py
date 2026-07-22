"""FX rate lookup for money normalization (docs/02 §5.3).

Rates are stored per (currency, date) in the fx_rates table. Weekends and
holidays have no published rate, so lookups fall back to the most recent
PRIOR business day — never a future rate (temporal safety).
"""

from bisect import bisect_right
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.db.models import FxRateRow

MAX_FALLBACK_DAYS = 7  # beyond this the rate is considered stale → None


class FxProvider:
    """In-memory FX lookup, loaded once per batch run."""

    def __init__(self, rates: dict[date, Decimal]):
        # sorted date list enables prior-business-day fallback via bisect
        self._dates: list[date] = sorted(rates)
        self._rates = rates

    @classmethod
    async def load(cls, session: AsyncSession, currency: str) -> "FxProvider":
        stmt = select(FxRateRow.rate_date, FxRateRow.usd_per_unit).where(
            FxRateRow.currency == currency.upper()
        )
        rows = (await session.execute(stmt)).all()
        return cls({r.rate_date: Decimal(r.usd_per_unit) for r in rows})

    def rate_at(self, d: date | str) -> Decimal | None:
        """USD per 1 unit at date d, falling back ≤ MAX_FALLBACK_DAYS backward."""
        if isinstance(d, str):
            d = date.fromisoformat(d)
        if not self._dates:
            return None
        idx = bisect_right(self._dates, d) - 1
        if idx < 0:
            return None
        found = self._dates[idx]
        if (d - found).days > MAX_FALLBACK_DAYS:
            return None
        return self._rates[found]

    def __len__(self) -> int:
        return len(self._dates)

    def __call__(self, d: date | str) -> Decimal | None:
        """Adapter-facing callable form (KoreaAdapter.set_fx_provider)."""
        return self.rate_at(d)
