"""OpenTelemetry exporter from the worker fleet to Dynatrace, fire-and-forget.

When `DT_ENVIRONMENT` and a valid auth token are set, every `AgentEvent` is
mirrored as an OTel span + metric points and shipped to Dynatrace via OTLP/HTTP.
Davis can then baseline the fleet and raise real problems Warden reads back via
the MCP server, closing the live loop end-to-end.

Constraints (per Dynatrace docs):
- HTTP/protobuf only, no gRPC.
- Endpoint pattern: `{DT_ENVIRONMENT}/api/v2/otlp` with `/v1/traces`, `/v1/metrics`.
- **Auth depends on tenant type and token type.** Classic Dynatrace SaaS
  (`*.live.dynatrace.com`) accepts `Authorization: Api-Token dt0c01...`. The new
  Dynatrace Platform (`*.apps.dynatrace.com`) accepts `Authorization: Bearer ...`
  but only when the token carries the OTLP ingest scopes
  (`openTelemetryTrace.ingest`, `metrics.ingest`, `logs.ingest`).
- `BatchSpanProcessor` + `PeriodicExportingMetricReader` so the simulation loop
  is never blocked on export; all calls are wrapped in `try/except` so a
  Dynatrace outage cannot stall Warden.
"""

from __future__ import annotations

import os
import threading

_TRACER = None
_METER = None
_INITIALIZED = False
_LOCK = threading.Lock()
_INSTRUMENTS: dict = {}


def _resolve_endpoint() -> str | None:
    explicit = os.getenv("DT_OTLP_ENDPOINT", "").strip().rstrip("/")
    if explicit:
        return explicit
    base = os.getenv("DT_ENVIRONMENT", "").strip().rstrip("/")
    if not base:
        return None
    # The OTLP gateway lives on the classic `.live.dynatrace.com` host even when
    # the Platform UI lives on `.apps.dynatrace.com`. Translate transparently so
    # users can keep using their UI URL in DT_ENVIRONMENT.
    if ".apps.dynatrace.com" in base:
        base = base.replace(".apps.dynatrace.com", ".live.dynatrace.com")
    return f"{base}/api/v2/otlp"


def _resolve_auth_header() -> tuple[str | None, str]:
    """Return (header_value, scheme_label). Header is None if no token configured."""
    api_token = os.getenv("DT_API_TOKEN", "").strip()
    if api_token:
        return f"Api-Token {api_token}", "Api-Token"
    bearer = os.getenv("DT_OTEL_BEARER", "").strip()
    if bearer:
        return f"Bearer {bearer}", "Bearer"
    # Fallback: if DT_PLATFORM_TOKEN is set, try it as Bearer. Only works if the
    # token carries openTelemetryTrace.ingest / metrics.ingest / logs.ingest.
    platform = os.getenv("DT_PLATFORM_TOKEN", "").strip()
    if platform:
        return f"Bearer {platform}", "Bearer"
    return None, "(none)"


def is_enabled() -> bool:
    return _INITIALIZED and _TRACER is not None


def init_otel(service_name: str = "warden", namespace: str = "warden.fleet") -> bool:
    """Initialize the OTel SDK with Dynatrace OTLP exporters. Idempotent.

    Returns True if export is configured and ready, False if no auth is set or
    the optional OTel packages are missing. Never raises.
    """
    global _TRACER, _METER, _INITIALIZED
    with _LOCK:
        if _INITIALIZED:
            return _TRACER is not None
        _INITIALIZED = True

        endpoint = _resolve_endpoint()
        auth_header, scheme = _resolve_auth_header()
        if not endpoint or not auth_header:
            print("[warden.otel] disabled: missing DT_ENVIRONMENT or DT_API_TOKEN / DT_OTEL_BEARER / DT_PLATFORM_TOKEN.")
            return False

        try:
            import logging

            from opentelemetry import metrics, trace
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            print(f"[warden.otel] opentelemetry packages not installed ({exc}); export disabled.")
            return False

        # Make OTel exporter errors (especially 401 on wrong token / scope) visible
        # on stderr so a bad token is not silently swallowed.
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.WARNING)
        for name in (
            "opentelemetry.exporter.otlp.proto.http.trace_exporter",
            "opentelemetry.exporter.otlp.proto.http.metric_exporter",
        ):
            logging.getLogger(name).setLevel(logging.WARNING)

        resource = Resource.create({
            "service.name": service_name,
            "service.namespace": namespace,
            "deployment.environment": os.getenv("WARDEN_MODE", "sim"),
            "telemetry.sdk.language": "python",
        })
        headers = {"Authorization": auth_header}

        span_exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)
        tp = TracerProvider(resource=resource)
        tp.add_span_processor(BatchSpanProcessor(
            span_exporter, max_export_batch_size=128, schedule_delay_millis=2000,
        ))
        trace.set_tracer_provider(tp)
        _TRACER = trace.get_tracer("warden.fleet")

        metric_exporter = OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", headers=headers)
        reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10000)
        mp = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(mp)
        _METER = metrics.get_meter("warden.fleet")

        _INSTRUMENTS["actions"] = _METER.create_counter("warden.agent.actions", unit="1")
        _INSTRUMENTS["errors"] = _METER.create_counter("warden.agent.errors", unit="1")
        _INSTRUMENTS["latency_ms"] = _METER.create_histogram("warden.agent.latency_ms", unit="ms")
        _INSTRUMENTS["cost_usd"] = _METER.create_counter("warden.agent.cost_usd", unit="USD")
        _INSTRUMENTS["value_usd"] = _METER.create_counter("warden.agent.value_usd", unit="USD")

        print(f"[warden.otel] initialized: endpoint={endpoint}, auth={scheme}, service={service_name}")
        return True


def record_event(event, agent_state: str = "healthy", scenario: str | None = None) -> None:
    """Mirror an `AgentEvent` to OTel. Fire-and-forget; never blocks, never raises."""
    if not is_enabled():
        return
    try:
        attrs = {
            "agent.id": event.agent_id,
            "agent.state": agent_state,
            "event.kind": event.kind,
            "reversible": bool(event.reversible),
            "error": bool(event.error),
        }
        if event.action_type:
            attrs["action.type"] = event.action_type
        if scenario:
            attrs["scenario"] = scenario

        if event.kind in {"action", "error"}:
            with _TRACER.start_as_current_span(f"agent.{event.kind}", attributes=attrs):
                pass

        if event.kind == "action":
            _INSTRUMENTS["actions"].add(1, attributes=attrs)
        if event.error:
            _INSTRUMENTS["errors"].add(1, attributes=attrs)
        if event.latency_ms > 0:
            _INSTRUMENTS["latency_ms"].record(float(event.latency_ms), attributes=attrs)
        if event.cost_usd > 0:
            _INSTRUMENTS["cost_usd"].add(float(event.cost_usd), attributes=attrs)
        if event.value_usd > 0:
            _INSTRUMENTS["value_usd"].add(float(event.value_usd), attributes=attrs)
    except Exception:
        pass


def force_flush(timeout_ms: int = 5000) -> bool:
    """Flush traces and metrics. Returns True if both providers flush cleanly."""
    if not is_enabled():
        return False
    try:
        from opentelemetry import metrics, trace
        tp = trace.get_tracer_provider()
        mp = metrics.get_meter_provider()
        ok_t = tp.force_flush(timeout_ms) if hasattr(tp, "force_flush") else True
        ok_m = mp.force_flush(timeout_ms) if hasattr(mp, "force_flush") else True
        return bool(ok_t) and bool(ok_m)
    except Exception:
        return False
