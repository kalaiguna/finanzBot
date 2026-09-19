# finanzbot — Implementation Plan

_Based on `finanzbot_spec.md` v1.0 + analysis of `finanziq` codebase · September 2026_
_All decisions locked. See `CLAUDE.md` for constraints and git workflow._

---

## 1. Spec Validation

The spec architecture is sound. Key findings from the finanziq codebase audit:

### What the spec says to reuse — confirmed locations

| Spec instruction | finanziq location | Status |
|---|---|---|
| PAYSLIP_PROMPT → prompts.py | `scripts/process_payslip.py:133` | ✅ Ready to copy |
| BANK_PROMPT → prompts.py | `scripts/process_payslip.py:194` | ✅ Ready to copy |
| Category/merchant logic | `scripts/parsers/categorizer.py` (200+ rules, 160 lines) | ✅ Rich, copy whole file |
| data.json → Turso migration | `data/processed/data.json` (payslips + bank statements) | ✅ Exists |
| dashboard/index.html | `dashboard/index.html` | ✅ Exists |

### What the spec doesn't mention but exists in finanziq (important)

1. **Deterministic parsers** — `scripts/parsers/payslip_parser.py` and `bank_parser.py` are regex-based parsers that achieve ≥80% confidence on DATEV payslips and Sparkasse statements. This means the majority of PDF processing will never need a Gemini call. These should be integrated into `extractor.py` (same pattern as `process_payslip.py:259–295`).

2. **Receipts data** — Historical receipts are NOT in `data.json`. They live in `data/processed/receipts.json` (and a local SQLite `receipts.db`). The migration script in the spec only handles `data.json` — it needs a second pass for receipts.

3. **Rich receipt schema** — finanziq's `core/schemas.py` tracks item-level VAT detail (`ReceiptItem` with `vat_rate`, `qty`, `unit_price`). The spec's `receipts` table flattens this to `raw_json`. That's acceptable — items survive in `raw_json` for queries.

---

## 2. Technical Decisions (Locked)

| # | Decision | Rationale |
|---|---|---|
| D1 | Drop `python-telegram-bot`. Use direct `requests` to `api.telegram.org`. Keep Flask. | PTB v21 is async-only; Flask is sync. No reason to carry an async framework for simple webhook handling. |
| D2 | Include deterministic parsers (`payslip_parser.py`, `bank_parser.py`) in extractor.py. | Gemini is the fallback, not the default. 80%+ of PDFs never touch the API — faster, no quota, offline-capable. |
| D3 | Turso `db.py` via raw `requests` against HTTP pipeline API. No extra package. | `libsql-client` is deprecated on PyPI. HTTP API works everywhere, no deprecation risk, matches spec description. |
| D4 | Migrate both `data.json` (payslips + bank statements) AND `receipts.json` in `migrate_finanziq.py`. | Partial migration would corrupt aggregate queries like "how much did I spend on groceries this year?". |
| D5 | Receipt items stay in `raw_json` only. No `receipt_items` table in v1. | Adds schema and migration complexity for queries nobody uses in v1. Note as future extension in `db.py`. |
| D6 | Add `_hash TEXT UNIQUE` to both `transactions` and `receipts` tables. Use `INSERT OR IGNORE`. | 3 lines that prevent a whole class of re-upload bugs. Hash keys: transactions=`(date, description, amount, statement_month)`, receipts=`(date, merchant, total)`. |

### Gemini SDK note

`google-generativeai>=0.8` is the correct pip name. Model ID: `gemini-2.0-flash`. No changes from spec.

---

## 3. Phase Plan

Each phase maps to one feature branch (`phase/N-short-name`). After each phase:
1. **Code review** — correctness, constraints, security
2. **Doc review** — CLAUDE.md accuracy, inline comments, .env.example completeness
3. **Changelog entry** — fill in the `_pending_` entry in `CHANGELOG.md`
4. **Commit-ready notification** — user approves before any `git commit`

