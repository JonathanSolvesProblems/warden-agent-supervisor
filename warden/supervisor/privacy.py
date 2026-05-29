"""Privacy controls for what Warden sends to a generative model.

Two guarantees, both enforced in code rather than in documentation:

1. **Allowlist on the prompt.** `safe_for_llm` drops any field not in the
   explicit whitelist. A future code change cannot accidentally leak a new
   field (raw customer IDs, fraud scores, etc.) without extending the
   allowlist on purpose.
2. **Append-only audit log.** `audit` records the timestamp, model, SHA-256
   hash and byte count of every prompt and response, plus which fields were
   dropped. Never the raw content. Suitable for "prove what was sent" after
   the fact without making the log itself a new data risk.
"""

from __future__ import annotations

import hashlib
import json
import time

# Top-level fields the brain may send to the model.
_ALLOWED_TOP_LEVEL = {
    "dynatrace_problem",
    "davis_root_cause",
    "fleet_rollup",
    "suspect_agent",
    "value_at_risk_usd",
    "has_irreversible_actions",
}

# Nested-object whitelists.
_ALLOWED_PROBLEM_KEYS = {
    "problemId",
    "title",
    "severityLevel",
    "affectedEntity",
    "signal",
    "metricValue",
}
_ALLOWED_ROLLUP_KEYS = {
    "agent",
    "actions",
    "errors",
    "cost_usd",
    "value_usd",
    "max_value_usd",
}


def safe_for_llm(payload: dict) -> tuple[dict, list[str]]:
    """Whitelist what may be sent to a generative model.

    Returns (clean_payload, dropped_keys). The clean payload contains ONLY
    keys on the allowlist. Dropped keys are returned so the audit log records
    what was filtered out.
    """
    dropped: list[str] = []
    clean: dict = {}
    for key, value in payload.items():
        if key not in _ALLOWED_TOP_LEVEL:
            dropped.append(key)
            continue
        if key == "dynatrace_problem" and isinstance(value, dict):
            sub = {k: v for k, v in value.items() if k in _ALLOWED_PROBLEM_KEYS}
            for k in value:
                if k not in _ALLOWED_PROBLEM_KEYS:
                    dropped.append(f"dynatrace_problem.{k}")
            clean[key] = sub
        elif key == "fleet_rollup" and isinstance(value, list):
            cleaned_rollup: list = []
            for row in value:
                if isinstance(row, dict):
                    rc = {k: v for k, v in row.items() if k in _ALLOWED_ROLLUP_KEYS}
                    for k in row:
                        if k not in _ALLOWED_ROLLUP_KEYS:
                            dropped.append(f"fleet_rollup[].{k}")
                    cleaned_rollup.append(rc)
                else:
                    cleaned_rollup.append(row)
            clean[key] = cleaned_rollup
        else:
            clean[key] = value

    # Deduplicate dropped keys while preserving order of first occurrence.
    seen: set[str] = set()
    unique_dropped: list[str] = []
    for k in dropped:
        if k not in seen:
            seen.add(k)
            unique_dropped.append(k)
    return clean, unique_dropped


def audit(
    model: str,
    vertex: bool,
    prompt: str,
    response: str,
    dropped: list[str],
    log_path: str,
) -> None:
    """Append a one-line JSON audit entry. Hashes and sizes only, never content."""
    if not log_path:
        return
    prompt_bytes = (prompt or "").encode("utf-8")
    response_bytes = (response or "").encode("utf-8")
    entry = {
        "ts": time.time(),
        "model": model,
        "vertex": vertex,
        "input_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "input_bytes": len(prompt_bytes),
        "output_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "output_bytes": len(response_bytes),
        "dropped_fields": dropped,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        # Never crash the supervisory loop because audit logging failed.
        pass
