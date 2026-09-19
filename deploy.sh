#!/bin/bash
# deploy.sh — full finanzbot Cloud Run deployment
set -euo pipefail

PROJECT_ID="your-gcp-project-id"
REGION="europe-west1"
SERVICE_NAME="finanzbot"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"

# 1. Build and push container
gcloud builds submit --tag "$IMAGE"

# 2. Deploy to Cloud Run
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --max-instances 3 \
  --set-secrets "\
TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,\
GEMINI_API_KEY=gemini-api-key:latest,\
TURSO_DATABASE_URL=turso-db-url:latest,\
TURSO_AUTH_TOKEN=turso-auth-token:latest,\
ALLOWED_TELEGRAM_USER_ID=allowed-user-id:latest"

# 3. Register Telegram webhook
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" --format "value(status.url)")
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook?url=$SERVICE_URL/webhook"
