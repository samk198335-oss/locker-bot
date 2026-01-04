import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ==================================================
# RENDER KEEP-ALIVE
# ==================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), HealthHandler)
    server.serve_forever()

# ==================================================
# CSV
# ==================================================
def load_data():
    response = requests.get(CSV_URL, timeout=15)
    response.encoding = "utf-8"
    csv_file = StringIO(response.text)
    reader = csv.DictReader(csv_file)
    return list(reader)

def norm(val: str) -> str:
    return (val or "").strip().lower()

# ==================================================
# LOGIC
# ==================================================
def has_knife(row):
    return norm(row.get("knife")) in {"1", "2", "yes", "так", "є", "true"}

def no_knife(row):
    return norm(row.get("knife")) in {"0", "", "no", "ні", "false"}

def has_locker(row):
    val = norm(row.get("locker"))
    return val not in {"", "-", "ні", "no", "false"}

def no_locker(row):
    val = norm(row.get("locker"))
    return val in {"", "-", "ні", "no", "false"}

# ==================================================
# COMMANDS
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Команди:\n"
        "/stats\n"
        "/knife_list – прізвище + ніж\n"
        "/no_knife_list – прізвище без ножа\n"
        "/locker_list – прізвище + шафка\n"
        "/no_locker_list – без шафки"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    total = len(data)
    knife_yes = sum(1 for r in data if has_knife(r))
    knife_no = sum(1 for r in data if no_knife(r))
    locker_yes = sum(1 for r in data if has_locker(r))
    locker_no = sum(1 for r in data if no_locker(r))

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"❌ Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [f"• {r['surname']}" for r in data if has_knife(r)]

    await update.message.reply_text(
        "🔪 Прізвища з ножами:\n" + "\n".join(rows)
        if rows else "🔪 Прізвища з ножами:\nНемає даних"
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [f"• {r['surname']}" for r in data if no_knife(r)]

    await update.message.reply_text(
        "❌ Без ножів:\n" + "\n".join(rows)
        if rows else "❌ Без ножів:\nНемає даних"
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        f"• {r['surname']} — {r['locker']}"
        for r in data if has_locker(r)
    ]

    await update.message.reply_text(
        "🗄 Прізвище + шафка:\n" + "\n".join(rows)
        if rows else "🗄 Прізвище + шафка:\nНемає даних"
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [f"• {r['surname']}" for r in data if no_locker(r)]

    await update.message.reply_text(
        "❌ Без шафки:\n" + "\n".join(rows)
        if rows else "❌ Без шафки:\nНемає даних"
    )

# ==================================================
# MAIN
# ==================================================
def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()

if __name__ == "__main__":
    main()
