"""Batch attestation issuance for Dubai (AE) unit classes (docs/08).

Same single-tx pipeline as scripts/issue_attestations.py, adapted for AE:
values are already USD (AED peg applied at ingestion), admin_1 = "Dubai",
identity = unit class. Requires the AE CountryAdapterCap (AE_ADAPTER_CAP env
or .env) registered on-chain first.

Usage:
    python scripts/issue_attestations_ae.py --model-id <id> --limit 10
    python scripts/issue_attestations_ae.py --model-id <id> --limit 5 --dry-run
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
from sqlalchemy import text

from packages.avm.confidence import to_bps
from packages.core.config import get_settings
from packages.core.db.session import get_session_factory

log = structlog.get_logger()

SUI_EXE = os.path.expandvars(r"%USERPROFILE%\.sui-cli\sui.exe")
VALIDITY_MS = 90 * 24 * 3600 * 1000
GAS_BUDGET = 40_000_000
MIN_BALANCE_MIST = 60_000_000  # keep headroom for the sukuk demo txs
DEPLOYER = "0xd37d93cf8226e38399e5a8a01d485a65dc632d0854bc51c16cd1b6c7eb6897dd"


def sui_call(settings, ae_cap: str, c: dict, model_id: str, report_hash: str) -> dict:
    value = round(c["value_now"] * 100)
    args = [
        ae_cap,
        settings.sui_adapter_registry_id,
        settings.sui_property_index_id,
        settings.sui_valuation_feed_id,
        settings.sui_issuer_cap_id,
        c["global_id"],
        c["local_id_canonical"],
        "APARTMENT",
        str(900_000_000),  # lat/lng offset-encoded 0 — geocoding pending
        str(1_800_000_000),
        "Dubai",
        c["admin_level_2"] or "",
        c["community_name"] or "",
        str(round(float(c["net_area_sqm"]) * 100)),
        "0",  # built_year not in DLD open data
        "0",
        "0",
        str(value),
        str(round(value * math.exp(c["q_lo"]))),
        str(round(value * math.exp(c["q_hi"]))),
        str(to_bps(c["confidence"])),
        "0",  # METHOD_AVM
        model_id,
        f"https://github.com/axellee8065/valis/tree/main/reports/backtest_{model_id}",
        report_hash,
        str(VALIDITY_MS),
        settings.sui_clock_id,
        DEPLOYER,
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
        raise RuntimeError(proc.stderr.strip().splitlines()[-1] if proc.stderr else "call failed")
    return json.loads(proc.stdout)


def get_balance_mist() -> int:
    proc = subprocess.run(
        [SUI_EXE, "client", "gas", "--json"], capture_output=True, text=True, encoding="utf-8"
    )
    return sum(int(c["mistBalance"]) for c in json.loads(proc.stdout))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    ae_cap = os.environ.get("AE_ADAPTER_CAP", "")
    assert ae_cap, "set AE_ADAPTER_CAP (register_adapter first)"

    reports = Path(f"reports/backtest_{args.model_id}")
    cal = json.loads(Path(f"models/{args.model_id}/conformal.json").read_text())
    report_hash = "0x" + hashlib.sha256((reports / "report.md").read_bytes()).hexdigest()

    df = pd.read_parquet(reports / "candidates.parquet")
    df = df[df["confidence"] >= args.min_confidence].sort_values("confidence", ascending=False)

    def seg(key):
        return cal["segments"].get(key, cal["global"])

    # conformal segments are comp-dispersion buckets (train_avm_ae comp track)
    df["q_lo"] = df["segment"].map(lambda s: seg(s)["q_lo"])
    df["q_hi"] = df["segment"].map(lambda s: seg(s)["q_hi"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        done = {
            r[0]
            for r in await session.execute(
                text("SELECT global_id FROM appraisal_attestations WHERE is_active")
            )
        }
    df = df[~df["global_id"].isin(done)].head(args.limit)

    log.info("issuing", count=len(df), dry_run=args.dry_run)
    if args.dry_run:
        print(
            df[["global_id", "admin_level_2", "complex_name", "value_now", "confidence"]]
            .head(20)
            .to_string()
        )
        return

    issued, failed, gas_spent = 0, 0, 0
    async with session_factory() as session:
        for _, c in df.iterrows():
            if get_balance_mist() < MIN_BALANCE_MIST:
                log.warning("gas_low_stopping", issued=issued)
                break
            try:
                result = sui_call(settings, ae_cap, c, args.model_id, report_hash)
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
                gas_spent += (
                    int(gas["computationCost"])
                    + int(gas["storageCost"])
                    - int(gas["storageRebate"])
                )
                now = datetime.now(UTC)
                value = round(c["value_now"] * 100)
                await session.execute(
                    text("""INSERT INTO appraisal_attestations
                        (attestation_uid, global_id, value_usd_cents, confidence_score_bps,
                         ci_lower_usd_cents, ci_upper_usd_cents, method, model_id, report_hash,
                         issued_at, expires_at, sui_tx_digest, is_active)
                        VALUES (:uid, :gid, :v, :c, :lo, :hi, 'AVM', :mid, :rh,
                                :ia, :ea, :d, true)"""),
                    {
                        "uid": att_id,
                        "gid": c["global_id"],
                        "v": value,
                        "c": to_bps(c["confidence"]),
                        "lo": round(value * math.exp(c["q_lo"])),
                        "hi": round(value * math.exp(c["q_hi"])),
                        "mid": args.model_id,
                        "rh": report_hash,
                        "ia": now,
                        "ea": now + timedelta(milliseconds=VALIDITY_MS),
                        "d": result["digest"],
                    },
                )
                await session.commit()
                issued += 1
                log.info(
                    "issued",
                    n=issued,
                    complex=str(c["complex_name"])[:30],
                    value_usd=round(c["value_now"]),
                )
            except Exception as exc:
                failed += 1
                log.error("issue_failed", gid=c["global_id"][:18], error=str(exc)[:200])
            await asyncio.sleep(0.1)

    print(f"\nissued: {issued}  failed: {failed}  gas: {gas_spent / 1e9:.3f} SUI")


if __name__ == "__main__":
    asyncio.run(main())
