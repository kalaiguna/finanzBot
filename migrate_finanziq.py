#!/usr/bin/env python3
"""
migrate_finanziq.py — One-off script to seed Turso with finanziq historical data.

Run once after first deployment (env vars must be set):
  python migrate_finanziq.py

Sources:
  ../finanziq/data/processed/data.json     → payslips + transactions tables
  ../finanziq/data/processed/receipts.json → receipts table

Re-running is safe — all inserts use INSERT OR IGNORE.
"""

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_FINANZIQ = Path(__file__).parent.parent / "finanziq"
_DATA_JSON = _FINANZIQ / "data" / "processed" / "data.json"
_RECEIPTS_JSON = _FINANZIQ / "data" / "processed" / "receipts.json"


def _verify_sources() -> None:
    missing = [p for p in (_DATA_JSON, _RECEIPTS_JSON) if not p.exists()]
    if missing:
        for p in missing:
            log.error("Source not found: %s", p)
        sys.exit(1)


# ── Payslips ──────────────────────────────────────────────────────────────────

def _migrate_payslips(payslips: list) -> int:
    from models import Payslip
    import db

    for i, ps in enumerate(payslips, 1):
        period = ps.get("period", {})
        gross = ps.get("gross", {})
        net = ps.get("net_income", {})
        ded = ps.get("deductions", {})
        ytd = ps.get("cumulative_ytd", {})

        db.insert_payslip(Payslip(
            year=period.get("year", 0),
            month=period.get("month", 0),
            gross_total=gross.get("total"),
            net_pay=net.get("net_pay"),
            payout=net.get("payout"),
            income_tax=ded.get("tax", {}).get("income_tax"),
            social_security_total=ded.get("social_security", {}).get("total"),
            employer=ps.get("employee", {}).get("employer"),
            gross_ytd=ytd.get("gross_ytd"),
            tax_ytd=ytd.get("tax_ytd"),
            raw_json=json.dumps(ps, ensure_ascii=False),
        ))
        log.info("  [%d/%d] payslip %s", i, len(payslips), period.get("label", ""))

    return len(payslips)


# ── Bank statements → transactions ────────────────────────────────────────────

def _migrate_bank_statements(bank_statements: list) -> int:
    from models import Transaction
    import db

    total_txns = 0
    for bs in bank_statements:
        period = bs.get("period", {})
        statement_month = (
            period.get("label")
            or f"{period.get('month', '?')}/{period.get('year', '?')}"
        )
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
            for t in bs.get("transactions", [])
        ]
        db.insert_transactions(txns)
        total_txns += len(txns)
        log.info("  %s: %d transactions", statement_month, len(txns))

    return total_txns


# ── Receipts ──────────────────────────────────────────────────────────────────

def _migrate_receipts(receipts: list) -> int:
    from models import Receipt
    from parsers.categorizer import categorize
    import db

    for i, r in enumerate(receipts, 1):
        # Use full store name for categorization — 'dm-drogerie markt' matches 'dm-' rule
        merchant = r.get("store", "Unknown")
        category = categorize(merchant, "")

        db.insert_receipt(Receipt(
            date=r["date"],
            merchant=merchant,      # hash keyed on this post-mapped value
            total=float(r["total"]),
            currency="EUR",
            category=category,
            payment_method=r.get("payment_method", "unknown"),
            raw_json=json.dumps(r, ensure_ascii=False),
        ))
        log.info("  [%d/%d] receipt %s €%.2f at %s", i, len(receipts), r["date"], float(r["total"]), merchant)

    return len(receipts)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    _verify_sources()

    import db
    db.init_schema()

    log.info("Source: %s", _DATA_JSON)
    data = json.loads(_DATA_JSON.read_text(encoding="utf-8"))

    log.info("\n── Payslips ──────────────────────────────────────")
    ps_count = _migrate_payslips(data.get("payslips", []))

    log.info("\n── Bank statements → transactions ────────────────")
    tx_count = _migrate_bank_statements(data.get("bank_statements", []))

    log.info("\nSource: %s", _RECEIPTS_JSON)
    receipts_data = json.loads(_RECEIPTS_JSON.read_text(encoding="utf-8"))

    log.info("\n── Receipts ──────────────────────────────────────")
    rx_count = _migrate_receipts(receipts_data.get("receipts", []))

    log.info("\n✅ Migration complete")
    log.info("   Payslips:     %d", ps_count)
    log.info("   Transactions: %d", tx_count)
    log.info("   Receipts:     %d", rx_count)
    log.info("\nRe-running is safe — all inserts use INSERT OR IGNORE.")


if __name__ == "__main__":
    main()
