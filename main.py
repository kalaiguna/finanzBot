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

# Init schema at module load so it runs under gunicorn as well as direct execution
db.init_schema()


def _send(chat_id: int, text: str) -> None:
    try:
        resp = requests.post(
            f"{_BOT_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        log.error("Failed to send Telegram message to chat_id=%s: %s", chat_id, e)


@app.route("/webhook", methods=["POST"])
def webhook():
    # Entire handler wrapped — always return 200 so Telegram never retries
    try:
        update = request.json
        msg = update.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        reply = router.route(update)
        if reply and chat_id:
            _send(chat_id, reply)
    except Exception as e:
        log.error("Unhandled webhook error: %s", e, exc_info=True)
        try:
            chat_id = request.json.get("message", {}).get("chat", {}).get("id")
            if chat_id:
                _send(chat_id, "❌ Something went wrong. Please try again.")
        except Exception:
            pass
    return jsonify({"ok": True})


@app.route("/dashboard")
def dashboard():
    path = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Dashboard not available.", 404


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
