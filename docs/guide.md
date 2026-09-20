# finanzbot: Detailed Guide

> For a quick overview, see the [README](../README.md). For the product roadmap and future milestones, see the [Backlog](backlog.md).

---

## Table of Contents

1. [For Users: What can I do with this?](#1-for-users)
2. [Security: Is it safe to send payslips and bank statements?](#security)
3. [For Developers and AI Engineers: How is it built?](#2-for-developers--ai-engineers)
4. [For DevOps Engineers: How do I deploy it?](#3-for-devops-engineers)
5. [Extending finanzbot: new banks, document types, AI models](#extending-finanzbot)

---

## 1. For Users

### What problem does this solve?

Tracking personal finances manually is tedious. You take a photo of a supermarket receipt, download a PDF from your bank's portal, or receive a payslip, then either lose it or spend time entering data into a spreadsheet. finanzbot removes that friction entirely: you forward the document to a Telegram chat, and it handles the rest.

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
✅ €42.50 at REWE: Groceries
✅ 01/2026 statement: 34 transactions, €1,284.60 total expenses
✅ January 2026 payslip: gross €5,000.00, net €3,200.00, payout €3,200.00
```

Queries get a conversational reply with amounts formatted in euros.

### Privacy

finanzbot is a single-user system. It validates every incoming message against a single allowed Telegram user ID and silently ignores everyone else; no reply, no log of the content. Your financial data never leaves your own GCP project and Turso database.

---

## Security

> *"Is it safe to send payslips and bank statements through Telegram?"*

It is the right question. Here is exactly what happens to your document at each hop:

### 1. Telegram

Telegram encrypts all messages in transit (TLS) and at rest on their servers. Your bot token is private; only messages sent explicitly to your bot are delivered to it. No other bot, user, or Telegram employee can read your messages unless they have your bot token.

Telegram does retain messages on their servers temporarily (or permanently if you do not delete them). If this is a concern, delete the message after sending; finanzbot has already extracted and stored the data.

### 2. Cloud Run (your instance)

The document travels from Telegram's servers directly into memory on your Cloud Run container:

- Downloaded as raw bytes into `io.BytesIO`; **never written to disk**
- Processed (text extracted or image parsed)
- Raw bytes discarded immediately after extraction
- Only the structured fields (amounts, dates, merchant names) leave this step

The container runs in **your GCP project**, not a shared backend. The code is open source; you can verify exactly what it does.

### 3. Gemini API

If the deterministic parser reads the document with high confidence (≥ 80%), **Gemini is never called**; your document goes nowhere beyond your own container.

If Gemini is called as a fallback, **extracted text** (not the original PDF or image) is sent to the API. Google's [Gemini API terms](https://ai.google.dev/gemini-api/terms) state that API inputs are not used to train models.

### 4. Turso database

Only structured fields are stored:

| Document | What is stored |
|---|---|
| Receipt | date, merchant, total, category, payment method |
| Bank statement | date, description, merchant, amount, category |
| Payslip | year, month, gross, net, tax, social security, employer |

Raw PDFs and images are **never persisted** anywhere. The `raw_json` field stores the Gemini extraction output (structured text), not the original document.

### 5. You own the infrastructure

| Component | Who owns it |
|---|---|
| Cloud Run container | Your GCP project |
| Turso database | Your Turso account |
| Bot token | Your BotFather token |
| All secrets | Your Google Secret Manager |

There is no shared backend, no analytics pipeline, no third party that aggregates your data.

### Single-user lock

The `ALLOWED_TELEGRAM_USER_ID` environment variable hardcodes your Telegram user ID. Every incoming message is checked before any processing:

- Message from you → processed normally
- Message from anyone else → silently ignored, nothing logged, no reply

Even if someone discovers your bot's username, they cannot interact with it.

### What to be aware of

- **Telegram message retention:** Telegram stores messages. Delete sensitive documents from the chat after sending if you prefer they not remain on Telegram's servers.
- **Gemini fallback:** for unusual document layouts the deterministic parser can't read, extracted text goes to Gemini. This is rare for standard DATEV payslips and Sparkasse statements.
- **Bot token security:** keep your bot token in Google Secret Manager, never in the codebase or environment files committed to git.

---

## 2. For Developers & AI Engineers

### Tech stack

| Layer | Technology | Why |
|---|---|---|
| Runtime | Python 3.12, Flask (sync WSGI) | Simple, no async complexity needed for webhook workload |
| AI | Gemini 2.0 Flash via `google-generativeai` | Free tier covers personal use volume; multimodal for receipt photos |
| Database | Turso Edge SQLite (HTTP pipeline API) | Serverless-friendly; no persistent connection needed; free tier sufficient |
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
Cloud Run: Flask app (main.py)
        │
        ├── router.py         # validates user ID, classifies message type
        │         │
        │         ├── photo / image document  ──────────────────────┐
        │         ├── PDF (konto / auszug keywords)  ───────────────┤
        │         ├── PDF (abrechnung / gehalts / lohn keywords)  ──┤
        │         └── text message  ──────────────────────────────┐ │
        │                                                         │ │
        ├── extractor.py  ◄───────────────────────────────────────┘─┘
        │     │
        │     ├── Receipt (photo / image)
        │     │     └── PIL Image → Gemini Vision → structured JSON
        │     │
        │     ├── Bank statement (PDF)
        │     │     ├── pdfplumber → deterministic Sparkasse parser
        │     │     │     confidence ≥ 80 → done
        │     │     └── confidence < 80  → Gemini text fallback
        │     │
        │     └── Payslip (PDF)
        │           ├── pdfplumber → deterministic DATEV parser
        │           │     confidence ≥ 80 → done
        │           └── confidence < 80  → Gemini text fallback
        │
        ├── querier.py  ◄─────── text message
        │     ├── Gemini: NL → SQL
        │     ├── db.py: validate SELECT + execute against Turso
        │     └── Gemini: SQL rows → natural language answer
        │
        └── db.py             # Turso HTTP pipeline client
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

27 tests covering extractor (11), querier (8), and router (8). All external calls (Gemini, Telegram API, Turso) are mocked; no credentials needed.

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

Schema is applied automatically on first startup via `db.init_schema()`, which runs at module load time (not inside `if __name__ == '__main__'`; this is intentional so it runs under gunicorn).

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

`GET /health` returns `{"status": "ok"}`; use this for Cloud Run startup probes or uptime monitors.

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

### Observability & cost protection

finanzbot runs entirely on free tiers for personal use, but a misconfiguration (e.g. webhook loop, bot exposed to unexpected traffic) can generate surprise API and compute charges. Set these up before going live.

**1. GCP Budget Alert (most important)**

```bash
# In GCP Console → Billing → Budgets & alerts
# Set monthly budget: €5 (well above expected €0 cost)
# Alert thresholds: 50%, 80%, 100%
# Notification: email + Pub/Sub if you want automated response
```

This is the single most effective cost protection measure. GCP will email you if spend deviates from zero.

**2. Cloud Run: cap max instances**

Add `--max-instances 3` to `deploy.sh` to prevent runaway horizontal scaling if the webhook receives unexpected bursts:

```bash
gcloud run deploy "$SERVICE_NAME" \
  --max-instances 3 \
  ...
```

For a single-user personal bot, 1 instance handles all load. The cap is a safety net, not a performance setting.

**3. Cloud Run request count alert**

In GCP Console → Cloud Monitoring → Alerting, create an alert on:

- **Metric:** `run.googleapis.com/request_count`
- **Threshold:** > 500 requests in 1 hour
- **Rationale:** normal personal use is ~5–10 requests/day; a spike indicates webhook misconfiguration or an external party hammering the endpoint

**4. Gemini API quota**

Gemini 2.0 Flash free tier allows 1,500 requests/day via AI Studio. The bot uses 1–2 Gemini calls per message, so the limit supports ~750 documents/day; well above personal use.

Monitor in GCP Console → APIs & Services → Gemini API → Quotas. Set a quota alert at 200 requests/day to get an early warning before the free tier is exhausted.

**5. Cloud Logging: error rate alert**

Cloud Run logs to Cloud Logging automatically. Create a log-based metric on `severity=ERROR` and alert if the error rate exceeds 10 errors in 10 minutes; this catches Turso outages, Gemini failures, or malformed webhook payloads before they silently accumulate.

**6. Turso usage**

Turso's free tier (500M reads, 10M writes, 5GB) will not be exhausted by personal use. Monitor in the [Turso dashboard](https://app.turso.tech). No native alerting on the free tier; a monthly manual check is sufficient.

### Historical data migration (one-off)

If migrating from finanziq, place finanziq at `../finanziq` relative to this repo and run:

```bash
python migrate_finanziq.py
```

Safe to run multiple times; all inserts use `INSERT OR IGNORE` with content hashes. Prints a summary of rows inserted vs skipped.

---

## Extending finanzbot

finanzbot is released under the [MIT licence](../LICENSE); fork it, self-host it, and adapt it freely. The architecture is intentionally modular so each layer can be changed independently.

### Adding a new bank format

Each bank has its own PDF layout. To add support for a different bank (e.g. DKB, ING, N26):

1. **Write a deterministic parser** in `parsers/new_bank_parser.py`: return a dict with `_confidence` 0–100 and the same `period`/`transactions` shape as `bank_parser.py`
2. **Register filename keywords:** add identifying keywords to `_BANK_KEYWORDS` in `router.py` and map them to a new handler
3. **Add a Gemini fallback prompt** in `prompts.py` if the bank's layout is complex enough that the deterministic parser alone won't achieve high confidence
4. **Write tests** following the pattern in `tests/test_extractor.py`

The existing `BANK_PROMPT` in `prompts.py` is generic enough to handle most Eurozone bank statements as a fallback without modification.

### Adding a new document type (e.g. ETF / investment statements)

1. **`models.py`:** add a new Pydantic model (e.g. `Investment`) with monetary fields auto-rounded via `field_validator`
2. **`db.py`:** add `CREATE TABLE IF NOT EXISTS investments (...)` to `init_schema()` and an `insert_investment()` function; add a `_hash` column for dedup
3. **`prompts.py`:** add an extraction prompt describing the expected JSON structure
4. **`extractor.py`:** add a `handle_investment_pdf(file_id)` function following the deterministic-first pattern
5. **`router.py`:** add filename keywords (e.g. `"depot"`, `"wertpapier"`) and dispatch to the new handler
6. **`querier.py`:** the NL→SQL pipeline requires no changes; just ensure `NL_TO_SQL_PROMPT` includes the new table schema

### Changing the AI model

**Within Gemini (current SDK):** swap the model string in `extractor.py` and `querier.py`:

```python
_model = genai.GenerativeModel("gemini-2.5-pro")  # any Gemini variant
```

**Cross-provider model neutrality:** the current code is coupled to the `google-generativeai` SDK. Swapping to Claude, GPT-4o, or another provider requires replacing the SDK. The practical path is [LiteLLM](https://docs.litellm.ai), a single unified interface that works across 100+ providers with one call:

```python
import litellm
# model string controls the provider; no SDK swap needed
response = litellm.completion(
    model=os.environ["LLM_MODEL"],  # e.g. "gemini/gemini-2.0-flash", "claude-sonnet-4-5", "gpt-4o"
    messages=[{"role": "user", "content": prompt}]
)
```

The change is contained in `extractor.py` and `querier.py` only. Prompts, routing, and the database layer are unaffected.

> **Receipt extraction requires a multimodal (vision) model.** Verify that your chosen model supports image input before switching. Gemini Flash, GPT-4o, and Claude 3+ all support vision. Bank/payslip extraction and NL queries work with any text model.

### A note on Google ADK

The current codebase uses the **`google-generativeai` SDK directly**. Every AI call is a single `model.generate_content([prompt, input])` request. Google Agent Development Kit (ADK) is **not used** in v1.x.

**What ADK is:** ADK is open-source (Python, TypeScript, Go, Java) and architecturally model-agnostic. It integrates with LiteLLM, so an ADK agent can call Claude, GPT-4o, or a self-hosted Llama model as its backend. It also deploys as a standard container and runs on Cloud Run, AWS ECS, or Azure container instances.

**What ADK is not:** a substitute for LiteLLM on the model-neutrality question. The model-neutral integration point is LiteLLM regardless of whether ADK is in use. ADK's primary value is agent orchestration: giving the model the ability to call tools, reason across multiple steps, and manage state. Its documentation, native optimisations, and ecosystem primitives naturally favour Gemini, so straying from that requires extra effort.

**Why it is on the roadmap for v2.0+:** the querier currently calls Gemini twice with fixed prompts (NL to SQL, then rows to answer). It cannot decide to run a follow-up query or ask a clarifying question. ADK enables exactly that kind of multi-step reasoning. The migration is contained entirely within `querier.py`. See [Backlog → v2.0.0](backlog.md#v200--agentic-querier-adk).

### Key libraries for extension

| Library | Docs | Used for |
|---|---|---|
| `google-generativeai` | [ai.google.dev](https://ai.google.dev/gemini-api/docs) | Gemini API calls: vision, text extraction, NL→SQL |
| `pdfplumber` | [github.com/jsvine/pdfplumber](https://github.com/jsvine/pdfplumber) | PDF text + table extraction |
| `pydantic` v2 | [docs.pydantic.dev](https://docs.pydantic.dev) | Model validation, monetary rounding |
| `flask` | [flask.palletsprojects.com](https://flask.palletsprojects.com) | Webhook server, dashboard route |
| `requests` | [docs.python-requests.org](https://docs.python-requests.org) | Telegram API calls, Turso HTTP pipeline |
| `Pillow` | [pillow.readthedocs.io](https://pillow.readthedocs.io) | Opening images for Gemini Vision |
