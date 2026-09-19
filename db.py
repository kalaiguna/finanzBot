import hashlib
import logging
import os

import requests

from models import Payslip, Receipt, Transaction

log = logging.getLogger(__name__)

# libsql:// → https:// for the HTTP pipeline endpoint
_DB_URL = os.environ["TURSO_DATABASE_URL"].replace("libsql://", "https://") + "/v2/pipeline"
_HEADERS = {
    "Authorization": f"Bearer {os.environ['TURSO_AUTH_TOKEN']}",
    "Content-Type": "application/json",
}


# ── Transport ─────────────────────────────────────────────────────────────────

def _arg(v) -> dict:
    """Convert a Python scalar to a Turso typed argument object."""
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": str(v)}
    return {"type": "text", "value": str(v)}


def _turso(sql: str, args: list = ()) -> dict:
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in args]}},
            {"type": "close"},
        ]
    }
    resp = requests.post(_DB_URL, headers=_HEADERS, json=payload, timeout=10)
    resp.raise_for_status()
    result = resp.json()["results"][0]
    if result["type"] == "error":
        raise RuntimeError(f"Turso error: {result['error']['message']}")
    return result["response"]["result"]


# ── Deduplication ─────────────────────────────────────────────────────────────

def _hash(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


# ── Schema ────────────────────────────────────────────────────────────────────

def init_schema() -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS receipts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT    NOT NULL,
            merchant       TEXT,
            total          REAL    NOT NULL,
            currency       TEXT    DEFAULT 'EUR',
            category       TEXT,
            payment_method TEXT,
            raw_json       TEXT,
            created_at     TEXT    DEFAULT (datetime('now')),
            _hash          TEXT    UNIQUE
        )""",
        """CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT    NOT NULL,
            description     TEXT,
            merchant        TEXT,
            amount          REAL    NOT NULL,
            type            TEXT,
            category        TEXT,
            statement_month TEXT,
            created_at      TEXT    DEFAULT (datetime('now')),
            _hash           TEXT    UNIQUE
        )""",
        """CREATE TABLE IF NOT EXISTS payslips (
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
        )""",
    ]
    for sql in statements:
        _turso(sql)
    log.info("Schema initialised")


# ── Writers ───────────────────────────────────────────────────────────────────

def insert_receipt(r: Receipt) -> None:
    h = _hash(r.date, r.merchant, r.total)
    _turso(
        """INSERT OR IGNORE INTO receipts
           (date, merchant, total, currency, category, payment_method, raw_json, _hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [r.date, r.merchant, r.total, r.currency, r.category, r.payment_method, r.raw_json, h],
    )


def insert_transactions(txns: list[Transaction]) -> None:
    for t in txns:
        h = _hash(t.date, t.description, t.amount, t.statement_month)
        _turso(
            """INSERT OR IGNORE INTO transactions
               (date, description, merchant, amount, type, category, statement_month, _hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [t.date, t.description, t.merchant, t.amount, t.type, t.category, t.statement_month, h],
        )


def insert_payslip(p: Payslip) -> None:
    _turso(
        """INSERT OR IGNORE INTO payslips
           (year, month, gross_total, net_pay, payout, income_tax,
            social_security_total, employer, gross_ytd, tax_ytd, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [p.year, p.month, p.gross_total, p.net_pay, p.payout, p.income_tax,
         p.social_security_total, p.employer, p.gross_ytd, p.tax_ytd, p.raw_json],
    )


# ── Reader ────────────────────────────────────────────────────────────────────

def query(sql: str, args: list = ()) -> list[dict]:
    result = _turso(sql, args)
    cols = [c["name"] for c in result["cols"]]
    return [
        {col: cell.get("value") for col, cell in zip(cols, row)}
        for row in result["rows"]
    ]
