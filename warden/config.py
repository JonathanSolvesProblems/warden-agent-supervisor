"""Runtime configuration and policy thresholds.

With no environment set, Warden runs in SIMULATION mode and needs nothing.
Setting WARDEN_MODE=live (plus the Gemini + Dynatrace vars in .env) swaps in
the real Gemini brain and the real Dynatrace MCP server.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv() -> None:
    """Minimal .env loader (avoids a hard dependency on python-dotenv for sim mode)."""
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    except OSError:
        pass


_load_dotenv()


def mode() -> str:
    """'sim' (default) or 'live'."""
    return os.getenv("WARDEN_MODE", "sim").strip().lower()


def is_live() -> bool:
    return mode() == "live"


@dataclass(frozen=True)
class Thresholds:
    """Policy knobs Warden uses to decide severity and whether a human must approve."""

    # An action moving more than this much money is "high value".
    high_value_usd: float = 250.0
    # Cumulative blast radius above this always escalates to a human.
    human_approval_blast_usd: float = 1000.0
    # Error rate (errors / actions) over the window that flags a problem.
    error_rate_alarm: float = 0.30
    # Actions-per-window above this for one agent flags runaway behavior.
    # Healthy agents take <=1 action/tick, so a full window tops out near the
    # window size; set comfortably above that to avoid false positives.
    action_rate_alarm: int = 12
    # Spend (cost_usd) per window above this flags a cost anomaly.
    cost_alarm_usd: float = 50.0
    # Detection/analysis window, in simulated ticks.
    window_ticks: int = 10


THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class GeminiConfig:
    project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    model: str = os.getenv("WARDEN_GEMINI_MODEL", "gemini-flash-latest")
    # Default to Flash so the brain runs on the AI Studio free tier out of the box.
    # Switch to gemini-pro-latest when running on Vertex with paid quota.
    reasoning_model: str = os.getenv("WARDEN_GEMINI_REASONING_MODEL", "gemini-flash-latest")
    use_vertex: bool = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true"


@dataclass(frozen=True)
class DynatraceConfig:
    environment: str = os.getenv("DT_ENVIRONMENT", "")
    platform_token: str = os.getenv("DT_PLATFORM_TOKEN", "")
    grail_budget_gb: float = float(os.getenv("DT_GRAIL_QUERY_BUDGET_GB", "50") or 50)
    slack_webhook: str = os.getenv("SLACK_WEBHOOK_URL", "")


GEMINI = GeminiConfig()
DYNATRACE = DynatraceConfig()
