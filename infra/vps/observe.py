"""Read the existing HTTP histogram; no second metrics collector or SDK."""

import json
import math
import sys
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

base, version = sys.argv[1:]
labels = 'service_name="pycil-api",version=' + json.dumps(version)
labels += ',http_target!~"/livez|/readyz|unmatched|/v1/assistant:run"'


def query(expression):
    with urlopen(
        base.rstrip("/") + "/api/v1/query?" + urlencode({"query": expression}),
        timeout=5,
    ) as response:
        result = json.load(response)
    if result.get("status") != "success" or len(result["data"]["result"]) != 1:
        raise ValueError("missing metric")
    value = float(result["data"]["result"][0]["value"][1])
    if not math.isfinite(value):
        raise ValueError("invalid metric")
    return value


try:
    freshness = query(
        "time() - max(timestamp(http_server_duration_milliseconds_count{"
        + labels
        + "}))"
    )
    if freshness > 90:
        raise ValueError("stale telemetry")
    count = query(
        "sum(increase(http_server_duration_milliseconds_count{" + labels + "}[2m]))"
    )
    errors = query(
        "(sum(increase(http_server_duration_milliseconds_count{"
        + labels
        + ',http_status_code=~"5.."}[2m])) or vector(0))'
    )
    duration = query(
        "sum(increase(http_server_duration_milliseconds_sum{" + labels + "}[2m]))"
    )
    if count <= 0 or (count >= 50 and errors / count > 0.02):
        raise ValueError("No request observations or HTTP error budget exceeded")
except (OSError, URLError, ValueError, KeyError, TypeError):
    raise SystemExit(
        "observe: missing/stale/empty telemetry or HTTP errors exceed 2% with >=50 requests in 2m"
    ) from None
print(
    json.dumps(
        {
            "requests_2m": round(count, 2),
            "errors_2m": round(errors, 2),
            "mean_ms": round(duration / count, 2) if count else None,
        }
    )
)
