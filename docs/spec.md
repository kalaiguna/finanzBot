**finanzbot**

Personal Finance Automation — Telegram + Gemini + Cloud Run + Turso

Architecture & Implementation Specification _v1.0 · September 2026_

Replaces / extends: C:\\Users\\g.aa.chandrasekaran\\Code\\finanziq

_This document is the authoritative specification for finanzbot. It is intended to be fed directly to Claude Code or Antigravity CLI to scaffold and implement the full application._

# **1\. Purpose & Scope**

finanzbot replaces the finanziq static-dashboard project with a fully serverless, mobile-first personal finance assistant. The user interacts exclusively through Telegram — sending receipt photos, bank statement PDFs, and payslip PDFs, and asking natural language questions about their finances.

The existing finanziq codebase provides validated extraction logic and a tested data model. finanzbot retains that logic and ports it to a cloud-native runtime, replacing:

- Local Python scripts → Cloud Run container (Python 3.12)
- Static data.json file → Turso Edge SQLite database
- Browser dashboard → Telegram Bot conversational interface
- Manual script execution → Automatic processing on document receipt
- Anthropic Claude API → Google Gemini 2.0 Flash (free tier)

_The static HTML dashboard (dashboard/index.html) from finanziq is preserved as-is and can optionally be served from Cloud Run at /dashboard. No changes required to it._

# **2\. Application Name**

| **Property**                      | **Value**                                      |
| --------------------------------- | ---------------------------------------------- |
| App name                          | finanzbot                                      |
| Repository                        | github.com/&lt;user&gt;/finanzbot              |
| Language                          | Python 3.12                                    |
| Existing codebase to migrate from | C:\\Users\\g.aa.chandrasekaran\\Code\\finanziq |
| Primary interface                 | Telegram Bot                                   |
| Target runtime                    | Google Cloud Run (serverless container)        |

# **3\. Architecture**

## **3.1 System Diagram**

```
┌─────────────────────────────────────────────────────────┐
│                      USER (Mobile)                      │
│  Sends: receipt photo · PDF · text question             │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  TELEGRAM BOT API                       │
│  Webhook → forwards all messages to Cloud Run           │
└─────────────────────┬───────────────────────────────────┘
                      │ POST /webhook
                      ▼
┌─────────────────────────────────────────────────────────┐
│              CLOUD RUN  (Python 3.12)                   │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  router.py  │  │ extractor.py │  │  querier.py  │  │
│  │  (webhook   │→ │  (receipt /  │  │  (NL → SQL   │  │
│  │   handler)  │  │   PDF parse) │  │   → answer)  │  │
│  └─────────────┘  └──────┬───────┘  └──────┬───────┘  │
└─────────────────────────┬──────────────────┬───────────┘
                          │                  │
              ┌───────────┘      ┌───────────┘
              ▼                  ▼
  ┌──────────────────┐  ┌─────────────────────┐
  │  Gemini 2.0 Flash│  │  Turso Edge SQLite   │
  │  Vision + Text   │  │  (receipts, txns,    │
  │  (AI Studio free)│  │   payslips tables)   │
  └──────────────────┘  └─────────────────────┘
```

## **3.2 Cost Model**

All components operate within permanent free tiers at the expected usage of 20 receipts/month, 2 PDFs/month, and ~100 queries/month.

| **Component**      | **Service**                  | **Free Tier Limit**         | **Est. Usage/Month**      | **Cost**  |
| ------------------ | ---------------------------- | --------------------------- | ------------------------- | --------- |
| Compute            | Google Cloud Run             | 2M requests, 360k GB-sec    | ~122 requests, ~3 min CPU | **€0.00** |
| AI Vision + NL     | Gemini 2.0 Flash (AI Studio) | 1,500 req/day = 45,000/mo   | ~122 requests             | **€0.00** |
| Database           | Turso Edge SQLite            | 500M reads, 10M writes, 5GB | <1,000 ops/month          | **€0.00** |
| Bot API            | Telegram Bot API             | Unlimited                   | All messages              | **€0.00** |
| Container Registry | Artifact Registry            | 0.5 GB free                 | ~200 MB image             | **€0.00** |
| Total              |                              |                             |                           | **€0.00** |

