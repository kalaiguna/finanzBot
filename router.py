import logging
import os

import extractor
import querier

log = logging.getLogger(__name__)

_ALLOWED_USER_ID = os.environ["ALLOWED_TELEGRAM_USER_ID"]

_PAYSLIP_KEYWORDS = {"abrechnung", "gehalts", "lohn", "brutto", "netto", "bezuege"}
_BANK_KEYWORDS = {"konto", "auszug"}


def _largest_photo_id(photos: list) -> str:
    """Telegram sends photos as an array of sizes; the last is the largest."""
    return photos[-1]["file_id"]


def route(update: dict) -> str | None:
    msg = update.get("message", {})
    user_id = str(msg.get("from", {}).get("id", ""))

    if user_id != _ALLOWED_USER_ID:
        log.warning("Rejected message from unknown user_id=%s", user_id)
        return None

    if photos := msg.get("photo"):
        return extractor.handle_receipt(_largest_photo_id(photos))

    if doc := msg.get("document"):
        mime = doc.get("mime_type", "")
        file_id = doc["file_id"]
        name = doc.get("file_name", "").lower()

        if mime.startswith("image/"):
            return extractor.handle_receipt(file_id)

        if mime == "application/pdf":
            if any(k in name for k in _PAYSLIP_KEYWORDS):
                return extractor.handle_payslip_pdf(file_id)
            if any(k in name for k in _BANK_KEYWORDS):
                return extractor.handle_bank_pdf(file_id)
            # PDF with no recognisable keyword — bank statement is the safer default
            log.info("Unrecognised PDF name '%s' — routing as bank statement", name)
            return extractor.handle_bank_pdf(file_id)

    if text := msg.get("text"):
        return querier.handle_query(text)

    return "❓ Unrecognised message type. Send a receipt photo, a PDF, or a text question."
