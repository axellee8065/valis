"""On-chain attestation issuer service (docs/05 §4).

Wraps the Sui SDK to register properties and mint AppraisalAttestation objects.
pysui is imported lazily so the rest of the codebase works without Sui deps.

Batch flow (scripts/issue_attestations.py):
    1. Query DB for properties needing attestation (new or expiring)
    2. Run AVM prediction batch
    3. Upload reports to R2/Walrus → (uri, sha256)
    4. register (if needed) → issue → publish_to_feed  — bundled in one PTB
    5. Store sui_tx_digest + attestation_uid in DB
"""

import hashlib
from dataclasses import dataclass

import structlog

from packages.core.config import get_settings
from packages.core.ids import global_id_bytes
from packages.core.schemas import AVMPrediction

log = structlog.get_logger()

# Sui testnet courtesy limit — keep issuance around 5–10 tx/s (docs/05 §4.2)
TX_PER_SECOND = 5

METHOD_CODE = {"AVM": 0, "CONSENSUS": 1, "HYBRID": 2}


@dataclass(frozen=True)
class IssuedAttestation:
    attestation_uid: str
    sui_tx_digest: str


class AttestationIssuer:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from pysui import SuiConfig, SyncClient  # lazy heavy dep

            cfg = SuiConfig.user_config(
                rpc_url=self.settings.sui_rpc_url,
                prv_keys=[self.settings.sui_issuer_privkey],
            )
            self._client = SyncClient(cfg)
        return self._client

    @staticmethod
    def report_hash(report_bytes: bytes) -> bytes:
        return hashlib.sha256(report_bytes).digest()

    def issue_attestation(
        self,
        property_object_id: str,
        prediction: AVMPrediction,
        report_uri: str,
        report_hash_32: bytes,
        validity_ms: int,
        recipient: str,
        method: str = "AVM",
    ) -> IssuedAttestation:
        """Call valis::attestation::issue. Returns object id + tx digest."""
        from pysui.sui.sui_txn import SyncTransaction

        client = self._get_client()
        txn = SyncTransaction(client=client)
        txn.move_call(
            target=f"{self.settings.sui_package_id}::attestation::issue",
            arguments=[
                txn.object(self.settings.sui_issuer_cap_id),
                txn.object(property_object_id),
                prediction.value_usd_cents,
                prediction.ci_lower_usd_cents or prediction.value_usd_cents,
                prediction.ci_upper_usd_cents or prediction.value_usd_cents,
                prediction.confidence_score_bps or 0,
                METHOD_CODE[method],
                list(prediction.model_id.encode()),
                list(report_uri.encode()),
                list(report_hash_32),
                validity_ms,
                txn.object(self.settings.sui_clock_id),
                recipient,
            ],
        )
        result = txn.execute()
        if not result.is_ok():
            raise RuntimeError(f"attestation issue failed: {result.result_string}")
        digest = result.result_data.digest
        created = [
            c.object_id
            for c in result.result_data.effects.created
            if "AppraisalAttestation" in getattr(c, "object_type", "")
        ]
        uid = created[0] if created else ""
        log.info("attestation_issued", digest=digest, uid=uid, global_id=prediction.global_id)
        return IssuedAttestation(attestation_uid=uid, sui_tx_digest=digest)

    def register_property(self, adapter_cap_id: str, prop: dict) -> str:
        """Call valis::property_registry::register. `prop` follows the
        normalized Property schema. Returns tx digest.

        Lat/lng use offset encoding (u64): stored = (deg + offset) * 1e7,
        offset 90 for lat, 180 for lng — Move has no signed integers.
        """
        from pysui.sui.sui_txn import SyncTransaction

        client = self._get_client()
        txn = SyncTransaction(client=client)
        lat_e7 = int((float(prop.get("latitude") or 0) + 90) * 10**7)
        lng_e7 = int((float(prop.get("longitude") or 0) + 180) * 10**7)
        txn.move_call(
            target=f"{self.settings.sui_package_id}::property_registry::register",
            arguments=[
                txn.object(adapter_cap_id),
                txn.object(self.settings.sui_property_index_id),
                list(global_id_bytes(prop["global_id"])),
                list(prop["local_id_canonical"].encode()),
                list(prop["property_type"].encode()),
                lat_e7,
                lng_e7,
                list((prop.get("admin_level_1") or "").encode()),
                list((prop.get("admin_level_2") or "").encode()),
                list((prop.get("admin_level_3") or "").encode()),
                int(float(prop.get("net_area_sqm") or 0) * 100),
                int(prop.get("built_year") or 0),
                int(prop.get("floors_total") or 0),
                int(prop.get("floor_number") or 0),
                txn.object(self.settings.sui_clock_id),
            ],
        )
        result = txn.execute()
        if not result.is_ok():
            raise RuntimeError(f"property register failed: {result.result_string}")
        return result.result_data.digest

    def publish_to_feed(self, attestation_id: str) -> str:
        """Push an attestation to the shared ValuationFeed. Returns tx digest."""
        from pysui.sui.sui_txn import SyncTransaction

        client = self._get_client()
        txn = SyncTransaction(client=client)
        txn.move_call(
            target=f"{self.settings.sui_package_id}::oracle_feed::publish",
            arguments=[
                txn.object(self.settings.sui_valuation_feed_id),
                txn.object(attestation_id),
                txn.object(self.settings.sui_clock_id),
            ],
        )
        result = txn.execute()
        if not result.is_ok():
            raise RuntimeError(f"feed publish failed: {result.result_string}")
        return result.result_data.digest
