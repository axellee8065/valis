"""POST /v1/valuation — AVM prediction endpoint (docs/03 §5.2).

P95 latency target < 200ms; the model lives in process memory.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from packages.avm.confidence import (
    ConfidenceInputs,
    confidence_score,
    confidence_tier,
    to_bps,
)
from packages.core.schemas import GLOBAL_ID_PATTERN

router = APIRouter(tags=["valuation"])


class ValuationRequest(BaseModel):
    global_id: str = Field(..., pattern=GLOBAL_ID_PATTERN)
    as_of: datetime | None = None


class ValuationResponse(BaseModel):
    global_id: str
    model_id: str
    value_usd_cents: int
    ci_lower_usd_cents: int
    ci_upper_usd_cents: int
    confidence_score_bps: int
    confidence_tier: str
    predicted_at: datetime


# Populated by the model-loading lifecycle once a trained artifact exists.
# Kept module-level so scripts/predict_batch and the API share one instance.
ACTIVE_MODEL = None  # set by packages.api.model_loader (M3+)


@router.post("/valuation", response_model=ValuationResponse)
async def create_valuation(req: ValuationRequest) -> ValuationResponse:
    if ACTIVE_MODEL is None:
        raise HTTPException(
            status_code=503,
            detail="No active AVM model. Train one with scripts/train_avm.py and activate it.",
        )
    prediction = ACTIVE_MODEL.predict(req.global_id, as_of=req.as_of)
    if prediction is None:
        raise HTTPException(
            status_code=404, detail="Property unknown or model refused (low confidence)"
        )

    score = confidence_score(
        ConfidenceInputs(
            same_complex_transactions_365d=prediction.liquidity,
            days_since_last_complex_tx=prediction.days_since_last_tx,
            model_prediction_std=prediction.rel_std,
            segment_backtest_accuracy=prediction.segment_ppe10,
        )
    )
    return ValuationResponse(
        global_id=req.global_id,
        model_id=prediction.model_id,
        value_usd_cents=prediction.value_usd_cents,
        ci_lower_usd_cents=prediction.ci_lower_usd_cents,
        ci_upper_usd_cents=prediction.ci_upper_usd_cents,
        confidence_score_bps=to_bps(score),
        confidence_tier=confidence_tier(score),
        predicted_at=datetime.now(UTC),
    )