_AI Studio free tier note: prompts sent to Gemini via the free AI Studio key may be used by Google to improve their models. For financial data privacy, obtain a paid Vertex AI key — cost at this volume is approximately €0.01–0.05/month._

# **4\. Component Specification**

## **4.1 Repository Structure**

```
finanzbot/
├── main.py                    # Cloud Run entrypoint (Flask webhook server)
├── router.py                  # Message type detection + dispatch
├── extractor.py               # Gemini vision: receipts + PDFs → structured data
├── querier.py                 # NL query → Gemini → SQL → formatted answer
├── db.py                      # Turso HTTP client + schema helpers
├── models.py                  # Pydantic models: Receipt, Transaction, Payslip
├── prompts.py                 # All Gemini prompt templates (centralised)
├── Dockerfile                 # Python 3.12-slim container
├── requirements.txt           # Dependencies
├── deploy.sh                  # One-command Cloud Run deployment
├── .env.example               # Required environment variables
├── tests/
│   ├── test_extractor.py
│   └── test_querier.py
├── dashboard/                 # Preserved from finanziq (static HTML)
│   └── index.html
└── README.md
```

## **4.2 Environment Variables**

| **Variable**             | **Description**                                 | **Where to obtain**      |
| ------------------------ | ----------------------------------------------- | ------------------------ |
| TELEGRAM_BOT_TOKEN       | Bot API token                                   | BotFather on Telegram    |
| GEMINI_API_KEY           | Gemini 2.0 Flash API key                        | aistudio.google.com      |
| TURSO_DATABASE_URL       | libsql://your-db.turso.io                       | turso.tech dashboard     |
| TURSO_AUTH_TOKEN         | Turso database auth token                       | turso.tech dashboard     |
| ALLOWED_TELEGRAM_USER_ID | Your Telegram numeric user ID                   | @userinfobot on Telegram |
| CLOUD_RUN_URL            | Deployed service URL (for webhook registration) | Set after first deploy   |

## **4.3 Message Routing (router.py)**

Every incoming Telegram message is classified into one of four types and dispatched accordingly:

| **Message Type**     | **Detection Logic**                                       | **Handler**                    | **Response**                                         |
| -------------------- | --------------------------------------------------------- | ------------------------------ | ---------------------------------------------------- |
| Receipt image        | photo or document with image MIME type                    | extractor.handle_receipt()     | ✅ Logged €X.XX at Merchant — Category               |
| PDF — bank statement | document .pdf + filename contains konto/auszug/bank       | extractor.handle_bank_pdf()    | ✅ July statement: X transactions, €Y total expenses |
| PDF — payslip        | document .pdf + filename contains abrechnung/gehalts/lohn | extractor.handle_payslip_pdf() | ✅ July payslip: gross €X, net €Y, payout €Z         |
| Text query           | text message                                              | querier.handle_query()         | Natural language answer with figures                 |

_Security: all incoming messages must be validated against ALLOWED_TELEGRAM_USER_ID before processing. Reject and log any message from an unknown user ID._

## **4.4 Extractor Module (extractor.py)**

### **Receipt extraction**

Receipts are sent as Telegram photo messages or image document uploads. The extractor:

- Downloads the image from Telegram file API to memory (do not write to disk)
- Encodes image as base64
- Sends to Gemini 2.0 Flash with the receipt extraction prompt (see §4.6)
- Parses JSON response into a Receipt Pydantic model
- Writes one row to the receipts table in Turso
- Returns confirmation string to router

### **PDF extraction**

Bank statements and payslips are multi-page PDFs. The extractor:

- Downloads the PDF from Telegram file API to memory
- Uses pdfplumber to extract text from all pages
- Sends extracted text (not the PDF binary) to Gemini with the appropriate prompt
- Parses JSON response into BankStatement or Payslip Pydantic model
- Batch-inserts all transactions / payslip fields to Turso
- Returns summary confirmation string to router

_PDF text extraction via pdfplumber is used rather than sending the PDF binary to Gemini vision. This is more reliable for structured German financial documents and avoids multimodal token costs._

## **4.5 Querier Module (querier.py)**

Natural language queries are processed in two steps:

