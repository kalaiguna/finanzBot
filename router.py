import logging
import os

import extractor
import querier

log = logging.getLogger(__name__)

_ALLOWED_USER_ID = os.environ["ALLOWED_TELEGRAM_USER_ID"].strip()

# Bank keywords checked first — they are more specific and won't appear in payslip names.
# Payslip keywords like "netto" are common substrings in German compound words (e.g.
# "nettobetrag"), so checking bank first avoids misrouting bank PDFs as payslips.
_BANK_KEYWORDS = {"konto", "auszug"}
_PAYSLIP_KEYWORDS = {"abrechnung", "gehalts", "lohn", "brutto", "netto", "bezuege"}


def _largest_photo_id(photos: list) -> str | None:
    """Return the file_id of the largest photo, or None if the list is empty."""
    return photos[-1]["file_id"] if photos else None


def route(update: dict) -> str | None:
    msg = update.get("message", {})
    user_id = str(msg.get("from", {}).get("id", ""))

    if user_id != _ALLOWED_USER_ID:
        log.warning("Rejected message from unknown user_id=%s", user_id)
        return None

    if photos := msg.get("photo"):
        file_id = _largest_photo_id(photos)
        if file_id:
            return extractor.handle_receipt(file_id)

    if doc := msg.get("document"):
        mime = doc.get("mime_type", "")
        file_id = doc["file_id"]
        name = doc.get("file_name", "").lower()

        if mime.startswith("image/"):
            return extractor.handle_receipt(file_id)

        if mime == "application/pdf":
            if any(k in name for k in _BANK_KEYWORDS):
                return extractor.handle_bank_pdf(file_id)
            if any(k in name for k in _PAYSLIP_KEYWORDS):
                return extractor.handle_payslip_pdf(file_id)
            # PDF with no recognisable keyword — bank statement is the safer default
            log.info("Unrecognised PDF name '%s' — routing as bank statement", name)
            return extractor.handle_bank_pdf(file_id)

    if text := msg.get("text"):
        return querier.handle_query(text)

    return "❓ Unrecognised message type. Send a receipt photo, a PDF, or a text question."
