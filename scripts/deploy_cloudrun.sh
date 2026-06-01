#!/usr/bin/env bash
# Deploy Warden's operator console to Cloud Run.
#
#   bash scripts/deploy_cloudrun.sh <GCP_PROJECT_ID> [REGION]
#
# Prereqs:
#   1. gcloud CLI installed and on PATH.
#   2. `gcloud auth login` done in this shell.
#   3. A GCP project with billing enabled.
#
# What this does:
#   - Enables the four APIs Cloud Run needs (run, cloudbuild, artifactregistry, secretmanager).
#   - Builds the Dockerfile in the repo root and pushes it to Artifact Registry.
#   - Deploys to Cloud Run with the judging-week-friendly config:
#       sim mode, no auth, 1 warm instance for state consistency, 1h timeout for SSE.
#   - Prints the public URL at the end.

set -euo pipefail

PROJECT_ID="${1:-}"
REGION="${2:-us-central1}"
SERVICE_NAME="warden"

if [ -z "$PROJECT_ID" ]; then
  echo "Usage: bash scripts/deploy_cloudrun.sh <GCP_PROJECT_ID> [REGION]"
  echo "Example: bash scripts/deploy_cloudrun.sh warden-agent-supervisor us-central1"
  exit 1
fi

echo ">>> Setting active project to $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

echo ">>> Enabling required APIs (idempotent, takes ~30s on first run)"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

echo ">>> Deploying $SERVICE_NAME to Cloud Run in $REGION"
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --min-instances=1 \
  --max-instances=1 \
  --cpu=1 \
  --memory=512Mi \
  --concurrency=20 \
  --timeout=3600 \
  --set-env-vars WARDEN_MODE=sim

echo
echo ">>> Done. Public URL:"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format='value(status.url)'
