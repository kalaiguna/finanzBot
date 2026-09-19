import logging
import os
import re

import google.generativeai as genai

import db
from prompts import NL_TO_ANSWER_PROMPT, NL_TO_SQL_PROMPT

log = logging.getLogger(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
_model = genai.GenerativeModel("gemini-2.0-flash")

_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


def _validate_sql(raw: str) -> str:
    """Extract the first statement and confirm it is a SELECT. Raises ValueError otherwise."""
    first = raw.split(";")[0].strip()
    if not _SELECT_RE.match(first):
        raise ValueError(f"rejected non-SELECT SQL: {first[:120]}")
    return first


def handle_query(question: str) -> str:
    # Step 1 — NL → SQL
    sql_resp = _model.generate_content([NL_TO_SQL_PROMPT, question])
    raw_sql = sql_resp.text.strip()
    log.debug("Gemini SQL: %s", raw_sql)

    try:
        sql = _validate_sql(raw_sql)
    except ValueError as e:
        log.warning("SQL validation: %s", e)
        return "❓ I couldn't turn that into a safe database query. Try rephrasing."

    # Step 2 — Execute against Turso
    try:
        rows = db.query(sql)
    except Exception as e:
        log.error("Turso query error: %s | sql=%s", e, sql)
        return "❌ The database query failed. Please try again."

    # Step 3 — Rows → natural language answer
    answer_resp = _model.generate_content([
        NL_TO_ANSWER_PROMPT,
        f"Question: {question}\nResult: {rows}",
    ])
    return answer_resp.text.strip()
