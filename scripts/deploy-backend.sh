#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-us-central1}"
SERVICE="arb-backend"

echo "Deploying $SERVICE to Cloud Run ($REGION, project: $PROJECT_ID)..."

# --no-cpu-throttling: keep CPU allocated between requests so the asyncio event
#   loop (WS adapters + pipeline) is never frozen — otherwise latency spikes.
# --min-instances 1: avoid cold starts and keep persistent WS connections alive.
gcloud run deploy "$SERVICE" \
  --source backend/ \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars DB_PATH=/tmp/arb.db \
  --no-cpu-throttling \
  --min-instances 1 \
  --port 8080

echo "Deploy complete."
gcloud run services describe "$SERVICE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)"
