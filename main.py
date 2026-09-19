import logging
import os

import requests
from flask import Flask, jsonify, request

import db
import router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)

_BOT_URL = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"


def _send(chat_id: int, text: str) -> None:
    requests.post(
        f"{_BOT_URL}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    try:
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        reply = router.route(update)
        if reply and chat_id:
            _send(chat_id, reply)
    except Exception as e:
        log.error("Unhandled webhook error: %s", e, exc_info=True)
    # Always return 200 — Telegram retries on non-2xx, causing duplicate processing
    return jsonify({"ok": True})


@app.route("/dashboard")
def dashboard():
    path = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    db.init_schema()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