- Step 1 — Gemini converts the user's question to a SQL query against the Turso schema, guided by a system prompt that includes the full schema definition and example queries.
- Step 2 — The SQL is executed against Turso. Results are passed back to Gemini with a formatting prompt to produce a readable natural language answer.

Example interactions the querier must handle:

| **User message**                                | **Expected behaviour**                                                                                                                   |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| "How much did I spend on groceries last month?" | SQL: SELECT SUM(amount) FROM receipts WHERE category='Groceries' AND month. Returns: "🛒 Groceries July: €387.44 across 18 transactions" |
| "What is my savings rate this year?"            | Joins payslips + receipts tables. Computes (net_pay - total_expenses) / net_pay × 100                                                    |
| "Show me my top 5 merchants"                    | GROUP BY merchant ORDER BY SUM(amount) DESC LIMIT 5                                                                                      |
| "Any large transactions this week?"             | WHERE amount > 100 AND date >= date('now','-7 days')                                                                                     |
| "Compare July vs June grocery spend"            | Two separate SUMs, formatted as comparison                                                                                               |
| "What did I earn net this month?"               | SELECT payout FROM payslips WHERE period = current month                                                                                 |

## **4.6 Prompt Templates (prompts.py)**

### **RECEIPT_EXTRACTION_PROMPT**

```
You are a receipt data extraction assistant.
Extract data from this receipt image and return ONLY valid JSON.
No markdown, no explanation, no code fences.
Return exactly this structure:
{
  "date": "YYYY-MM-DD",
  "merchant": "<clean merchant name>",
  "total": <number>,
  "currency": "EUR",
  "category": "<one of: Groceries|Dining|Shopping|Utilities|
               Healthcare|Transport|Entertainment|Other>",
  "items": [{"description": "<item>", "amount": <number>}],
  "payment_method": "<cash|card|unknown>",
  "confidence": <0.0-1.0>
}
German receipts: amounts use comma as decimal separator (1,99 = 1.99).
If date not visible, use today's date.
```

### **BANK_STATEMENT_EXTRACTION_PROMPT**

Identical in structure to the prompt in the existing finanziq scripts/process_payslip.py. Reuse verbatim — the extraction logic is validated against real Sparkasse statements.

### **PAYSLIP_EXTRACTION_PROMPT**

Identical to the prompt in finanziq scripts/process_payslip.py. Reuse verbatim — validated against real Accenture/DATEV payslips.

### **NL_TO_SQL_PROMPT**

```
You are a SQL generation assistant for a personal finance database.
Given a user question, generate a single SQLite-compatible SQL query.
Return ONLY the SQL. No explanation, no markdown.
Schema:
  receipts(id, date, merchant, total, currency, category,
           payment_method, raw_json, created_at)
  transactions(id, date, description, merchant, amount,
               type, category, statement_month, created_at)
  payslips(id, year, month, gross_total, net_pay, payout,
           income_tax, social_security_total, employer,
           gross_ytd, tax_ytd, raw_json, created_at)
Rules:
  - "this month" = strftime('%Y-%m', 'now')
  - "last month" = strftime('%Y-%m', date('now','-1 month'))
  - expenses are negative amounts in transactions table
  - receipts.total is always positive
  - Use ABS() when summing expense amounts
  - Always add LIMIT 100 unless user asks for totals/averages
```

## **4.7 Database Schema (db.py)**

```
-- receipts: one row per scanned receipt image
CREATE TABLE IF NOT EXISTS receipts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  date         TEXT NOT NULL,
  merchant     TEXT,
  total        REAL NOT NULL,
  currency     TEXT DEFAULT 'EUR',
  category     TEXT,
  payment_method TEXT,
  raw_json     TEXT,
  created_at   TEXT DEFAULT (datetime('now'))
);
-- transactions: one row per bank statement line
CREATE TABLE IF NOT EXISTS transactions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  date            TEXT NOT NULL,
  description     TEXT,
  merchant        TEXT,
  amount          REAL NOT NULL,
  type            TEXT,
  category        TEXT,
  statement_month TEXT,
  created_at      TEXT DEFAULT (datetime('now'))
);
-- payslips: one row per monthly payslip
CREATE TABLE IF NOT EXISTS payslips (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  year                  INTEGER NOT NULL,
  month                 INTEGER NOT NULL,
  gross_total           REAL,
  net_pay               REAL,
  payout                REAL,
  income_tax            REAL,
  social_security_total REAL,
  employer              TEXT,
  gross_ytd             REAL,
  tax_ytd               REAL,
  raw_json              TEXT,
  created_at            TEXT DEFAULT (datetime('now')),
  UNIQUE(year, month)
);
```

