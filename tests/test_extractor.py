"""
Tests for extractor.py — mocked Gemini, Telegram file API, db, and parsers.
All cases assert nothing is written to disk (io.BytesIO usage).
"""
import io
import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TURSO_DATABASE_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_AUTH_TOKEN", "test-turso-token")
os.environ.setdefault("ALLOWED_TELEGRAM_USER_ID", "123456")

# Stub google.generativeai before extractor imports it.
# GenerativeModel must return an unspecced MagicMock so we can patch .generate_content.
_model_instance = MagicMock()
_genai_stub = types.ModuleType("google.generativeai")
_genai_stub.configure = lambda **kw: None
_genai_stub.GenerativeModel = MagicMock(return_value=_model_instance)
sys.modules.setdefault("google.generativeai", _genai_stub)
sys.modules.setdefault("google", types.ModuleType("google"))

import extractor  # noqa: E402


def _make_gemini_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.text = f"```json\n{json.dumps(payload)}\n```"
    return resp


_RECEIPT_PAYLOAD = {
    "date": "2026-01-15",
    "merchant": "REWE",
    "total": 42.50,
    "currency": "EUR",
    "category": "Groceries",
    "payment_method": "card",
}

_BANK_PAYLOAD = {
    "period": {"label": "01/2026", "month": 1, "year": 2026},
    "transactions": [
        {
            "date": "2026-01-10",
            "description": "REWE Zahlung",
            "merchant": "REWE",
            "amount": -35.20,
            "type": "expense",
            "category": "Groceries",
        },
        {
            "date": "2026-01-12",
            "description": "Gehalt",
            "merchant": "",
            "amount": 3000.00,
            "type": "income",
            "category": "Income",
        },
    ],
}

_PAYSLIP_PAYLOAD = {
    "period": {"label": "January 2026", "year": 2026, "month": 1},
    "gross": {"total": 5000.0},
    "net_income": {"net_pay": 3200.0, "payout": 3200.0},
    "deductions": {
        "tax": {"income_tax": 900.0},
        "social_security": {"total": 900.0},
    },
    "employee": {"employer": "Acme GmbH"},
    "cumulative_ytd": {"gross_ytd": 5000.0, "tax_ytd": 900.0},
}

_FAKE_FILE_ID = "file123"
_FAKE_PDF = b"%PDF-1.4 fake content"
_FAKE_IMAGE = b"\xff\xd8\xff fake jpeg"


# ── Receipt ───────────────────────────────────────────────────────────────────

class TestHandleReceipt(unittest.TestCase):

    def test_receipt_happy_path(self):
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_IMAGE), \
             patch("extractor.db.insert_receipt") as mock_insert, \
             patch("extractor.Image.open"):
            mock_model.generate_content.return_value = _make_gemini_response(_RECEIPT_PAYLOAD)
            result = extractor.handle_receipt(_FAKE_FILE_ID)
        assert "REWE" in result
        assert "42.50" in result
        mock_insert.assert_called_once()

    def test_receipt_uses_in_memory_image(self):
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_IMAGE), \
             patch("extractor.db.insert_receipt"), \
             patch("extractor.Image.open") as mock_open:
            mock_model.generate_content.return_value = _make_gemini_response(_RECEIPT_PAYLOAD)
            extractor.handle_receipt(_FAKE_FILE_ID)
        args, _ = mock_open.call_args
        assert isinstance(args[0], io.BytesIO), "Image.open must receive BytesIO, not a file path"

    def test_receipt_total_rounded_to_2dp(self):
        payload = {**_RECEIPT_PAYLOAD, "total": 99.999}
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_IMAGE), \
             patch("extractor.db.insert_receipt") as mock_insert, \
             patch("extractor.Image.open"):
            mock_model.generate_content.return_value = _make_gemini_response(payload)
            extractor.handle_receipt(_FAKE_FILE_ID)
        receipt = mock_insert.call_args[0][0]
        assert receipt.total == 100.0

    def test_receipt_missing_merchant_defaults_unknown(self):
        payload = {k: v for k, v in _RECEIPT_PAYLOAD.items() if k != "merchant"}
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_IMAGE), \
             patch("extractor.db.insert_receipt") as mock_insert, \
             patch("extractor.Image.open"):
            mock_model.generate_content.return_value = _make_gemini_response(payload)
            extractor.handle_receipt(_FAKE_FILE_ID)
        receipt = mock_insert.call_args[0][0]
        assert receipt.merchant == "Unknown"


