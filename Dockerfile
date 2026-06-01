# Warden operator console for Cloud Run.
#
# The hosted dashboard runs in WARDEN_MODE=sim and uses only the Python
# standard library, so no requirements.txt install is needed in this image.
# Live MCP and live Gemini are not invoked from the hosted URL; they are
# exercised locally by scripts/live_check.py and scripts/otel_smoke.py.

FROM python:3.12-slim

WORKDIR /app

# Copy only what the web dashboard needs.
COPY warden ./warden

# Cloud Run injects PORT at runtime; the app picks it up via PORT env (see
# warden/web/app.py). Bind 0.0.0.0 so the container is reachable from outside.
ENV WARDEN_MODE=sim \
    WARDEN_WEB_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

# Documented default; Cloud Run will override via $PORT.
EXPOSE 8080

CMD ["python", "-m", "warden.web.app"]
