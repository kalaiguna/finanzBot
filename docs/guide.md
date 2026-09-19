# finanzbot — Detailed Guide

> For a quick overview, see the [README](../README.md).

---

## Table of Contents

1. [For Users — What can I do with this?](#1-for-users)
2. [For Developers & AI Engineers — How is it built?](#2-for-developers--ai-engineers)
3. [For DevOps Engineers — How do I deploy it?](#3-for-devops-engineers)

---

## 1. For Users

### What problem does this solve?

Tracking personal finances manually is tedious. You take a photo of a supermarket receipt, download a PDF from your bank's portal, or receive a payslip — and then either lose it or spend time entering data into a spreadsheet. finanzbot removes that friction entirely: you forward the document to a Telegram chat, and it handles the rest.

It stores everything in a personal database and lets you ask plain-language questions like:

> *"How much did I spend on groceries last month?"*
> *"What was my net salary in March?"*
> *"Show me all transactions above €200 in January."*

### What can I send?

| What you send | What the bot does |
|---|---|
| Receipt photo (JPEG / PNG) | Reads merchant, date, and total; categorises the spend; stores it |
| Bank statement PDF | Parses all transactions; assigns merchant and category to each; stores them |
| Payslip PDF | Extracts gross, net, tax, social security, and employer; stores the payslip |
| Text message | Converts your question into a database query and replies in natural language |

### What do I get back?

After every document, the bot confirms what it stored:

```
✅ €42.50 at REWE — Groceries
✅ 01/2026 statement: 34 transactions, €1,284.60 total expenses
✅ January 2026 payslip: gross €5,000.00, net €3,200.00, payout €3,200.00
```

Queries get a conversational reply with amounts formatted in euros.

### Privacy

finanzbot is a single-user system. It validates every incoming message against a single allowed Telegram user ID and silently ignores everyone else. Your financial data never leaves your own GCP project and Turso database.

---

## 2. For Developers & AI Engineers

### Tech stack

| Layer | Technology | Why |
|---|---|---|
| Runtime | Python 3.12, Flask (sync WSGI) | Simple, no async complexity needed for webhook workload |
| AI | Gemini 2.0 Flash via `google-generativeai` | Free tier covers personal use volume; multimodal for receipt photos |
| Database | Turso Edge SQLite — HTTP pipeline API | Serverless-friendly; no persistent connection needed; free tier sufficient |
| Telegram | Direct `requests` to `api.telegram.org` | No PTB overhead; webhook-only (no polling) |
| PDF parsing | `pdfplumber` | Reliable text extraction; handles German bank/payslip layouts |
| Validation | Pydantic v2 | Structured output validation from Gemini responses |
| Container | Docker (`python:3.12-slim`) | Minimal image; poppler-utils added for pdfplumber |
| Deploy target | Google Cloud Run | Serverless; scales to zero; free tier covers personal use |

### Architecture

```
User (Telegram Mobile)
        │  HTTPS
        ▼
Telegram Bot API
        │  POST /webhook
        ▼
Cloud Run — Flask app (main.py)
        │
        ├── router.py         — validates user ID, classifies message type
        │
        ├── extractor.py      — documents → structured data
        │     ├── parsers/    — deterministic (runs first, confidence 0–100)
        │     └── Gemini      — fallback if confidence < 80
        │
        ├── querier.py        — NL → SQL → Turso → NL answer
        │     └── Gemini      — both NL→SQL and SQL rows→answer steps
        │
        └── db.py             — Turso HTTP pipeline client
                └── Turso Edge SQLite
```

### Key design decisions

**Deterministic parsers first.** `parsers/payslip_parser.py` and `parsers/bank_parser.py` are rule-based parsers validated against real German DATEV and Sparkasse documents. They return a `_confidence` score (0–100). Gemini is only called if confidence falls below 80 or the parser raises an exception. This keeps costs near zero for the common case and Gemini as a reliable fallback for edge cases.

**In-memory file handling.** All uploaded files are downloaded as `bytes`, wrapped in `io.BytesIO`, processed, and discarded. Nothing is ever written to disk. This is both a privacy constraint and a Cloud Run requirement (the filesystem is ephemeral and not writable beyond `/tmp`).

**Turso via raw HTTP.** The `libsql` Python client is not used. All calls go through `db.py`'s `_turso()` helper which POSTs to Turso's `/v2/pipeline` endpoint. This avoids a native dependency and works cleanly in a slim container.

**Deduplication by content hash.** Both `receipts` and `transactions` tables have a `_hash TEXT UNIQUE` column. Hashes are computed from the content fields before insert, and all inserts use `INSERT OR IGNORE`. Re-processing the same document is safe.

**SELECT-only query guard.** `querier.py` strips the Gemini SQL response to its first semicolon-delimited statement and rejects anything that does not start with `SELECT`. This prevents prompt-injection attacks from causing destructive queries even if the NL→SQL model misbehaves.

### Code structure

```
finanzbot/
├── main.py              # Flask app; db.init_schema() at module level
├── router.py            # Message classifier and dispatcher
├── extractor.py         # Receipt / bank PDF / payslip PDF handlers
├── querier.py           # NL query pipeline
├── db.py                # Turso HTTP client; schema init; insert/query helpers
├── models.py            # Pydantic v2 models: Receipt, Transaction, BankStatement, Payslip
├── prompts.py           # All Gemini prompts centralised
├── parsers/
│   ├── bank_parser.py   # Deterministic Sparkasse parser (from finanziq)
│   ├── payslip_parser.py# Deterministic DATEV parser (from finanziq)
│   └── categorizer.py   # 200+ merchant → category rules (from finanziq)
├── migrate_finanziq.py  # One-off historical data import
├── tests/
│   ├── test_extractor.py
│   ├── test_querier.py
│   └── test_router.py
├── dashboard/
│   └── index.html       # Static finance dashboard (served at /dashboard)
├── Dockerfile
├── deploy.sh
└── requirements.txt
```

### How AI is used

| Step | Model call | Input | Output |
|---|---|---|---|
| Receipt extraction | Gemini 2.0 Flash (vision) | `RECEIPT_EXTRACTION_PROMPT` + image bytes | JSON: date, merchant, total, category |
| Bank PDF extraction | Gemini 2.0 Flash (text) | `BANK_PROMPT` + PDF text | JSON: period, transactions array |
| Payslip PDF extraction | Gemini 2.0 Flash (text) | `PAYSLIP_PROMPT` + PDF text | JSON: period, gross, net, deductions, YTD |
| NL → SQL | Gemini 2.0 Flash (text) | `NL_TO_SQL_PROMPT` + user question | SQL SELECT statement |
| SQL rows → answer | Gemini 2.0 Flash (text) | `NL_TO_ANSWER_PROMPT` + question + rows | Conversational reply in euros |

The `PAYSLIP_PROMPT` and `BANK_PROMPT` are copied verbatim from the predecessor project (finanziq) where they were validated against real German documents. Do not modify them without re-validating against real documents.

### Running tests

```bash
python -m pytest tests/ -v
```

27 tests covering extractor (11), querier (8), and router (8). All external calls (Gemini, Telegram API, Turso) are mocked — no credentials needed.

---

## 3. For DevOps Engineers

### Prerequisites

| Tool | Purpose |
|---|---|
| `gcloud` CLI | Build, deploy, secrets |
| Docker | Local container build/test |
| Telegram BotFather | Create a bot and get the token |
| Turso CLI or account | Create database, get URL and token |
| Google AI Studio | Get a Gemini API key (free) |
| GCP project with billing | Required even for free tier Cloud Run |

### Secrets

All secrets are stored in **Google Secret Manager** and injected into Cloud Run at deploy time. No secrets are baked into the container image.

```bash
echo -n "your-telegram-token"   | gcloud secrets create telegram-bot-token --data-file=-
echo -n "your-gemini-key"       | gcloud secrets create gemini-api-key --data-file=-
echo -n "libsql://db.turso.io"  | gcloud secrets create turso-db-url --data-file=-
echo -n "your-turso-token"      | gcloud secrets create turso-auth-token --data-file=-
echo -n "123456789"             | gcloud secrets create allowed-user-id --data-file=-
```

Replace `123456789` with your Telegram user ID (send `/start` to `@userinfobot` to find yours).

### Turso database setup

```bash
turso db create finanzbot
turso db show finanzbot --url    # → TURSO_DATABASE_URL (libsql://...)
turso db tokens create finanzbot  # → TURSO_AUTH_TOKEN
```

Schema is applied automatically on first startup via `db.init_schema()`, which runs at module load time (not inside `if __name__ == '__main__'` — this is intentional so it runs under gunicorn).

### Deploy

Edit `deploy.sh` and set `PROJECT_ID` to your GCP project, then:

```bash
chmod +x deploy.sh
./deploy.sh
```

The script:
1. Builds and pushes the container via `gcloud builds submit`
2. Deploys to Cloud Run (single region, unauthenticated, all 5 secrets mounted)
3. Registers the Telegram webhook to the deployed service URL

### Cloud Run specifics

| Setting | Value | Why |
|---|---|---|
| Workers | 1 (`--workers 1`) | Webhook workload is low-concurrency; avoids shared state issues |
| Timeout | 120s (`--timeout 120`) | Gemini + Turso calls can be slow on cold PDFs |
| Port | 8080 (via `PORT` env var) | Cloud Run default |
| Min instances | 0 (default) | Scales to zero between messages |
| Ingress | Unauthenticated | Telegram webhook requires public HTTPS endpoint |

### Health check

`GET /health` returns `{"status": "ok"}` — use this for Cloud Run startup probes or uptime monitors.

### Local development

```bash
cp .env.example .env
# fill in real values

pip install -r requirements.txt
flask --app main run --port 8080
```

To test the webhook locally, expose the port with [ngrok](https://ngrok.com) and register it:

```bash
ngrok http 8080
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<ngrok-id>.ngrok.io/webhook"
```

### Historical data migration (one-off)

If migrating from finanziq, place finanziq at `../finanziq` relative to this repo and run:

```bash
python migrate_finanziq.py
```

Safe to run multiple times — all inserts use `INSERT OR IGNORE` with content hashes. Prints a summary of rows inserted vs skipped.
