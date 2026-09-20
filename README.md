# finanzbot

Personal finance automation via Telegram. Send a receipt photo, bank statement PDF, or payslip PDF; finanzbot extracts the data, stores it in a personal database, and lets you query it in plain language.

```
You → Telegram → finanzbot → Gemini + Turso → "You spent €1,284 last month"
```

---

## Why finanzbot?

Most finance apps sit on your home screen waiting for you to open them, navigate to the right screen, and type something in. finanzbot lives in Telegram, where you already are.

Done shopping? Snap the receipt, send it. Payslip arrived? Forward the PDF. That's the entire workflow: no app to open, no form to fill, no category to pick from a dropdown.

A few things that make it different:

- **Capture in the moment:** Telegram is always a swipe away; the friction of opening a dedicated finance app is enough to make most people skip it
- **No manual entry, ever:** photo or PDF in, structured data out
- **Ask instead of navigate:** "how much did I spend on dining this month?" beats hunting through filters and date pickers
- **No bank login required:** works from the PDFs and receipts you already have; no OAuth dance with your bank
- **Your data, your infrastructure:** stored in your own database; no third-party SaaS holds your financial records
- **Built for German documents:** purpose-built for DATEV payslips and Sparkasse statements; generic apps frequently misread German formats
- **Free to run:** Gemini, Turso, and Cloud Run free tiers cover personal use entirely

---

## What it does

- **Receipt photo** → reads merchant, date, total, and spending category
- **Bank statement PDF** → parses every transaction, assigns categories
- **Payslip PDF** → extracts gross, net, tax, and year-to-date figures
- **Text question** → converts to SQL, queries your database, replies in natural language

Runs entirely serverless on Google Cloud Run. Zero cost for personal use (Gemini, Turso, and Cloud Run all have generous free tiers).

---

## Is it safe to send payslips and bank statements through Telegram?

This is the right question to ask. Here is exactly what happens to your documents:

1. **Telegram:** Telegram encrypts messages in transit (TLS) and at rest on their servers. The bot only receives the message because you explicitly sent it to your own bot token. Nobody else's bot can read your messages.

2. **Your Cloud Run instance:** the document is downloaded directly from Telegram's servers into memory. It is never written to disk. Once data is extracted, the raw file is discarded; it does not go anywhere else.

3. **Gemini:** if the deterministic parser cannot read the document with sufficient confidence, the text (not the original file) is sent to Gemini for extraction. Google's [API data usage policy](https://ai.google.dev/gemini-api/terms) for API calls does not use your data to train models.

4. **Turso:** only the structured fields (amounts, dates, categories) are stored. Raw PDFs and images are never persisted anywhere.

5. **You own everything:** the bot runs in your GCP project, the database is your Turso account. There is no shared backend, no analytics pipeline, no third party that holds your data.

The single-user lock (`ALLOWED_TELEGRAM_USER_ID`) means the bot silently ignores any message not from you; no reply, no log of the content.

→ Full security details: [Guide → Security](docs/guide.md#security)

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
| **Users:** what you can send, what you get back, privacy | [Guide → For Users](docs/guide.md#1-for-users) |
| **Developers & AI engineers:** tech stack, architecture, AI usage, tests | [Guide → For Developers](docs/guide.md#2-for-developers--ai-engineers) |
| **DevOps engineers:** Cloud Run, secrets, deploy, local dev | [Guide → For DevOps](docs/guide.md#3-for-devops-engineers) |
| **Product roadmap:** v1.1 polish → v2.0 agentic querier (ADK) | [Backlog](docs/backlog.md) |

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

## Extending finanzbot

finanzbot is designed to be adapted. Common extension points:

- **Different bank:** add a deterministic parser in `parsers/`, register its filename keywords in `router.py`
- **New document type** (e.g. ETF statements, investment PDFs): add a model in `models.py`, a table in `db.py`, a prompt in `prompts.py`, a handler in `extractor.py`, and a routing branch in `router.py`
- **Different Gemini model:** swap `"gemini-2.0-flash"` in `extractor.py` and `querier.py` for any Gemini variant; for full provider neutrality (Claude, GPT-4o, etc.) see [LiteLLM](https://docs.litellm.ai); the change stays within those two files

Full extension guide: [Guide → Extending finanzbot](docs/guide.md#extending-finanzbot)

---

## Running tests

```bash
python -m pytest tests/ -v
```

27 tests, no credentials required (all external calls mocked).

---

## License

[MIT](LICENSE); fork it, adapt it, self-host it. The only requirement is attribution.
