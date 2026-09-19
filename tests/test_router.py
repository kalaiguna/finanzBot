"""
Tests for router.py — mocked extractor and querier.
_ALLOWED_USER_ID is patched directly to avoid env-var collision with test_extractor.py.
"""
import os
import sys
import types
import unittest
from unittest.mock import patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TURSO_DATABASE_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_AUTH_TOKEN", "test-turso-token")
os.environ.setdefault("ALLOWED_TELEGRAM_USER_ID", "111222333")

for mod in ("google.generativeai", "google", "pdfplumber", "PIL", "PIL.Image"):
    sys.modules.setdefault(mod, types.ModuleType(mod))

import router  # noqa: E402

_ALLOWED = "111222333"
_UNKNOWN = "999888777"
_FILE_ID = "abc123"


def _msg(user_id: str, **extra) -> dict:
    return {"message": {"from": {"id": int(user_id)}, **extra}}


# All tests that exercise the allowed-user path patch router._ALLOWED_USER_ID
# directly — the module-level value may have been set from env before this file
# was imported if test_extractor.py ran first in the same process.
_patch_allowed = patch("router._ALLOWED_USER_ID", _ALLOWED)


@_patch_allowed
class TestRouterAllowedUser(unittest.TestCase):

    @patch("router.extractor.handle_receipt", return_value="✅ receipt")
    def test_photo_routes_to_receipt(self, mock_receipt, *_):
        update = _msg(_ALLOWED, photo=[{"file_id": _FILE_ID, "file_size": 100}])
        result = router.route(update)
        mock_receipt.assert_called_once_with(_FILE_ID)
        assert result == "✅ receipt"

    @patch("router.extractor.handle_bank_pdf", return_value="✅ bank")
    def test_pdf_with_konto_routes_to_bank(self, mock_bank, *_):
        update = _msg(_ALLOWED, document={
            "file_id": _FILE_ID, "mime_type": "application/pdf",
            "file_name": "kontoauszug_jan_2026.pdf",
        })
        result = router.route(update)
        mock_bank.assert_called_once_with(_FILE_ID)
        assert result == "✅ bank"

    @patch("router.extractor.handle_payslip_pdf", return_value="✅ payslip")
    def test_pdf_with_gehaltsabrechnung_routes_to_payslip(self, mock_payslip, *_):
        update = _msg(_ALLOWED, document={
            "file_id": _FILE_ID, "mime_type": "application/pdf",
            "file_name": "gehaltsabrechnung_jan_2026.pdf",
        })
        result = router.route(update)
        mock_payslip.assert_called_once_with(_FILE_ID)
        assert result == "✅ payslip"

    @patch("router.querier.handle_query", return_value="You spent €42.")
    def test_text_message_routes_to_querier(self, mock_query, *_):
        update = _msg(_ALLOWED, text="How much did I spend on food?")
        result = router.route(update)
        mock_query.assert_called_once_with("How much did I spend on food?")
        assert result == "You spent €42."


class TestRouterUnknownUser(unittest.TestCase):

    @patch("router.extractor.handle_receipt")
    def test_unknown_user_photo_silently_rejected(self, mock_receipt):
        with patch("router._ALLOWED_USER_ID", _ALLOWED):
            update = _msg(_UNKNOWN, photo=[{"file_id": _FILE_ID}])
            result = router.route(update)
        mock_receipt.assert_not_called()
        assert result is None

    @patch("router.querier.handle_query")
    def test_unknown_user_text_silently_rejected(self, mock_query):
        with patch("router._ALLOWED_USER_ID", _ALLOWED):
            update = _msg(_UNKNOWN, text="show me my balance")
            result = router.route(update)
        mock_query.assert_not_called()
        assert result is None


@_patch_allowed
class TestRouterEdgeCases(unittest.TestCase):

    @patch("router.extractor.handle_bank_pdf", return_value="✅ bank default")
    def test_unrecognised_pdf_name_defaults_to_bank(self, mock_bank, *_):
        update = _msg(_ALLOWED, document={
            "file_id": _FILE_ID, "mime_type": "application/pdf",
            "file_name": "document.pdf",
        })
        result = router.route(update)
        mock_bank.assert_called_once_with(_FILE_ID)

    @patch("router.extractor.handle_receipt", return_value="✅ image receipt")
    def test_image_document_routes_to_receipt(self, mock_receipt, *_):
        update = _msg(_ALLOWED, document={
            "file_id": _FILE_ID, "mime_type": "image/jpeg",
            "file_name": "receipt.jpg",
        })
        result = router.route(update)
        mock_receipt.assert_called_once_with(_FILE_ID)
        assert result == "✅ image receipt"


if __name__ == "__main__":
    unittest.main()
