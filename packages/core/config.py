"""Central settings — loaded from environment (.env locally, Railway secrets in prod)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Korea public data
    molit_api_key: str = ""
    kongsi_api_key: str = ""
    seum_api_key: str = ""
    seoul_open_data_key: str = ""
    bok_ecos_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://valis:valis_dev@localhost:5432/valis"

    # Object storage (local: MinIO, prod: R2)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "valis"
    s3_secret_access_key: str = "valis_dev_secret"
    s3_bucket_raw: str = "valis-raw"
    s3_bucket_reports: str = "valis-reports"

    # Sui
    sui_network: str = "testnet"
    sui_rpc_url: str = "https://fullnode.testnet.sui.io:443"
    sui_package_id: str = ""
    sui_adapter_registry_id: str = ""
    sui_property_index_id: str = ""
    sui_valuation_feed_id: str = ""
    sui_issuer_cap_id: str = ""
    sui_admin_cap_id: str = ""
    sui_issuer_privkey: str = ""
    sui_clock_id: str = "0x6"

    # Ops
    sentry_dsn: str = ""
    log_level: str = "INFO"
    environment: str = "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
