import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ===============================
# 🔧 RENDER STABILIZATION (PORT)
# ===============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ===============================
# 🔑 CONFIG
# ===============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "PASTE_YOUR_GOOGLE_SHEETS_CSV_LINK_HERE"

# Очікувані колонки в таблиці:
# name | knife | locker | location (або будь-які, які в тебе є)

# ===============================
# 📄 CSV LOADER
# ===============================

def load_csv():
    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()
    content = response.content.decode("utf-8")
    reader = csv.DictReader(StringIO(content))
    return list(reader)

# ===============================
# 🤖 COMMANDS
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт 👋\n"
        "Доступні команди:\n"
        "/find\n"
        "/knife\n"
        "/no_knife\n"
        "/with_locker\n"
        "/no_locker"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    if not data:
        await update.message.reply_text("❌ Дані відсутні")
        return

    text = "\n".join([row.get("name", "—") for row in data])
    await update.message.reply_text(text)

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    result = [r for r in data if r.get("knife", "").lower() == "yes"]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = "\n".join([r.get("name", "—") for r in result])
    await update.message.reply_text(text)

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    result = [r for r in data if r.get("knife", "").lower() == "no"]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = "\n".join([r.get("name", "—") for r in result])
    await update.message.reply_text(text)

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    result = [r for r in data if r.get("locker", "").lower() == "yes"]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = "\n".join([r.get("name", "—") for r in result])
    await update.message.reply_text(text)

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    result = [r for r in data if r.get("locker", "").lower() == "no"]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = "\n".join([r.get("name", "—") for r in result])
    await update.message.reply_text(text)

# ===============================
# 🚀 MAIN
# ===============================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    app.run_polling()

if __name__ == "__main__":
    main()
