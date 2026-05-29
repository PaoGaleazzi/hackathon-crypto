#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-us-central1}"
SERVICE="arb-backend"

echo "Deploying $SERVICE to Cloud Run ($REGION, project: $PROJECT_ID)..."

gcloud run deploy "$SERVICE" \
  --source backend/ \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-env-vars DB_PATH=/tmp/arb.db \
  --port 8080

echo "Deploy complete."
gcloud run services describe "$SERVICE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format "value(status.url)"
