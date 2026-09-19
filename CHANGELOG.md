# Changelog

All notable changes to **finanzbot** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

> Phases in progress. Entries accumulate here until a phase is merged.

---

## [0.1.0] - Foundation — _pending_

### Added
- `models.py` — Pydantic v2 models: `Receipt`, `Transaction`, `BankStatement`, `Payslip`
- `db.py` — Turso HTTP pipeline client; `init_schema()`, `insert_receipt()`, `insert_transactions()`, `insert_payslip()`, `query()`; deduplication via `_hash TEXT UNIQUE` on `receipts` and `transactions`
- `prompts.py` — All Gemini prompt templates: `PAYSLIP_PROMPT`, `BANK_PROMPT` (copied verbatim from finanziq), `RECEIPT_EXTRACTION_PROMPT`, `NL_TO_SQL_PROMPT`, `NL_TO_ANSWER_PROMPT`
- `.env.example` — Required environment variable reference

---

## [0.2.0] - Parsers — _pending_

### Added
- `categorizer.py` — Keyword-based German merchant → spending category classifier (200+ rules, copied from finanziq)
- `parsers/payslip_parser.py` — Deterministic DATEV Brutto-Netto-Abrechnung parser; returns `_confidence` 0–100 (copied from finanziq)
- `parsers/bank_parser.py` — Deterministic Sparkasse Kontoauszug parser; returns `_confidence` 0–100 (copied from finanziq)

---

## [0.3.0] - Extractor — _pending_

### Added
- `extractor.py` — Document extraction module: `handle_receipt()`, `handle_bank_pdf()`, `handle_payslip_pdf()`; deterministic-first strategy (confidence ≥ 80 skips Gemini); all file I/O in memory via `io.BytesIO`

---

## [0.4.0] - Querier — _pending_

### Added
- `querier.py` — Natural language query pipeline: NL → Gemini → SQL → Turso → Gemini → formatted answer; SELECT-only guard on generated SQL

---

## [0.5.0] - Router & Server — _pending_

### Added
- `router.py` — Telegram message classifier and dispatcher; user ID validation (`ALLOWED_TELEGRAM_USER_ID`) with silent rejection of unknown users
- `main.py` — Flask webhook server; `/webhook` POST handler; `/dashboard` static HTML route; `/health` liveness probe; `init_schema()` on startup

---

## [0.6.0] - Migration — _pending_

### Added
- `migrate_finanziq.py` — One-off historical data import from finanziq: `data/processed/data.json` (payslips + bank statement transactions) and `data/processed/receipts.json`; dedup-safe via `INSERT OR IGNORE` with `_hash`

---

## [0.7.0] - Packaging — _pending_

### Added
- `Dockerfile` — Python 3.12-slim container with pdfplumber system deps (poppler)
- `requirements.txt` — Pinned dependencies; no `python-telegram-bot` or `libsql-client`
- `deploy.sh` — Cloud Run build + deploy + Telegram webhook registration in one script
- `dashboard/index.html` — Static finance dashboard preserved from finanziq; served at `/dashboard`
- `README.md` — Operational guide: prerequisites, secrets setup, deploy, first-run checklist

---

## [1.0.0] - First Deployable Bot — _pending_

### Added
- `tests/test_extractor.py` — Unit tests for extraction paths (mocked Gemini + Telegram file API)
- `tests/test_querier.py` — Unit tests for NL→SQL→answer pipeline (mocked Gemini + Turso)
- `tests/test_router.py` — Unit tests for all 4 routing branches + user ID rejection

### Changed
- Version bumped to 1.0.0 on passing full validation checklist from `finanzbot_spec.md §7.2`

---

### Historical Context

finanzbot replaces [finanziq](../finanziq) — a local Python script + static HTML dashboard — with a fully serverless, mobile-first Telegram bot. The finanziq codebase provided validated extraction logic (deterministic parsers, prompts, merchant categorizer) and historical financial data (payslips from July 2022, bank statements, receipts) that seed the Turso database on first deploy.
