# finanzbot

Personal finance automation via Telegram. Send a receipt photo, bank statement PDF, or payslip PDF — finanzbot extracts the data, stores it in a personal database, and lets you query it in plain language.

```
You → Telegram → finanzbot → Gemini + Turso → "You spent €1,284 last month"
```

---

## Why finanzbot?

Most finance apps require you to connect your bank account, sign up for a service, or enter data manually. finanzbot flips that:

- **Zero manual entry** — forward a document, data is extracted automatically
- **No bank login required** — works from the PDFs and receipts you already have
- **Your data stays yours** — stored in your own database on your own GCP project; no third-party SaaS holds your financial data
- **Built for German documents** — purpose-built for DATEV payslips and Sparkasse bank statements; generic apps frequently misread German formats
- **Ask in plain language** — no dashboard to learn, no filters to configure; just ask
- **Runs free** — Gemini, Turso, and Cloud Run free tiers cover personal use volume entirely

---

## What it does

- **Receipt photo** → reads merchant, date, total, and spending category
- **Bank statement PDF** → parses every transaction, assigns categories
- **Payslip PDF** → extracts gross, net, tax, and year-to-date figures
- **Text question** → converts to SQL, queries your database, replies in natural language

Runs entirely serverless on Google Cloud Run. Zero cost for personal use (Gemini, Turso, and Cloud Run all have generous free tiers).

---

## Quick start

1. [Set up secrets](docs/guide.md#secrets) in Google Secret Manager (5 values)
2. [Create a Turso database](docs/guide.md#turso-database-setup) and get the URL + token
3. Edit `PROJECT_ID` in `deploy.sh`, then run `./deploy.sh`
4. Send a receipt photo to your bot on Telegram

---

## Detailed guides

| Audience | Link |
|---|---|
| **Users** — what you can send, what you get back, privacy | [Guide → For Users](docs/guide.md#1-for-users) |
| **Developers & AI engineers** — tech stack, architecture, AI usage, tests | [Guide → For Developers](docs/guide.md#2-for-developers--ai-engineers) |
| **DevOps engineers** — Cloud Run, secrets, deploy, local dev | [Guide → For DevOps](docs/guide.md#3-for-devops-engineers) |
| **Product roadmap** — v1.1 polish → v2.0 agentic querier (ADK) | [Backlog](docs/backlog.md) |

---

## Tech stack (at a glance)

Python 3.12 · Flask · Gemini 2.0 Flash · Turso Edge SQLite · Google Cloud Run · Docker · Pydantic v2

---

## Routes

| Route | Description |
|---|---|
| `POST /webhook` | Telegram update receiver |
| `GET /dashboard` | Static finance dashboard |
| `GET /health` | Liveness probe |

---

## Running tests

```bash
python -m pytest tests/ -v
```

27 tests, no credentials required (all external calls mocked).
