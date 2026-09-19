"""
Tests for querier.py — mocked Gemini and Turso db layer.
"""
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("TURSO_DATABASE_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_AUTH_TOKEN", "test-turso-token")

_genai_stub = types.ModuleType("google.generativeai")
_genai_stub.configure = lambda **kw: None
_genai_stub.GenerativeModel = MagicMock(return_value=MagicMock())
sys.modules.setdefault("google.generativeai", _genai_stub)
sys.modules.setdefault("google", types.ModuleType("google"))

import querier  # noqa: E402


def _gemini_text(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


_VALID_SQL = "SELECT SUM(amount) FROM transactions WHERE category = 'Groceries'"
_ROWS = [{"SUM(amount)": -120.5}]
_FRIENDLY_ANSWER = "You spent €120.50 on groceries."


class TestValidateSql(unittest.TestCase):

    def test_valid_select_passes(self):
        assert querier._validate_sql(_VALID_SQL) == _VALID_SQL

    def test_non_select_raises(self):
        with self.assertRaises(ValueError):
            querier._validate_sql("DROP TABLE receipts")

    def test_semicolon_injection_stripped(self):
        injected = f"{_VALID_SQL}; DROP TABLE receipts"
        result = querier._validate_sql(injected)
        assert "DROP" not in result
        assert result.startswith("SELECT")

    def test_case_insensitive_select(self):
        assert querier._validate_sql("select * from receipts") is not None


class TestHandleQuery(unittest.TestCase):

    def test_valid_query_round_trip(self):
        with patch("querier._model") as mock_model, \
             patch("querier.db.query", return_value=_ROWS) as mock_db:
            mock_model.generate_content.side_effect = [
                _gemini_text(_VALID_SQL),
                _gemini_text(_FRIENDLY_ANSWER),
            ]
            result = querier.handle_query("How much did I spend on groceries?")
        assert result == _FRIENDLY_ANSWER
        mock_db.assert_called_once_with(_VALID_SQL)

    def test_non_select_sql_rejected_before_db(self):
        with patch("querier._model") as mock_model, \
             patch("querier.db.query") as mock_db:
            mock_model.generate_content.side_effect = [
                _gemini_text("DROP TABLE receipts"),
                _gemini_text("irrelevant"),
            ]
            result = querier.handle_query("delete everything")
        mock_db.assert_not_called()
        assert "safe" in result.lower() or "query" in result.lower()

    def test_empty_result_passes_to_gemini_for_natural_answer(self):
        with patch("querier._model") as mock_model, \
             patch("querier.db.query", return_value=[]):
            mock_model.generate_content.side_effect = [
                _gemini_text(_VALID_SQL),
                _gemini_text("No data found."),
            ]
            querier.handle_query("anything")
        # Second call (answer step) receives the empty rows in its prompt
        answer_call_args = str(mock_model.generate_content.call_args_list[1])
        assert "[]" in answer_call_args or "Result: []" in answer_call_args

    def test_prose_instead_of_sql_returns_safe_message(self):
        with patch("querier._model") as mock_model, \
             patch("querier.db.query") as mock_db:
            mock_model.generate_content.side_effect = [
                _gemini_text("Sorry, I cannot generate SQL for that."),
                _gemini_text("irrelevant"),
            ]
            result = querier.handle_query("tell me a joke")
        mock_db.assert_not_called()
        assert isinstance(result, str) and len(result) > 0


if __name__ == "__main__":
    unittest.main()
