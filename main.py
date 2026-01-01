import os
import csv
import io
import threading
import requests

from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== CONFIG ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8Gkmgqr1G5BkD40wtOMI/export?format=csv"

PORT = int(os.environ.get("PORT", 10000))
# ============================================


# ---------- FAKE HTTP SERVER (Render Free) ----------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")


def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    server.serve_forever()


# ---------- HELPERS ----------
def normalize(value: str) -> str:
    return value.strip().lower()


def is_yes(value: str) -> bool:
    return normalize(value) in ["yes", "true", "1", "так", "+"]


def is_no(value: str) -> bool:
    return normalize(value) in ["no", "false", "0", "ні", "-"]


# ---------- DATA ----------
def load_data():
    try:
        r = requests.get(CSV_URL, timeout=10)
        r.raise_for_status()
        csv_file = io.StringIO(r.text)
        reader = csv.DictReader(csv_file)
        return list(reader)
    except Exception as e:
        print("❌ CSV load error:", e)
        return []


def filter_data(data, knife=None, locker=None):
    results = []

    for row in data:
        if knife == "yes" and not is_yes(row.get("knife", "")):
            continue
        if knife == "no" and not is_no(row.get("knife", "")):
            continue

        if locker == "yes" and not is_yes(row.get("locker", "")):
            continue
        if locker == "no" and not is_no(row.get("locker", "")):
            continue

        results.append(row)

    return results


def format_results(rows):
    if not rows:
        return "❌ Нічого не знайдено"

    messages = []
    for r in rows:
        messages.append(
            f"📍 {r.get('name', '')}\n"
            f"ℹ️ {r.get('info', '')}"
        )

    return "\n\n".join(messages)


# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю!\n\n"
        "Доступні команди:\n"
        "/find — пошук\n"
        "/knife — з ножем\n"
        "/no_knife — без ножа\n"
        "/with_locker — з шафкою\n"
        "/no_locker — без шафки"
    )


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(format_results(data))


async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, knife="yes"))
    )


async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, knife="no"))
    )


async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, locker="yes"))
    )


async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, locker="no"))
    )


# ---------- MAIN ----------
def main():
    threading.Thread(target=run_http_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    print("✅ Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
