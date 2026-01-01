import os
import csv
import io
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= CONFIG =================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

PORT = int(os.environ.get("PORT", 10000))

# =========================================

# ---------- FAKE HTTP SERVER (Render Free) ----------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_http_server():
    server = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    server.serve_forever()

# ---------- CSV HELPERS ----------
def load_data():
    try:
        r = requests.get(SHEET_URL, timeout=15)
        r.raise_for_status()
        f = io.StringIO(r.text)
        return list(csv.DictReader(f))
    except Exception as e:
        print("CSV LOAD ERROR:", e)
        return []

def has_knife(value: str) -> bool:
    if not value:
        return False
    return value.strip() != "0"

def has_locker(value: str) -> bool:
    if not value:
        return False
    v = value.strip().lower()
    return v not in ["0", "-", "ні", "нет"]

# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт 👋\n\n"
        "Доступні команди:\n"
        "/знайти Прізвище\n"
        "/ніж\n"
        "/безножа\n"
        "/зшафкою\n"
        "/безшафки"
    )

async def find_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажи прізвище після команди.")
        return

    query = " ".join(context.args).lower()
    rows = load_data()

    results = [r for r in rows if query in r.get("surname", "").lower()]

    if not results:
        await update.message.reply_text("Нічого не знайдено.")
        return

    msg = ""
    for r in results:
        msg += (
            f"📍 {r.get('Adress','')}\n"
            f"👤 {r.get('surname','')}\n"
            f"🔪 Ніж: {'є' if has_knife(r.get('knife','')) else 'немає'}\n"
            f"🧥 Шафка: {'є' if has_locker(r.get('locker','')) else 'немає'}\n\n"
        )

    await update.message.reply_text(msg)

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    count = len([r for r in rows if has_knife(r.get("knife",""))])
    await update.message.reply_text(f"🔪 З ножем: {count}")

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    count = len([r for r in rows if not has_knife(r.get("knife",""))])
    await update.message.reply_text(f"🚫 Без ножа: {count}")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    count = len([r for r in rows if has_locker(r.get("locker",""))])
    await update.message.reply_text(f"🧥 З шафкою: {count}")

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    count = len([r for r in rows if not has_locker(r.get("locker",""))])
    await update.message.reply_text(f"🚫 Без шафки: {count}")

# ---------- MAIN ----------
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("знайти", find_person))
    application.add_handler(CommandHandler("ніж", knife))
    application.add_handler(CommandHandler("безножа", no_knife))
    application.add_handler(CommandHandler("зшафкою", with_locker))
    application.add_handler(CommandHandler("безшафки", no_locker))

    application.run_polling()

if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()
    main()
