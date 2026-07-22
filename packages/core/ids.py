"""Deterministic global property ID generation (docs/01-data-schema.md §5).

WARNING: `local_id_canonical` rules are defined per-country by adapters and must
NEVER change. Changing them changes every global_id and breaks the link with
on-chain attestations.
"""

import hashlib


def make_global_id(country_code: str, local_id_canonical: str) -> str:
    """sha256("{COUNTRY}:{canonical}") hex, 0x-prefixed.

    - country_code: ISO 3166-1 alpha-2, uppercased here for safety
    - local_id_canonical: adapter-normalized canonical form
      (whitespace stripped, uppercase, delimiter normalized — adapter's job)
    """
    payload = f"{country_code.upper()}:{local_id_canonical}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"0x{digest}"


def global_id_bytes(global_id: str) -> bytes:
    """32-byte form used on-chain (Move `vector<u8>`)."""
    if not global_id.startswith("0x") or len(global_id) != 66:
        raise ValueError(f"invalid global_id: {global_id!r}")
    return bytes.fromhex(global_id[2:])
