"""KoreaAdapter — implements the CountryAdapter contract for KR."""

from collections.abc import AsyncIterator
from decimal import Decimal

from packages.adapter_kr.geo.address_normalizer import normalize_address
from packages.adapter_kr.kongsi.client import KongsiClient
from packages.adapter_kr.kongsi.normalizer import parse_pnu
from packages.adapter_kr.molit.client import MolitClient
from packages.adapter_kr.molit.normalizer import to_transaction
from packages.adapter_kr.seum.client import SeumClient
from packages.adapter_kr.seum.normalizer import to_property_enrichment
from packages.core.adapter import CountryAdapter
from packages.core.config import get_settings
from packages.core.schemas import GovernmentValuation, Property, Transaction


class KoreaAdapter(CountryAdapter):
    country_code = "KR"

    def __init__(
        self,
        molit_client: MolitClient | None = None,
        kongsi_client: KongsiClient | None = None,
        seum_client: SeumClient | None = None,
    ):
        settings = get_settings()
        self._molit = molit_client or MolitClient(settings.molit_api_key)
        self._kongsi = kongsi_client or KongsiClient(
            settings.kongsi_api_key, api_domain=settings.kongsi_api_domain
        )
        self._seum = seum_client or SeumClient(settings.seum_api_key)
        self._fx_provider = None  # set via set_fx_provider (FxProvider is callable)

    def set_fx_provider(self, provider) -> None:
        """provider: callable(date|str) -> Decimal | None (KRW→USD rate)."""
        self._fx_provider = provider

    async def fetch_transactions(
        self, region_code: str, year_month: str
    ) -> AsyncIterator[Transaction]:
        """region_code: 5-digit LAWD_CD; year_month: YYYYMM."""
        async for raw in self._molit.fetch_apt_trades(region_code, year_month):
            fx: Decimal | None = None
            if self._fx_provider is not None:
                fx = self._fx_provider(
                    f"{raw.deal_year}-{int(raw.deal_month):02d}-{int(raw.deal_day):02d}"
                )
            yield to_transaction(raw, fx_krw_usd=fx)

    async def fetch_building_register(self, pnu: str) -> list[dict]:
        """세움터 표제부 enrichment for a parcel. Returns partial-update dicts
        (units_in_building, floors_total, ...) — one per building on the parcel."""
        parts = parse_pnu(pnu)
        records = await self._seum.fetch_title_info(
            sgg_cd=parts["sgg_cd"],
            umd_cd=parts["umd_cd"],
            bun=parts["bonbun"],
            ji=parts["bubun"],
        )
        return [to_property_enrichment(r) for r in records]

    async def fetch_official_prices(self, pnu: str, year: int) -> list[dict]:
        """공시가격 raw records for a parcel+year (unit-level global_id matching
        happens at the ingestion layer where the property master is available)."""
        return await self._kongsi.fetch_by_pnu(pnu, year)

    async def fetch_property(self, local_id: str) -> Property:
        # Full Property assembly needs MOLIT + 세움터 + geocoding joined by PNU;
        # the property master is built via scripts/ingest_molit.py instead.
        raise NotImplementedError("use fetch_building_register + ingestion pipeline")

    async def fetch_government_valuation(self, local_id: str, year: int) -> GovernmentValuation:
        # Unit-level matching (dongNm/hoNm → canonical) lives in the ingestion
        # layer; use fetch_official_prices for the raw records.
        raise NotImplementedError("use fetch_official_prices + ingestion pipeline")

    def normalize_local_id(self, raw_id: str) -> str:
        return raw_id.strip().upper().replace(" ", "")

    def normalize_address(self, raw_address: str) -> tuple[str, str]:
        return normalize_address(raw_address)

    async def verify_property_exists(self, local_id: str) -> bool:
        """A parcel exists if the building register returns any 표제부 record."""
        try:
            records = await self.fetch_building_register(local_id)
        except Exception:
            return False
        return len(records) > 0

    async def aclose(self) -> None:
        await self._molit.aclose()
        await self._kongsi.aclose()
        await self._seum.aclose()
