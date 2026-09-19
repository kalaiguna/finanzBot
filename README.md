# finanzbot

Personal finance automation via Telegram. Send receipt photos, bank statement PDFs, and payslip PDFs — get structured data stored automatically in Turso Edge SQLite. Ask natural language questions about your spending.

## Prerequisites

- Google Cloud account with billing enabled (required even for free tier)
- `gcloud` CLI installed and authenticated
- Docker installed
- Telegram bot token from @BotFather
- Turso database URL and auth token
- Gemini API key from [aistudio.google.com](https://aistudio.google.com)

## Secrets Setup

Store all secrets in Google Secret Manager before deploying:

```bash
echo -n "your-telegram-token"   | gcloud secrets create telegram-bot-token --data-file=-
echo -n "your-gemini-key"       | gcloud secrets create gemini-api-key --data-file=-
echo -n "libsql://db.turso.io"  | gcloud secrets create turso-db-url --data-file=-
echo -n "your-turso-token"      | gcloud secrets create turso-auth-token --data-file=-
echo -n "123456789"             | gcloud secrets create allowed-user-id --data-file=-
```

Replace `your-gcp-project-id` in `deploy.sh` with your actual GCP project ID.

## Deploy

```bash
chmod +x deploy.sh
./deploy.sh
```

This builds the container, deploys to Cloud Run, and registers the Telegram webhook in one step.

## Turso Database

Schema is applied automatically on first startup via `db.init_schema()`. To create the database:

```bash
turso db create finanzbot
turso db show finanzbot --url    # → TURSO_DATABASE_URL
turso db tokens create finanzbot  # → TURSO_AUTH_TOKEN
```

## Historical Data Migration

To import existing finanziq data into Turso:

```bash
python migrate_finanziq.py
```

Requires finanziq to be at `../finanziq` relative to this repo. Safe to run multiple times — all inserts are `INSERT OR IGNORE` with content hashes.

## Local Development

```bash
cp .env.example .env
# fill in real values

pip install -r requirements.txt
flask --app main run --port 8080

# expose locally with ngrok for webhook testing
ngrok http 8080
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<ngrok-id>.ngrok.io/webhook"
```

## Routes

| Route | Description |
|---|---|
| `POST /webhook` | Telegram update receiver |
| `GET /dashboard` | Static finance dashboard (from finanziq) |
| `GET /health` | Liveness probe for Cloud Run |

## Supported Message Types

| What you send | What happens |
|---|---|
| Receipt photo (JPEG/PNG) | Gemini Vision extracts date, merchant, total → stored in `receipts` |
| Bank statement PDF (filename contains `konto` or `auszug`) | Deterministic Sparkasse parser (Gemini fallback if confidence < 80) → stored in `transactions` |
| Payslip PDF (filename contains `abrechnung`, `gehalts`, `lohn`, etc.) | Deterministic DATEV parser (Gemini fallback if confidence < 80) → stored in `payslips` |
| Text message | Natural language query → Gemini → SQL → formatted answer |

## Architecture

```
Telegram → Cloud Run (Flask) → router.py
                                 ├── extractor.py → pdfplumber + Gemini → Turso
                                 └── querier.py  → Gemini → Turso → Gemini → reply
```

All file processing is in-memory (`io.BytesIO`). Nothing is written to disk.