| Phase | Branch | Version | Deliverables |
|---|---|---|---|
| 1 | `phase/1-foundation` | 0.1.0 | `models.py`, `db.py`, `prompts.py`, `.env.example` |
| 2 | `phase/2-parsers` | 0.2.0 | `categorizer.py`, `parsers/` (3 files) |
| 3 | `phase/3-extractor` | 0.3.0 | `extractor.py` |
| 4 | `phase/4-querier` | 0.4.0 | `querier.py` |
| 5 | `phase/5-router-server` | 0.5.0 | `router.py`, `main.py` |
| 6 | `phase/6-migration` | 0.6.0 | `migrate_finanziq.py` |
| 7 | `phase/7-packaging` | 0.7.0 | `Dockerfile`, `requirements.txt`, `deploy.sh`, `dashboard/`, `README.md` |
| 8 | `phase/8-tests` | 1.0.0 | `tests/` (3 test files) → full checklist pass |

PRs are raised at logical feature boundaries: after Phase 2 (all static assets in), after Phase 5 (bot is functionally complete), and after Phase 8 (v1.0.0 release).

---

## 4. File-Level Implementation Notes

Files are listed in dependency order (each file only imports what's already written above it).

### Step 1 — `models.py`
Pydantic models. Source:
- `Receipt` — adapt from finanziq's `core/schemas.py:ReceiptData`
- `Transaction` — new (maps to transactions table)
- `Payslip` — adapt from finanziq's `data.json` payslip structure
- `BankStatement` — wraps a list of `Transaction`

### Step 2 — `db.py`
Turso HTTP client. Use `requests`, not `libsql-client`.

```python
# Pattern for all DB calls:
def _turso(sql: str, args: list = []) -> dict:
    resp = requests.post(
        f"{os.environ['TURSO_DATABASE_URL']}/v2/pipeline",
        headers={"Authorization": f"Bearer {os.environ['TURSO_AUTH_TOKEN']}"},
        json={"requests": [{"type": "execute", "stmt": {"sql": sql, "args": args}}]},
    )
    resp.raise_for_status()
    return resp.json()
```

Exports: `init_schema()`, `insert_receipt()`, `insert_transactions()`, `insert_payslip()`, `query()`.

### Step 3 — `prompts.py`
Copy verbatim from finanziq + add the NL_TO_SQL and ANSWER_FORMAT prompts from spec.

Sources:
- `PAYSLIP_PROMPT` ← `finanziq/scripts/process_payslip.py:133–192`
- `BANK_PROMPT` ← `finanziq/scripts/process_payslip.py:194–254`
- `RECEIPT_EXTRACTION_PROMPT` ← spec §4.6
- `NL_TO_SQL_PROMPT` ← spec §4.6
- `NL_TO_ANSWER_PROMPT` ← new (takes SQL result → readable answer)

### Step 4 — `parsers/` directory
Copy verbatim from finanziq. `categorizer.py` lives inside `parsers/` (not root) to preserve
the relative import `from .categorizer import categorize` in `bank_parser.py` unchanged.
- `parsers/categorizer.py` ← `finanziq/scripts/parsers/categorizer.py`
- `parsers/payslip_parser.py` ← `finanziq/scripts/parsers/payslip_parser.py`
- `parsers/bank_parser.py` ← `finanziq/scripts/parsers/bank_parser.py`
- `parsers/__init__.py` ← empty

These are dependency-free except `pdfplumber` and `re`.

### Step 6 — `extractor.py`
Core logic. Three public functions called by router:

```
handle_receipt(bot_file_id) -> str (confirmation message)
handle_bank_pdf(bot_file_id) -> str
handle_payslip_pdf(bot_file_id) -> str
```

Internal flow for PDFs:
1. Download from Telegram to `io.BytesIO` (never touch disk)
2. Try deterministic parser first (payslip_parser / bank_parser)
3. If confidence < 80: extract text with pdfplumber, send to Gemini
4. Parse JSON response → Pydantic model → insert to Turso
5. Return confirmation string

For receipts:
1. Download image bytes from Telegram
2. Base64-encode, send to Gemini with RECEIPT_EXTRACTION_PROMPT
3. Parse JSON → Receipt model → insert to Turso

Gemini client setup:
```python
import google.generativeai as genai
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")
```

### Step 7 — `querier.py`
Two-step NL query pipeline:
1. `model.generate_content([NL_TO_SQL_PROMPT, user_question])` → SQL string
2. `db.query(sql)` → rows
3. `model.generate_content([NL_TO_ANSWER_PROMPT, str(rows)])` → answer string

Safety: strip any non-SELECT SQL before executing (the prompt enforces SELECT-only, but validate defensively).

### Step 8 — `router.py`
Classify incoming Telegram update dict:

```python
def route(update: dict) -> str:
    msg = update.get("message", {})
    user_id = msg.get("from", {}).get("id")
    if str(user_id) != os.environ["ALLOWED_TELEGRAM_USER_ID"]:
        return None  # silently reject

    if msg.get("photo"):
        return extractor.handle_receipt(...)
    if doc := msg.get("document"):
        name = doc.get("file_name", "").lower()
        if doc["mime_type"] == "application/pdf":
            if any(k in name for k in ["abrechnung", "gehalts", "lohn", "brutto", "netto"]):
                return extractor.handle_payslip_pdf(...)
            if any(k in name for k in ["konto", "auszug"]):
                return extractor.handle_bank_pdf(...)
    if msg.get("text"):
        return querier.handle_query(msg["text"])
    return "❓ Unrecognised message type"
```

### Step 9 — `main.py`
Flask webhook server. Use `requests` directly for Telegram replies (not PTB).

```python
from flask import Flask, request, jsonify
import requests, os
from router import route

app = Flask(__name__)
BOT_URL = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    chat_id = update["message"]["chat"]["id"]
    reply = route(update)
    if reply:
        requests.post(f"{BOT_URL}/sendMessage",
                      json={"chat_id": chat_id, "text": reply})
    return jsonify({"ok": True})

@app.route("/dashboard")
def dashboard():
    return open("dashboard/index.html").read()

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    from db import init_schema
    init_schema()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
```

### Step 10 — `Dockerfile`
As specified in spec §4.8. No changes needed.

### Step 11 — `requirements.txt`

```
flask>=3.0
google-generativeai>=0.7
pdfplumber>=0.11
pydantic>=2.0
requests>=2.31
Pillow>=10.0
```

Removed: `python-telegram-bot`, `libsql-client` (both replaced by direct `requests` calls).

### Step 12 — `deploy.sh`
As specified in spec §5.2.

### Step 13 — `migrate_finanziq.py`
Migrates historical data from finanziq into Turso. Two data sources (not one):

```
../finanziq/data/processed/data.json   → payslips + transactions tables
../finanziq/data/processed/receipts.json → receipts table
```

Map finanziq's richer payslip structure to the flat `payslips` table fields.

### Step 14 — `tests/`

See §9 (Test Plan) for full case breakdown. Files:
- `tests/test_extractor.py`
- `tests/test_querier.py`
- `tests/test_router.py`

---

## 5. Data Migration Mapping

### `data.json` → `payslips` table

| data.json field | payslips column |
|---|---|
| `period.year` | `year` |
| `period.month` | `month` |
| `gross.total` | `gross_total` |
| `net_income.net_pay` | `net_pay` |
| `net_income.payout` | `payout` |
| `deductions.tax.income_tax` | `income_tax` |
| `deductions.social_security.total` | `social_security_total` |
| `employee.employer` | `employer` |
| `cumulative_ytd.gross_ytd` | `gross_ytd` |
| `cumulative_ytd.tax_ytd` | `tax_ytd` |
| whole record as JSON string | `raw_json` |

### `data.json` bank_statements → `transactions` table

Each `transaction` in each `bank_statement.transactions[]`:

| finanziq field | transactions column |
|---|---|
| `date` | `date` |
| `description` | `description` |
| `merchant` | `merchant` |
| `amount` | `amount` |
| `type` | `type` |
| `category` | `category` |
| parent `period.label` | `statement_month` |

### `receipts.json` → `receipts` table

| receipts.json field | receipts column |
|---|---|
| `date` | `date` |
| `store` | `merchant` |
| `total` | `total` |
| `payment_method` | `payment_method` |
| categorize(`store_chain`) | `category` |
| whole record as JSON | `raw_json` |

---

## 6. Deduplication Strategy

Both `receipts` and `transactions` tables get a `_hash TEXT UNIQUE` column. `INSERT OR IGNORE` on all inserts (both migration and live processing).

```sql
-- added to schema in db.py:
CREATE TABLE IF NOT EXISTS receipts (
  ...existing columns...,
  _hash TEXT UNIQUE   -- SHA-256 of (date || merchant || total)
);

CREATE TABLE IF NOT EXISTS transactions (
  ...existing columns...,
  _hash TEXT UNIQUE   -- SHA-256 of (date || description || amount || statement_month)
);
```

Hash computation in Python:
```python
import hashlib
def _hash(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
```

Edge case acknowledged: two receipts from the same merchant for the same total on the same day will collide. Extremely unlikely in personal use (~20 receipts/month). Noted as a known limitation in `db.py`.

---

## 7. Proposed PR Boundaries

| PR | Phases | Title | Rationale |
|---|---|---|---|
| PR-1 | 1–2 | `feat: foundation — models, db, prompts, parsers` | All static/reused assets in one PR; no runtime behaviour yet |
| PR-2 | 3–5 | `feat: bot core — extractor, querier, router, server` | Complete functional bot; reviewable end-to-end |
| PR-3 | 6–7 | `feat: migration + packaging` | Deploy-ready: historical data + container |
| PR-4 | 8 | `feat: tests + v1.0.0 release` | Closes the release checklist from spec §7.2 |

---

## 8. File Checklist

```
finanzbot/
├── models.py                  # Step 1
├── db.py                      # Step 2
├── prompts.py                 # Step 3
├── categorizer.py             # Step 4 (copy from finanziq)
├── parsers/
│   ├── __init__.py            # Step 5
│   ├── payslip_parser.py      # Step 5 (copy from finanziq)
│   └── bank_parser.py         # Step 5 (copy from finanziq)
├── extractor.py               # Step 6
├── querier.py                 # Step 7
├── router.py                  # Step 8
├── main.py                    # Step 9
├── Dockerfile                 # Step 10
├── requirements.txt           # Step 11
├── deploy.sh                  # Step 12
├── migrate_finanziq.py        # Step 13
├── .env.example               # (from spec §4.2)
├── dashboard/
│   └── index.html             # copy from finanziq/dashboard/index.html
└── tests/
    ├── test_extractor.py      # Step 14
    ├── test_querier.py        # Step 14
    └── test_router.py         # Step 14
```

---

## 9. Test Plan

Framework: `pytest`. Mocking: `unittest.mock.patch`. No real network calls, no real Turso DB, no real Gemini in unit tests.

---

### `tests/test_extractor.py`

#### Receipt handling

| ID | Case | Setup | Assert |
|---|---|---|---|
| R-01 | Valid receipt image | Mock Telegram file download → bytes; mock Gemini → valid JSON | `Receipt` model populated; `db.insert_receipt` called once with correct `merchant`, `total`, `_hash` |
| R-02 | Gemini returns malformed JSON | Mock Gemini → `"not json"` | `ValueError` caught internally; confirmation string contains "❌" or "failed" |
| R-03 | Gemini returns JSON missing required field | Mock Gemini → `{"date": "2026-01-01"}` (no `total`) | Pydantic `ValidationError` caught; graceful error reply |
| R-04 | Duplicate receipt (hash collision) | Insert once; mock Gemini → same receipt data again | `db.insert_receipt` called twice; second insert is `INSERT OR IGNORE` → no exception, idempotent reply |

#### Bank PDF handling

| ID | Case | Setup | Assert |
|---|---|---|---|
| B-01 | Deterministic parser confidence ≥ 80 | Mock `parse_bank_statement` → `{_confidence: 100, transactions: [...]}` | Gemini `generate_content` NOT called; `db.insert_transactions` called with correct rows |
| B-02 | Deterministic parser confidence < 80 | Mock `parse_bank_statement` → `{_confidence: 50}`; mock Gemini → valid bank JSON | Gemini IS called; transactions inserted from Gemini result |
| B-03 | In-memory only | Patch `open` / `tempfile` | No file path written to disk during PDF processing |
| B-04 | Zero transactions in statement | Deterministic parser returns `transactions: []` | Confirmation string mentions 0 transactions; no DB insert attempted |

#### Payslip PDF handling

| ID | Case | Setup | Assert |
|---|---|---|---|
| P-01 | Deterministic parser confidence ≥ 80 | Mock `parse_payslip` → `{_confidence: 100, ...}` | Gemini NOT called; `db.insert_payslip` called with correct gross/net/payout |
| P-02 | Deterministic parser confidence < 80 | Mock `parse_payslip` → `{_confidence: 40}`; mock Gemini → valid payslip JSON | Gemini IS called |
| P-03 | Duplicate payslip (same year+month) | `UNIQUE(year, month)` → second insert → `INSERT OR IGNORE` | No exception; reply indicates already recorded |

---

### `tests/test_querier.py`

| ID | Case | Setup | Assert |
|---|---|---|---|
| Q-01 | Valid NL query | Mock Gemini step-1 → `SELECT SUM(total) FROM receipts WHERE category='Groceries'`; mock Turso → `[[387.44]]`; mock Gemini step-2 → formatted answer | Final string returned contains `"387"` |
| Q-02 | Gemini generates non-SELECT SQL | Mock Gemini step-1 → `DELETE FROM receipts` | SQL rejected before Turso call; error reply returned; `db.query` NOT called |
| Q-03 | Gemini generates SQL with semicolon injection | Mock Gemini → `SELECT 1; DROP TABLE receipts` | Only the part before `;` passes, or entire query rejected |
| Q-04 | Turso returns empty result | Mock Turso → `[]` | Step-2 Gemini called with empty rows; graceful "no data found" answer returned (not an exception) |
| Q-05 | Gemini step-1 returns prose instead of SQL | Mock Gemini → `"I don't know"` | Caught gracefully; user-facing error reply; no Turso call |

---

### `tests/test_router.py`

| ID | Case | Setup | Assert |
|---|---|---|---|
| RT-01 | Photo from allowed user | Update with `photo` field, correct user ID | `extractor.handle_receipt` called |
| RT-02 | PDF "abrechnung" filename from allowed user | Document with `mime_type=application/pdf`, `file_name="Brutto-Netto-Abrechnung 2026 07 Juli.pdf"` | `extractor.handle_payslip_pdf` called |
| RT-03 | PDF "konto" filename from allowed user | Document with `file_name="Konto_1061013705-Auszug_2026_0007.PDF"` | `extractor.handle_bank_pdf` called |
| RT-04 | Text message from allowed user | `text: "how much did I spend last month?"` | `querier.handle_query` called with message text |
| RT-05 | Any message from unknown user | Correct structure but wrong `user_id` | Returns `None`; no handler called |
| RT-06 | Photo from unknown user | Photo message, wrong user ID | Returns `None`; `extractor.handle_receipt` NOT called |
| RT-07 | PDF with no recognisable keywords | `file_name="document.pdf"` | Falls through to unrecognised reply; no crash |
| RT-08 | Non-PDF document from allowed user | `mime_type=image/jpeg` as document | Not routed to PDF handler; treated as receipt or unrecognised |

---

### Spec §7.2 Validation Checklist (manual — Phase 8 sign-off gate)

These cannot be unit-tested; they require a running deployment:

- [ ] Send receipt photo → row in Turso `receipts`
- [ ] Send Sparkasse PDF → all transactions in `transactions`
- [ ] Send payslip PDF → correct gross/net in `payslips`
- [ ] Query "how much on groceries last month?" → correct € figure
- [ ] Query "what is my savings rate?" → computed from payslips + transactions
- [ ] `GET /dashboard` → returns finanziq HTML
- [ ] Message from unknown user → no response
- [ ] `docker build` succeeds
- [ ] `deploy.sh` completes → webhook registered → bot responds

---

_All decisions locked. Ready to implement._