## **4.8 Dockerfile**

```
FROM python:3.12-slim
WORKDIR /app
# System deps for pdfplumber
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev poppler-utils \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Cloud Run requires PORT env var
ENV PORT=8080
EXPOSE 8080
CMD ["python", "main.py"]
```

## **4.9 Requirements**

```
flask>=3.0
google-generativeai>=0.8
pdfplumber>=0.11
pydantic>=2.0
requests>=2.31
python-telegram-bot>=21.0
libsql-client>=0.3
Pillow>=10.0
```

# **5\. Deployment Guide**

## **5.1 Prerequisites**

- Google Cloud account with billing enabled (required even for free tier)
- gcloud CLI installed and authenticated
- Docker installed
- Telegram bot created via BotFather → token obtained
- Turso account created → database created → URL and token obtained
- Gemini API key from aistudio.google.com

## **5.2 One-Command Deploy (deploy.sh)**

The deploy.sh script handles the full deployment sequence:

```
#!/bin/bash
# deploy.sh — full finanzbot Cloud Run deployment
PROJECT_ID="your-gcp-project-id"
REGION="europe-west1"
SERVICE_NAME="finanzbot"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"
# 1. Build and push container
gcloud builds submit --tag $IMAGE
# 2. Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-secrets="TELEGRAM_BOT_TOKEN=telegram-bot-token:latest,\
    GEMINI_API_KEY=gemini-api-key:latest,\
    TURSO_DATABASE_URL=turso-db-url:latest,\
    TURSO_AUTH_TOKEN=turso-auth-token:latest,\
    ALLOWED_TELEGRAM_USER_ID=allowed-user-id:latest"
# 3. Register Telegram webhook
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region $REGION --format "value(status.url)")
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook\
  ?url=$SERVICE_URL/webhook"
echo "✅ finanzbot deployed to $SERVICE_URL"
echo "✅ Telegram webhook registered"
```

## **5.3 Secrets Setup**

Before running deploy.sh, store all secrets in Google Secret Manager:

```
echo -n "your-telegram-token"   | gcloud secrets create telegram-bot-token --data-file=-
echo -n "your-gemini-key"       | gcloud secrets create gemini-api-key --data-file=-
echo -n "libsql://db.turso.io"  | gcloud secrets create turso-db-url --data-file=-
echo -n "your-turso-token"      | gcloud secrets create turso-auth-token --data-file=-
echo -n "123456789"             | gcloud secrets create allowed-user-id --data-file=-
```

## **5.4 Turso Database Initialisation**

```
# Install Turso CLI
curl -sSfL https://get.tur.so/install.sh | bash
# Create database
turso db create finanzbot
# Get credentials
turso db show finanzbot --url
turso db tokens create finanzbot
# Schema is auto-applied on first Cloud Run startup via db.py init_schema()
```

# **6\. Migration from finanziq**

## **6.1 What to reuse**

| **finanziq asset**                          | **Action in finanzbot**                     | **Notes**                                                        |
| ------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------- |
| scripts/process_payslip.py — PAYSLIP_PROMPT | Copy verbatim into prompts.py               | Validated against real Accenture/DATEV payslips                  |
| scripts/process_payslip.py — BANK_PROMPT    | Copy verbatim into prompts.py               | Validated against real Sparkasse statements                      |
| data/processed/data.json                    | Migrate to Turso via one-off import script  | Seed historical data                                             |
| dashboard/index.html                        | Copy into finanzbot/dashboard/              | Serve at /dashboard route, update data source to query /api/data |
| Category logic & merchant mappings          | Copy into prompts.py bank extraction prompt | Already tuned for German merchants                               |

## **6.2 One-off historical data migration**

