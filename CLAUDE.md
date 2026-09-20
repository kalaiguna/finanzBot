# finanzbot: Claude Code Instructions

## What this project is

finanzbot is a serverless Telegram bot for personal finance automation. Users send receipt photos, bank statement PDFs, and payslip PDFs via Telegram; the bot extracts structured data and stores it in Turso Edge SQLite. Natural language queries ("how much did I spend on groceries last month?") are answered via Gemini + NL→SQL.

It **replaces** the finanziq local-script + static-dashboard project (expected at `../finanziq` relative to this repo).

Full spec: `docs/spec.md`
Implementation plan (phases, decisions): `docs/implementation-plan.md`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12, Flask (sync WSGI) |
| AI | Gemini 2.0 Flash via `google-generativeai` SDK |
| Database | Turso Edge SQLite (HTTP pipeline API only; no libsql package) |
| Telegram | Direct `requests` to `api.telegram.org` (no python-telegram-bot) |
| PDF parsing | `pdfplumber` |
| Validation | Pydantic v2 |
| Container | Docker (python:3.12-slim) |
| Deploy target | Google Cloud Run |

---

## Key Constraints (never violate these)

- **Never write PDFs or images to disk:** download to `io.BytesIO`, process in memory, discard.
- **Validate every Telegram message** against `ALLOWED_TELEGRAM_USER_ID` before any processing. Silently reject unknown users (no response, no log of content).
- **Deterministic parsers first:** `parsers/payslip_parser.py` and `parsers/bank_parser.py` run before Gemini. Only call Gemini if confidence < 80. Gemini is the fallback, not the default.
- **Turso via HTTP only:** all DB calls go through `db.py`'s `_turso()` helper. Never import `sqlite3` or any libsql package.
- **INSERT OR IGNORE with `_hash`:** both `receipts` and `transactions` tables have a `_hash TEXT UNIQUE` column. Always compute and pass the hash; never insert without it.
- **SELECT-only queries:** `querier.py` must strip and reject any non-SELECT SQL before executing against Turso.
- **No comments explaining WHAT the code does:** only WHY when non-obvious (hidden constraint, workaround, invariant). No docstring novels.

---

## What to reuse from finanziq (never rewrite from scratch)

| Asset | Source location |
|---|---|
| `PAYSLIP_PROMPT` | `finanziq/scripts/process_payslip.py:133` |
| `BANK_PROMPT` | `finanziq/scripts/process_payslip.py:194` |
| `parsers/payslip_parser.py` | `finanziq/scripts/parsers/payslip_parser.py` |
| `parsers/bank_parser.py` | `finanziq/scripts/parsers/bank_parser.py` |
| `parsers/categorizer.py` | `finanziq/scripts/parsers/categorizer.py` |
| `dashboard/index.html` | `finanziq/dashboard/index.html` |

When copying these files, preserve them exactly. Do not refactor, rename, or "improve" them; they are validated against real German financial documents.

---

## Git & Review Workflow

**Never commit to git.** When a phase is complete:
1. Run the phase's review (code + doc + changelog)
2. Notify the user: "Phase N complete; ready to commit: `<1-liner message>`"
3. If the phase closes a logical feature boundary, also draft a PR summary
4. Wait for user approval before any `git commit` or `git push`

Branch naming: `phase/N-short-name` (e.g. `phase/1-foundation`, `phase/3-extractor`)

---

## Phase Map

| Phase | Branch | Deliverables |
|---|---|---|
| 1 | `phase/1-foundation` | `models.py`, `db.py`, `prompts.py`, `.env.example` |
| 2 | `phase/2-parsers` | `categorizer.py`, `parsers/` (3 files, copied from finanziq) |
| 3 | `phase/3-extractor` | `extractor.py` |
| 4 | `phase/4-querier` | `querier.py` |
| 5 | `phase/5-router-server` | `router.py`, `main.py` |
| 6 | `phase/6-migration` | `migrate_finanziq.py` |
| 7 | `phase/7-packaging` | `Dockerfile`, `requirements.txt`, `deploy.sh`, `dashboard/`, README |
| 8 | `phase/8-tests` | `tests/` (extractor, querier, router) |

Each phase ends with: code review → doc review → changelog entry → commit-ready notification.

---

## Code Style

- Python 3.12: use `|` union types, `match` where natural, f-strings throughout
- Pydantic v2: use `model_validate()`, not `parse_obj()`
- No `print()` in library code: use `logging` with a named logger
- All monetary values as Python `float` (SQLite REAL); round to 2dp before storing
- Dates always as ISO 8601 strings (`"YYYY-MM-DD"`); no datetime objects in DB layer
- Environment variables always via `os.environ["KEY"]` (hard fail if missing); never `os.getenv("KEY", default)` for required vars

---

## Changelog Format

Follow Keep a Changelog (https://keepachangelog.com). Sections: Added / Changed / Fixed / Removed.
Versioning: 0.x.0 per phase until first deployable bot (Phase 7 = v1.0.0).

File: `CHANGELOG.md`
