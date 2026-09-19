# Changelog

All notable changes to **finanzbot** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `docs/guide.md` — three-audience guide (users, developers, DevOps); includes detailed extractor sub-flow diagram and observability/cost-protection section
- `docs/backlog.md` — five-milestone product roadmap (v1.1 polish → v2.1 agentic insights); ADK adoption path documented

### Changed
- `README.md` — streamlined with "Why finanzbot?" section leading with the Telegram-in-the-moment pitch; links to all docs by audience
- `prompts.py` — `NL_TO_ANSWER_PROMPT` tightened: role preamble replaced with directive fragment style; "friendly" tone preserved in task line; "lead with the insight" instruction added
- `deploy.sh` — `--max-instances 3` added as cost-protection guard against runaway horizontal scaling
- `docs/spec.md` — Amex statement support removed from future enhancements (out of scope); personal local paths replaced with relative `../finanziq`
- `CLAUDE.md` — personal local path replaced with relative `../finanziq`

---

## [0.1.0] - Foundation — 2026-09-19

### Added
- `models.py` — Pydantic v2 models: `Receipt`, `Transaction`, `BankStatement`, `Payslip`; all monetary fields auto-rounded to 2 dp via `field_validator`
- `db.py` — Turso HTTP pipeline client (`requests` only, no libsql package); `init_schema()`, `insert_receipt()`, `insert_transactions()`, `insert_payslip()`, `query()`; deduplication via `_hash TEXT UNIQUE` on `receipts` (keyed on `date|merchant|total`) and `transactions` (keyed on `date|description|amount|statement_month`); all inserts are `INSERT OR IGNORE`
- `prompts.py` — `PAYSLIP_PROMPT` and `BANK_PROMPT` copied verbatim from finanziq (validated against real DATEV/Sparkasse documents); `RECEIPT_EXTRACTION_PROMPT` from spec; `NL_TO_SQL_PROMPT` from spec; `NL_TO_ANSWER_PROMPT` (new)
- `.env.example` — All 6 required environment variables with source instructions

---

## [0.2.0] - Parsers — 2026-09-19

### Added
- `parsers/categorizer.py` — Keyword-based German merchant → spending category classifier (200+ rules, copied verbatim from finanziq); placed inside `parsers/` to preserve the relative import in `bank_parser.py`
- `parsers/payslip_parser.py` — Deterministic DATEV Brutto-Netto-Abrechnung parser; returns `_confidence` 0–100; copied verbatim from finanziq
- `parsers/bank_parser.py` — Deterministic Sparkasse Kontoauszug parser; returns `_confidence` 0–100; copied verbatim from finanziq
- `parsers/__init__.py` — package marker

---

## [0.3.0] - Extractor — 2026-09-19

### Added
- `extractor.py` — Document extraction module: `handle_receipt()`, `handle_bank_pdf()`, `handle_payslip_pdf()`; deterministic-first strategy (confidence ≥ 80 skips Gemini, exception from parser also falls back gracefully); all file I/O in memory via `io.BytesIO`, nothing written to disk; `_fmt()` helper guards against `None` monetary values in confirmation strings

---

## [0.4.0] - Querier — 2026-09-19

### Added
- `querier.py` — Natural language query pipeline: NL → Gemini → SQL → Turso → Gemini → formatted answer; `_validate_sql()` strips to first semicolon-delimited statement and rejects anything that is not a SELECT before any DB call; empty result sets passed to Gemini for graceful natural-language "no data" responses

---

## [0.5.0] - Router & Server — 2026-09-19

### Added
- `router.py` — Telegram message classifier and dispatcher; validates `ALLOWED_TELEGRAM_USER_ID` (with `.strip()`) first and silently returns `None` for unknown users; bank keywords checked before payslip keywords to prevent 'netto' substring matching compound German words in bank filenames; `_largest_photo_id()` guards against empty photo arrays
- `main.py` — Flask webhook server; `db.init_schema()` called at module level (runs under gunicorn, not just direct execution); entire webhook handler wrapped in try/except so HTTP 200 is always returned; exception path attempts to send user-facing error reply; `_send()` logs Telegram API errors via `raise_for_status()`; `/dashboard` returns 404 on missing file; `/health` liveness probe

---

## [0.6.0] - Migration — 2026-09-19

### Added
- `migrate_finanziq.py` — One-off historical data import from `../finanziq/data/processed/data.json` (payslips + bank statement transactions) and `../finanziq/data/processed/receipts.json`; receipt `merchant` mapped from finanziq `store` field before hashing so dedup keys are consistent with live processing; category derived from full store name via `parsers.categorizer` (e.g. `"dm-drogerie markt"` → `Shopping`); re-runnable safely via `INSERT OR IGNORE`

---

## [0.7.0] - Packaging — 2026-09-19

### Added
- `Dockerfile` — Python 3.12-slim container with pdfplumber system deps (poppler)
- `requirements.txt` — Pinned dependencies; no `python-telegram-bot` or `libsql-client`
- `deploy.sh` — Cloud Run build + deploy + Telegram webhook registration in one script
- `dashboard/index.html` — Static finance dashboard preserved from finanziq; served at `/dashboard`
- `README.md` — Operational guide: prerequisites, secrets setup, deploy, first-run checklist

---

## [1.0.0] - First Deployable Bot — 2026-09-19

### Added
- `tests/test_extractor.py` — 11 unit tests covering receipt (4 cases), bank PDF (4 cases), payslip PDF (3 cases); mocked Gemini + Telegram file API; asserts deterministic-first path, in-memory-only constraint, dedup idempotency
- `tests/test_querier.py` — 5 unit tests: valid query round-trip, non-SELECT rejection, semicolon injection guard, empty Turso result, prose-instead-of-SQL fallback
- `tests/test_router.py` — 8 unit tests covering all 4 routing branches, unknown user ID rejection (2 cases), unrecognised file type, non-PDF document

### Changed
- Version bumped to 1.0.0 on passing full validation checklist from `finanzbot_spec.md §7.2`

---

### Historical Context

finanzbot replaces [finanziq](../finanziq) — a local Python script + static HTML dashboard — with a fully serverless, mobile-first Telegram bot. The finanziq codebase provided validated extraction logic (deterministic parsers, prompts, merchant categorizer) and historical financial data (payslips from July 2022, bank statements, receipts) that seed the Turso database on first deploy.
