import io
import json
import logging
import os
import re

import google.generativeai as genai
import pdfplumber
import requests
from PIL import Image

import db
from models import BankStatement, Payslip, Receipt, Transaction
from parsers.bank_parser import parse_bank_statement
from parsers.payslip_parser import parse_payslip
from prompts import BANK_PROMPT, PAYSLIP_PROMPT, RECEIPT_EXTRACTION_PROMPT

log = logging.getLogger(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
_model = genai.GenerativeModel("gemini-2.0-flash")

_TG_FILE_URL = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
_TG_DL_URL = f"https://api.telegram.org/file/bot{os.environ['TELEGRAM_BOT_TOKEN']}"

_CONFIDENCE_THRESHOLD = 80


# ── Helpers ───────────────────────────────────────────────────────────────────

def _download(file_id: str) -> bytes:
    r = requests.get(f"{_TG_FILE_URL}/getFile", params={"file_id": file_id}, timeout=10)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    dl = requests.get(f"{_TG_DL_URL}/{file_path}", timeout=30)
    dl.raise_for_status()
    return dl.content


def _pdf_text(pdf_bytes: bytes) -> str:
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n--- PAGE BREAK ---\n\n".join(pages)


def _extract_json(raw: str) -> dict:
    """Parse the first JSON object out of a Gemini response that may contain prose or fences."""
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start: i + 1])
    raise ValueError(f"No JSON object in Gemini response. First 200 chars: {raw[:200]}")


def _fmt(value: float | None) -> str:
    return f"€{value:.2f}" if value is not None else "€?"


def _try_det_bank(pdf_bytes: bytes) -> dict | None:
    try:
        result = parse_bank_statement(io.BytesIO(pdf_bytes))
        conf = result.get("_confidence", 0)
        if conf >= _CONFIDENCE_THRESHOLD:
            log.info("bank det parser confidence=%d%% — skipping Gemini", conf)
            return result
        log.info("bank det parser confidence=%d%% — falling back to Gemini", conf)
    except Exception as e:
        log.warning("bank det parser failed: %s — falling back to Gemini", e)
    return None


def _try_det_payslip(pdf_bytes: bytes) -> dict | None:
    try:
        result = parse_payslip(io.BytesIO(pdf_bytes))
        conf = result.get("_confidence", 0)
        if conf >= _CONFIDENCE_THRESHOLD:
            log.info("payslip det parser confidence=%d%% — skipping Gemini", conf)
            return result
        log.info("payslip det parser confidence=%d%% — falling back to Gemini", conf)
    except Exception as e:
        log.warning("payslip det parser failed: %s — falling back to Gemini", e)
    return None


# ── Public handlers ───────────────────────────────────────────────────────────

def handle_receipt(file_id: str) -> str:
    image_bytes = _download(file_id)
    image = Image.open(io.BytesIO(image_bytes))
    response = _model.generate_content([RECEIPT_EXTRACTION_PROMPT, image])
    data = _extract_json(response.text)

    receipt = Receipt(
        date=data["date"],
        merchant=data.get("merchant", "Unknown"),
        total=float(data["total"]),
        currency=data.get("currency", "EUR"),
        category=data.get("category", "Other"),
        payment_method=data.get("payment_method", "unknown"),
        raw_json=json.dumps(data, ensure_ascii=False),
    )
    db.insert_receipt(receipt)
    return f"✅ Logged {_fmt(receipt.total)} at {receipt.merchant} — {receipt.category}"


def handle_bank_pdf(file_id: str) -> str:
    pdf_bytes = _download(file_id)
    data = _try_det_bank(pdf_bytes)

    if data is None:
        response = _model.generate_content([BANK_PROMPT, _pdf_text(pdf_bytes)])
        data = _extract_json(response.text)

    period = data.get("period", {})
    statement_month = period.get("label") or f"{period.get('month', '?')}/{period.get('year', '?')}"

    txns = [
        Transaction(
            date=t["date"],
            description=t.get("description", ""),
            merchant=t.get("merchant", ""),
            amount=float(t["amount"]),
            type=t.get("type", ""),
            category=t.get("category", "Other"),
            statement_month=statement_month,
        )
        for t in data.get("transactions", [])
    ]
    db.insert_transactions(txns)

    total_expenses = abs(sum(t.amount for t in txns if t.amount < 0))
    return (
        f"✅ {statement_month} statement: {len(txns)} transactions, "
        f"{_fmt(total_expenses)} total expenses"
    )


def handle_payslip_pdf(file_id: str) -> str:
    pdf_bytes = _download(file_id)
    data = _try_det_payslip(pdf_bytes)

    if data is None:
        response = _model.generate_content([PAYSLIP_PROMPT, _pdf_text(pdf_bytes)])
        data = _extract_json(response.text)

    period = data.get("period", {})
    gross = data.get("gross", {})
    net_income = data.get("net_income", {})
    deductions = data.get("deductions", {})
    ytd = data.get("cumulative_ytd", {})

    payslip = Payslip(
        year=period.get("year", 0),
        month=period.get("month", 0),
        gross_total=gross.get("total"),
        net_pay=net_income.get("net_pay"),
        payout=net_income.get("payout"),
        income_tax=deductions.get("tax", {}).get("income_tax"),
        social_security_total=deductions.get("social_security", {}).get("total"),
        employer=data.get("employee", {}).get("employer"),
        gross_ytd=ytd.get("gross_ytd"),
        tax_ytd=ytd.get("tax_ytd"),
        raw_json=json.dumps(data, ensure_ascii=False),
    )
    db.insert_payslip(payslip)

    label = period.get("label") or f"{period.get('month', '?')}/{period.get('year', '?')}"
    return (
        f"✅ {label} payslip: gross {_fmt(payslip.gross_total)}, "
        f"net {_fmt(payslip.net_pay)}, payout {_fmt(payslip.payout)}"
    )