A migration script should be created to import the existing data.json into Turso:

```
# migrate_finanziq.py — run once to seed Turso from finanziq data.json
import json
from db import execute_turso_query, init_schema
data = json.loads(open("../finanziq/data/processed/data.json").read())
init_schema()  # create tables if not exist
for ps in data["payslips"]:
    execute_turso_query(
        "INSERT OR IGNORE INTO payslips ...", [...]
    )
for bs in data["bank_statements"]:
    for tx in bs["transactions"]:
        execute_turso_query(
            "INSERT INTO transactions ...", [...]
        )
print("Migration complete")
```

## **6.3 What NOT to migrate**

- scripts/generate_demo_data.py — not needed, Turso is the source of truth
- The Anthropic SDK dependency — replaced entirely by google-generativeai
- Local file manifest.json — replaced by Turso UNIQUE constraints

# **7\. Instructions for Claude Code / Antigravity CLI**

_Feed this entire section verbatim as the initial prompt when starting a Claude Code or Antigravity CLI session to implement finanzbot._

## **7.1 Briefing prompt**

```
You are implementing "finanzbot" — a Telegram bot for personal finance
automation. The full specification is in this document.
Existing codebase to reference (do not modify):
  C:\Users\g.aa.chandrasekaran\Code\finanziq
Create a NEW repository at:
  C:\Users\g.aa.chandrasekaran\Code\finanzbot
Implementation order:
  1. models.py          — Pydantic models (Receipt, Transaction, Payslip)
  2. db.py              — Turso HTTP client + init_schema()
  3. prompts.py         — All prompt templates (copy from finanziq spec)
  4. extractor.py       — Gemini vision + PDF extraction
  5. querier.py         — NL → SQL → answer pipeline
  6. router.py          — Message type detection + dispatch
  7. main.py            — Flask webhook server
  8. Dockerfile         — Python 3.12-slim
  9. deploy.sh          — Cloud Run deployment script
 10. migrate_finanziq.py — One-off data migration from finanziq
 11. tests/             — Unit tests for extractor and querier
Key constraints:
  - Use google-generativeai SDK, NOT anthropic SDK
  - Use Gemini model: gemini-2.0-flash
  - All DB operations via Turso HTTP API (not sqlite3 file)
  - Validate all Telegram messages against ALLOWED_TELEGRAM_USER_ID
  - Never write PDFs or images to disk — process in memory
  - Reuse extraction prompts verbatim from finanziq
  - Preserve dashboard/index.html exactly — serve at /dashboard
```

## **7.2 Validation checklist**

The implementation is complete when all of the following pass:

- python -m pytest tests/ — all tests pass
- Send a receipt photo to the bot → row appears in Turso receipts table
- Send a Sparkasse PDF → all transactions in Turso transactions table
- Send a payslip PDF → row in Turso payslips table with correct gross/net figures
- Ask "how much did I spend on groceries last month?" → correct € figure returned
- Ask "what is my savings rate?" → computed from payslips + transactions tables
- GET /dashboard → returns finanziq dashboard HTML
- Message from unknown Telegram user → rejected with no response
- docker build succeeds with no errors
- deploy.sh completes → webhook registered → bot responds on Telegram

# **8\. Future Enhancements (Out of Scope for v1)**

| **Feature**            | **Description**                                                                       | **Complexity** |
| ---------------------- | ------------------------------------------------------------------------------------- | -------------- |
| Monthly summary push   | Bot proactively sends a monthly summary on the 1st of each month via Cloud Scheduler  | Low            |
| Amex statement support | Add PDF extraction prompt for American Express statements                             | Low            |
| Budget alerts          | Telegram alert when a category exceeds a configurable monthly limit                   | Medium         |
| Multi-currency         | Handle travel receipts in non-EUR currencies, convert to EUR                          | Medium         |
| Dashboard live data    | Update dashboard/index.html to fetch from /api/data endpoint instead of embedded JSON | Medium         |
| Voice queries          | Accept Telegram voice messages, transcribe via Gemini, process as text query          | Medium         |
| Annual tax report      | Generate a PDF summary of income, deductions, and expenses for tax filing             | High           |

_finanzbot specification · v1.0 · September 2026 · Confidential_