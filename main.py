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

# ===============================
# 🔧 Render keep-alive
# ===============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()

# ===============================
# 📥 Load CSV (UTF-8 FIX)
# ===============================
def load_data():
    response = requests.get(CSV_URL, timeout=15)
    text = response.content.decode("utf-8", errors="replace")
    reader = csv.DictReader(StringIO(text))
    return list(reader)

# ===============================
# 🧠 Helpers
# ===============================
def has_knife(val: str) -> bool:
    return str(val).strip() in ("1", "2")

def no_knife(val: str) -> bool:
    return str(val).strip() == "0"

def has_locker(val: str) -> bool:
    v = str(val).strip()
    if v == "" or v == "-":
        return False
    return True

def no_locker(val: str) -> bool:
    v = str(val).strip()
    return v == "" or v == "-"

# ===============================
# 🤖 Commands
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Команди:\n"
        "/stats\n"
        "/knife_list – прізвище + ніж\n"
        "/no_knife_list – без ножа\n"
        "/locker_list – прізвище + шафка\n"
        "/no_locker_list – без шафки"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    total = len(data)
    knife_yes = sum(1 for r in data if has_knife(r.get("knife", "")))
    knife_no = sum(1 for r in data if no_knife(r.get("knife", "")))
    locker_yes = sum(1 for r in data if has_locker(r.get("locker", "")))
    locker_no = sum(1 for r in data if no_locker(r.get("locker", "")))

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
    rows = [
        f"• {r['surname']}"
        for r in data
        if has_knife(r.get("knife", "")) and r.get("surname", "").strip()
    ]
    await update.message.reply_text("\n".join(rows) if rows else "Немає даних")

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        f"• {r['surname']}"
        for r in data
        if no_knife(r.get("knife", "")) and r.get("surname", "").strip()
    ]
    await update.message.reply_text("\n".join(rows) if rows else "Немає даних")

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        f"• {r['surname']} — {r['locker']}"
        for r in data
        if has_locker(r.get("locker", "")) and r.get("surname", "").strip()
    ]
    await update.message.reply_text("\n".join(rows) if rows else "Немає даних")

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        f"• {r['surname']}"
        for r in data
        if no_locker(r.get("locker", "")) and r.get("surname", "").strip()
    ]
    await update.message.reply_text("\n".join(rows) if rows else "Немає даних")

# ===============================
# 🚀 Run
# ===============================
if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()
