# finanzbot: Product Backlog

> Validated against v1.0.0 codebase. Items marked **[ADK]** require migrating from direct `google-generativeai` SDK calls to Google Agent Development Kit.

---

## Milestone map

| Version | Theme | AI approach |
|---|---|---|
| v1.0.0 | Foundation (shipped ✅) | Direct SDK: Gemini is a tool your code calls |
| v1.1.0 | Reliability & polish | Direct SDK |
| v1.2.0 | Proactive automation | Direct SDK |
| v1.3.0 | Dashboard integration | Direct SDK |
| v2.0.0 | Agentic querier | **[ADK]:** Gemini becomes an agent your code delegates to |
| v2.1.0 | Agentic insights | **[ADK]** |

---

## v1.0.0: Foundation ✅

All items shipped and merged to `main` on 2026-09-19.

- `models.py`: Pydantic v2 models: Receipt, Transaction, BankStatement, Payslip
- `db.py`: Turso HTTP pipeline client, schema init, dedup hashes
- `prompts.py`: all Gemini prompt templates
- `parsers/categorizer.py`: 200+ merchant → category rules
- `parsers/bank_parser.py`: deterministic Sparkasse parser
- `parsers/payslip_parser.py`: deterministic DATEV payslip parser
- `extractor.py`: receipt + bank PDF + payslip ingestion pipeline
- `querier.py`: two-step NL → SQL → answer
- `router.py`: message classification and user ID security gate
- `main.py`: Flask webhook, `/dashboard`, `/health`
- `Dockerfile`, `deploy.sh`, `requirements.txt`
- `migrate_finanziq.py`: seed Turso from finanziq historical data
- `tests/`: 27 unit tests across extractor, querier, router

---

## v1.1.0: Reliability & Polish

> All items use direct `google-generativeai` SDK. No architectural changes.

- **Unknown PDF clarification:** when a PDF filename contains no recognised keyword, ask the user to clarify ("Is this a bank statement or payslip?") rather than silently defaulting to bank statement
- **Structured Telegram replies:** use Telegram MarkdownV2 formatting: bold amounts, category emoji, aligned columns
- **/summary command:** user sends `/summary` → bot replies with current month snapshot: income, total expenses, top 3 spending categories, savings rate
- **/help command:** lists supported document types, example questions, and bot capabilities
- **Graceful error replies:** specific messages when Gemini returns malformed JSON, Turso is unreachable, or a PDF is password-protected

---

## v1.2.0: Proactive Automation

> All items use direct SDK. Introduces Cloud Scheduler and a new `budgets` table.

- **Monthly push summary:** Cloud Scheduler triggers on the 1st of each month; bot sends an unprompted summary to the user
- **Budget alerts:** configurable per-category monthly limits stored in a `budgets` table; bot sends a Telegram alert at 80% and 100% thresholds
- **Duplicate upload notification:** when the dedup hash fires, notify the user explicitly ("⚠️ This statement looks like it was already uploaded") instead of silently ignoring
- **Multi-user foundation:** replace `ALLOWED_TELEGRAM_USER_ID` single env var with a `users` table; each user gets their own data partition in Turso

---

## v1.3.0: Dashboard Integration

> All items use direct SDK. Bridges the static dashboard with live Turso data.

- **Live data endpoint:** add `GET /api/data` route to `main.py` that queries Turso and returns the same JSON shape as finanziq's `data.json`
- **Dashboard update:** modify `dashboard/index.html` to fetch from `/api/data` instead of embedded JSON; any month's data loads automatically
- **Receipt line items:** add a `receipt_items` table; update the Gemini receipt prompt to extract individual items; enables queries like "how much did I spend on produce across all receipts?"

---

## v2.0.0: Agentic Querier **[ADK]**

> This milestone replaces `querier.py` with a Google ADK agent. Everything else (ingestion pipeline, database, router, Telegram interface) remains unchanged. That seam is intentional.

**Why ADK here?** In v1.x the querier calls Gemini twice with fixed prompts: NL→SQL, then rows→answer. The model has no ability to decide what to do next. ADK flips this: Gemini becomes the orchestrator and calls a `query_db` tool as many times as it needs before composing an answer.

- **Replace `querier.py` with an ADK agent:** Gemini decides which SQL queries to run, calls the `query_db` tool iteratively, synthesises results
- **Multi-part question handling:** "Compare groceries this month vs last month and show me the top 5 new merchants" resolved without compound SQL prompt engineering
- **Clarification dialogue:** agent asks a follow-up when the user's question is ambiguous, rather than guessing
- **Conversation context:** agent retains context within a thread ("now filter that to just weekends" after a prior query)

---

## v2.1.0: Agentic Insights **[ADK]**

> Extends the ADK adoption to proactive, unprompted analysis.

- **Anomaly detection on upload:** agent reviews new transactions at ingest time and flags anything unusual: new merchant, amount significantly above category average, or a transaction that looks like a duplicate but passed the hash check
- **Voice queries:** accept Telegram voice messages, transcribe via Gemini, route through the agentic querier
- **Annual tax summary:** agent composes a structured income and deductions report suitable for a Steuerberater (German tax advisor)

---

## Out of scope (will not be added)

- Amex / credit card statement parsing: finanzbot targets Sparkasse bank statements and DATEV payslips
- Multi-currency receipt handling: all amounts stored and queried in EUR
- OCR for handwritten receipts: Gemini Vision handles printed receipts; handwritten are out of scope
