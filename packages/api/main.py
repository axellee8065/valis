"""Valis API Gateway (FastAPI, deployed on Railway).

Endpoints: health, valuation, properties, attestations.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from packages.api.routes import attestations, health, properties, stats, valuation
from packages.core.config import get_settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    log.info("api_start", environment=settings.environment)
    yield
    log.info("api_stop")


app = FastAPI(
    title="Valis Protocol API",
    version="0.1.0",
    description="On-chain real estate valuation infrastructure",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(valuation.router, prefix="/v1")
app.include_router(properties.router, prefix="/v1")
app.include_router(attestations.router, prefix="/v1")
app.include_router(stats.router, prefix="/v1")
