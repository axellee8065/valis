"""Model ID scheme and registry helpers (docs/03 §8, docs/06 §3.3).

model_id: avm-{country}-{region}-{property_type}-v{n}-{yyyymmdd}-{git_short_sha}
e.g. avm-kr-seoul-apt-v2-20260315-a3f8c2
"""

import re
import subprocess
from datetime import date

MODEL_ID_RE = re.compile(
    r"^avm-(?P<country>[a-z]{2})-(?P<region>[a-z0-9]+)-(?P<ptype>[a-z]+)"
    r"-v(?P<version>\d+)-(?P<date>\d{8})-(?P<sha>[0-9a-f]{6,12})$"
)


def git_short_sha(default: str = "000000") -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else default
    except OSError:
        return default


def make_model_id(
    country: str,
    region: str,
    property_type: str,
    version: int,
    trained_on: date | None = None,
    sha: str | None = None,
) -> str:
    d = (trained_on or date.today()).strftime("%Y%m%d")
    return (
        f"avm-{country.lower()}-{region.lower()}-{property_type.lower()}"
        f"-v{version}-{d}-{sha or git_short_sha()}"
    )


def parse_model_id(model_id: str) -> dict:
    m = MODEL_ID_RE.match(model_id)
    if not m:
        raise ValueError(f"invalid model_id: {model_id}")
    return m.groupdict()