# ── Bank PDF ──────────────────────────────────────────────────────────────────

class TestHandleBankPdf(unittest.TestCase):

    def test_bank_gemini_fallback_when_det_returns_none(self):
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_PDF), \
             patch("extractor._try_det_bank", return_value=None), \
             patch("extractor.db.insert_transactions"), \
             patch("extractor._pdf_text", return_value="pdf text"):
            mock_model.generate_content.return_value = _make_gemini_response(_BANK_PAYLOAD)
            result = extractor.handle_bank_pdf(_FAKE_FILE_ID)
        mock_model.generate_content.assert_called_once()
        assert "01/2026" in result
        assert "2 transactions" in result

    def test_bank_skips_gemini_when_det_confident(self):
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_PDF), \
             patch("extractor._try_det_bank", return_value={**_BANK_PAYLOAD, "_confidence": 95}), \
             patch("extractor.db.insert_transactions"):
            extractor.handle_bank_pdf(_FAKE_FILE_ID)
        mock_model.generate_content.assert_not_called()

    def test_bank_expense_total_excludes_income(self):
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_PDF), \
             patch("extractor._try_det_bank", return_value=None), \
             patch("extractor.db.insert_transactions"), \
             patch("extractor._pdf_text", return_value="pdf text"):
            mock_model.generate_content.return_value = _make_gemini_response(_BANK_PAYLOAD)
            result = extractor.handle_bank_pdf(_FAKE_FILE_ID)
        # Only the -35.20 transaction counts; income of 3000.00 excluded
        assert "35.20" in result

    def test_bank_empty_transactions(self):
        payload = {**_BANK_PAYLOAD, "transactions": []}
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_PDF), \
             patch("extractor._try_det_bank", return_value=None), \
             patch("extractor.db.insert_transactions") as mock_insert, \
             patch("extractor._pdf_text", return_value="pdf text"):
            mock_model.generate_content.return_value = _make_gemini_response(payload)
            result = extractor.handle_bank_pdf(_FAKE_FILE_ID)
        assert "0 transactions" in result
        mock_insert.assert_called_once_with([])


# ── Payslip PDF ───────────────────────────────────────────────────────────────

class TestHandlePayslipPdf(unittest.TestCase):

    def test_payslip_gemini_fallback_when_det_returns_none(self):
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_PDF), \
             patch("extractor._try_det_payslip", return_value=None), \
             patch("extractor.db.insert_payslip"), \
             patch("extractor._pdf_text", return_value="pdf text"):
            mock_model.generate_content.return_value = _make_gemini_response(_PAYSLIP_PAYLOAD)
            result = extractor.handle_payslip_pdf(_FAKE_FILE_ID)
        mock_model.generate_content.assert_called_once()
        assert "5000.00" in result
        assert "3200.00" in result

    def test_payslip_skips_gemini_when_det_confident(self):
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_PDF), \
             patch("extractor._try_det_payslip",
                   return_value={**_PAYSLIP_PAYLOAD, "_confidence": 90}), \
             patch("extractor.db.insert_payslip"):
            extractor.handle_payslip_pdf(_FAKE_FILE_ID)
        mock_model.generate_content.assert_not_called()

    def test_payslip_none_fields_render_as_question_mark(self):
        payload = {**_PAYSLIP_PAYLOAD, "gross": {}}
        with patch("extractor._model") as mock_model, \
             patch("extractor._download", return_value=_FAKE_PDF), \
             patch("extractor._try_det_payslip", return_value=None), \
             patch("extractor.db.insert_payslip"), \
             patch("extractor._pdf_text", return_value="pdf text"):
            mock_model.generate_content.return_value = _make_gemini_response(payload)
            result = extractor.handle_payslip_pdf(_FAKE_FILE_ID)
        assert "€?" in result


if __name__ == "__main__":
    unittest.main()
