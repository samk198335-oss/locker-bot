import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# 🔧 RENDER FREE STABILIZATION (HTTP PORT)
# ==================================================

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

# ==================================================
# 🔑 CONFIG
# ==================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ==================================================
# 📄 SAFE CSV LOADER
# ==================================================

def load_csv():
    try:
        response = requests.get(CSV_URL, timeout=10)
        response.raise_for_status()
        content = response.content.decode("utf-8")
        reader = csv.DictReader(StringIO(content))
        data = list(reader)
        return data
    except Exception as e:
        print("CSV LOAD ERROR:", e)
        return None

# ==================================================
# 🤖 COMMANDS
# ==================================================

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
        await update.message.reply_text("❌ Помилка завантаження таблиці")
        return

    await update.message.reply_text(f"📋 Всього записів: {len(data)}")

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    if not data:
        await update.message.reply_text("❌ Помилка завантаження таблиці")
        return

    count = sum(1 for r in data if r.get("knife", "").strip().lower() == "yes")
    await update.message.reply_text(f"🔪 З ножем: {count}")

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    if not data:
        await update.message.reply_text("❌ Помилка завантаження таблиці")
        return

    count = sum(1 for r in data if r.get("knife", "").strip().lower() == "no")
    await update.message.reply_text(f"🚫 Без ножа: {count}")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    if not data:
        await update.message.reply_text("❌ Помилка завантаження таблиці")
        return

    count = sum(1 for r in data if r.get("locker", "").strip().lower() == "yes")
    await update.message.reply_text(f"🔐 З шафкою: {count}")

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    if not data:
        await update.message.reply_text("❌ Помилка завантаження таблиці")
        return

    count = sum(1 for r in data if r.get("locker", "").strip().lower() == "no")
    await update.message.reply_text(f"🚫 Без шафки: {count}")

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    print("BOT STARTED")
    app.run_polling()

if __name__ == "__main__":
    main()
