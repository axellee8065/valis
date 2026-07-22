"""Country adapter contract (docs/02-korea-adapter.md §1, docs/06 §3.2).

The core protocol only speaks the normalized schema; adapters translate
country-specific raw sources into it.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from packages.core.schemas import GovernmentValuation, Property, Transaction


class CountryAdapter(ABC):
    country_code: str  # "KR", "AE", ...

    @abstractmethod
    def fetch_transactions(self, region_code: str, year_month: str) -> AsyncIterator[Transaction]:
        """Fetch normalized transactions for a region+month."""

    @abstractmethod
    async def fetch_property(self, local_id: str) -> Property:
        """Fetch a single property by local ID."""

    @abstractmethod
    async def fetch_government_valuation(self, local_id: str, year: int) -> GovernmentValuation:
        """Fetch government-assessed value."""

    @abstractmethod
    def normalize_local_id(self, raw_id: str) -> str:
        """Canonicalize local ID for global_id generation."""

    @abstractmethod
    def normalize_address(self, raw_address: str) -> tuple[str, str]:
        """Returns (normalized_english, original)."""

    @abstractmethod
    async def verify_property_exists(self, local_id: str) -> bool:
        """Check via government registry."""

    # --- Optional extensions for UAE (docs/06 §3.2). KR raises NotImplementedError. ---

    def fetch_offplan_registry(self, developer: str) -> AsyncIterator[Property]:
        """Off-plan property registry (UAE)."""
        raise NotImplementedError

    def fetch_lease_yields(self, region: str, ymd: str) -> AsyncIterator[dict]:
        """Rental yield data for income-approach models (UAE)."""
        raise NotImplementedError
