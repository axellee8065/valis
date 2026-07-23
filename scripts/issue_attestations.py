"""Batch attestation issuance (docs/05 §4.2).

Selects AUTO_ISSUE-grade holdout properties (confidence ≥ threshold), then per
property runs ONE on-chain transaction via valis::batch::register_and_attest
(register + mint + feed-publish bundled). Records results in the DB.

Idempotent: properties with an existing active attestation are skipped; an
on-chain EPropertyAlreadyRegistered abort is logged and skipped.

Usage:
    python scripts/issue_attestations.py --limit 100
    python scripts/issue_attestations.py --limit 10 --dry-run
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import structlog

from packages.avm.confidence import ConfidenceInputs, confidence_score, to_bps
from packages.core.config import get_settings
from packages.core.db.session import get_session_factory

log = structlog.get_logger()

SUI_EXE = os.path.expandvars(r"%USERPROFILE%\.sui-cli\sui.exe")
MODEL_ID = "avm-kr-seoul-apt-v3-20260723-14cf632"
PREDICTIONS = Path(f"reports/backtest_{MODEL_ID}/predictions.parquet")
CONFORMAL = Path(f"models/{MODEL_ID}/conformal.json")
REPORT_MD = Path(f"reports/backtest_{MODEL_ID}/report.md")
VALIDITY_MS = 90 * 24 * 3600 * 1000  # 90 days
GAS_BUDGET = 40_000_000
MIN_BALANCE_MIST = 100_000_000  # stop below 0.1 SUI


def load_candidates(min_confidence: float) -> pd.DataFrame:
    df = pd.read_parquet(PREDICTIONS)
    cal = json.loads(CONFORMAL.read_text(encoding="utf-8"))

    def seg(row):
        return cal["segments"].get(row["admin_level_2"], cal["global"])

    # one attestation per property: keep the most recent transaction row
    df = df.sort_values("transaction_date").drop_duplicates("global_id", keep="last")

    rows = []
    for _, r in df.iterrows():
        s = seg(r)
        conf = confidence_score(
            ConfidenceInputs(
                same_complex_transactions_365d=int(r["complex_transaction_count_365d"] or 0),
                days_since_last_complex_tx=float(
                    r["complex_last_transaction_days_ago"]
                    if pd.notna(r["complex_last_transaction_days_ago"])
                    else 999
                ),
                model_prediction_std=s["rel_std"],
                segment_backtest_accuracy=s["ppe10"],
            )
        )
        if conf < min_confidence:
            continue
        rows.append(
            {
                "global_id": r["global_id"],
                "admin_level_2": r["admin_level_2"] or "",
                "admin_level_3": r["admin_level_3"] or "",
                "net_area_sqm": float(r["net_area_sqm"]),
                "built_year": int(r["built_year"]) if pd.notna(r["built_year"]) else 0,
                "floor_number": int(r["floor_number"]) if pd.notna(r["floor_number"]) else 0,
                "pred_krw": float(r["prediction"]),
                "q_lo": s["q_lo"],
                "q_hi": s["q_hi"],
                "confidence": conf,
            }
        )
    out = pd.DataFrame(rows).sort_values("confidence", ascending=False)
    log.info("candidates_selected", total=len(out), min_confidence=min_confidence)
    return out


def sui_call(settings, c: dict, canonical: str, fx: float, report_hash: str) -> dict:
    """One register_and_attest transaction. Returns parsed JSON result."""
    to_cents = lambda krw: round(krw * fx * 100)  # noqa: E731
    value = to_cents(c["pred_krw"])
    args = [
        # caps & shared objects
        os.environ.get(
            "KR_ADAPTER_CAP", "0x023de0bced71fe309887ae5124e9abbcaa618210c5f33cd67da61300feea4690"
        ),
        settings.sui_adapter_registry_id,
        settings.sui_property_index_id,
        settings.sui_valuation_feed_id,
        settings.sui_issuer_cap_id,
        # property
        c["global_id"],
        canonical,
        "APARTMENT",
        str(900_000_000),  # lat offset-encoded 0 (geocoding: M6)
        str(1_800_000_000),
        "서울특별시",
        c["admin_level_2"],
        c["admin_level_3"],
        str(round(c["net_area_sqm"] * 100)),
        str(c["built_year"]),
        "0",
        str(max(c["floor_number"], 0)),
        # attestation
        str(value),
        str(to_cents(c["pred_krw"] * math.exp(c["q_lo"]))),
        str(to_cents(c["pred_krw"] * math.exp(c["q_hi"]))),
        str(to_bps(c["confidence"])),
        "0",  # METHOD_AVM
        MODEL_ID,
        f"https://github.com/axellee/valis/reports/{MODEL_ID}",
        report_hash,
        str(VALIDITY_MS),
        settings.sui_clock_id,
        "0xd37d93cf8226e38399e5a8a01d485a65dc632d0854bc51c16cd1b6c7eb6897dd",
    ]
    cmd = [
        SUI_EXE,
        "client",
        "call",
        "--package",
        settings.sui_package_id,
        "--module",
        "batch",
        "--function",
        "register_and_attest",
        "--gas-budget",
        str(GAS_BUDGET),
        "--json",
        "--args",
        *args,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip().splitlines()[-1] if proc.stderr else "sui call failed"
        )
    return json.loads(proc.stdout)


def get_balance_mist() -> int:
    proc = subprocess.run(
        [SUI_EXE, "client", "gas", "--json"], capture_output=True, text=True, encoding="utf-8"
    )
    coins = json.loads(proc.stdout)
    return sum(int(c["mistBalance"]) for c in coins)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    report_hash = "0x" + hashlib.sha256(REPORT_MD.read_bytes()).hexdigest()
    candidates = load_candidates(args.min_confidence)

    session_factory = get_session_factory()
    async with session_factory() as session:
        from sqlalchemy import text

        done = {
            r[0]
            for r in await session.execute(
                text("SELECT global_id FROM appraisal_attestations WHERE is_active")
            )
        }
        fx = (
            await session.execute(
                text(
                    "SELECT usd_per_unit FROM fx_rates WHERE currency='KRW' ORDER BY rate_date DESC LIMIT 1"
                )
            )
        ).scalar_one()
        candidates = candidates[~candidates["global_id"].isin(done)].head(args.limit)
        canon_rows = await session.execute(
            text(
                "SELECT global_id, local_id_canonical FROM properties WHERE global_id = ANY(:ids)"
            ),
            {"ids": list(candidates["global_id"])},
        )
        canonical_map = dict(canon_rows.all())

    log.info("issuing", count=len(candidates), fx=float(fx), dry_run=args.dry_run)
    if args.dry_run:
        print(candidates[["global_id", "admin_level_2", "pred_krw", "confidence"]].head(20))
        return

    issued, failed, gas_spent = 0, 0, 0
    async with session_factory() as session:
        from sqlalchemy import text

        for _, c in candidates.iterrows():
            if get_balance_mist() < MIN_BALANCE_MIST:
                log.warning("gas_low_stopping", issued=issued)
                break
            try:
                result = sui_call(
                    settings, c, canonical_map[c["global_id"]], float(fx), report_hash
                )
                status = result["effects"]["status"]["status"]
                if status != "success":
                    raise RuntimeError(result["effects"]["status"].get("error", "tx failed"))
                att_id = next(
                    ch["objectId"]
                    for ch in result.get("objectChanges", [])
                    if ch["type"] == "created"
                    and "AppraisalAttestation" in ch.get("objectType", "")
                )
                gas = result["effects"]["gasUsed"]
                tx_gas = (
                    int(gas["computationCost"])
                    + int(gas["storageCost"])
                    - int(gas["storageRebate"])
                )
                gas_spent += tx_gas

                now = datetime.now(UTC)
                await session.execute(
                    text(
                        """INSERT INTO appraisal_attestations
                           (attestation_uid, global_id, value_usd_cents, confidence_score_bps,
                            ci_lower_usd_cents, ci_upper_usd_cents, method, model_id, report_hash,
                            issued_at, expires_at, sui_tx_digest, is_active)
                           VALUES (:uid, :gid, :v, :c, :lo, :hi, 'AVM', :mid, :rh, :ia, :ea, :d, true)"""
                    ),
                    {
                        "uid": att_id,
                        "gid": c["global_id"],
                        "v": round(c["pred_krw"] * float(fx) * 100),
                        "c": to_bps(c["confidence"]),
                        "lo": round(c["pred_krw"] * math.exp(c["q_lo"]) * float(fx) * 100),
                        "hi": round(c["pred_krw"] * math.exp(c["q_hi"]) * float(fx) * 100),
                        "mid": MODEL_ID,
                        "rh": report_hash,
                        "ia": now,
                        "ea": now + timedelta(milliseconds=VALIDITY_MS),
                        "d": result["digest"],
                    },
                )
                await session.commit()
                issued += 1
                if issued % 10 == 0:
                    log.info("progress", issued=issued, gas_sui=round(gas_spent / 1e9, 3))
            except Exception as exc:
                failed += 1
                log.error("issue_failed", global_id=c["global_id"][:18], error=str(exc)[:200])
            await asyncio.sleep(0.1)  # testnet courtesy (docs/05 §4.2)

    avg = gas_spent / issued / 1e9 if issued else 0
    log.info(
        "batch_done",
        issued=issued,
        failed=failed,
        total_gas_sui=round(gas_spent / 1e9, 3),
        avg_gas_sui=round(avg, 5),
    )
    print(f"\nissued: {issued}  failed: {failed}")
    print(f"gas: {gas_spent / 1e9:.3f} SUI total, {avg:.5f} SUI/attestation")
    if avg:
        print(f"10,000 attestations ≈ {avg * 10_000:.0f} SUI (testnet)")


if __name__ == "__main__":
    asyncio.run(main())
