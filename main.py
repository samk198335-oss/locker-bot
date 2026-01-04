import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# =========================
# Render keep-alive
# =========================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# =========================
# CSV LOAD (UTF-8 SAFE)
# =========================
def load_data():
    r = requests.get(CSV_URL)
    text = r.content.decode("utf-8")
    reader = csv.DictReader(StringIO(text))
    return list(reader)

# =========================
# NORMALIZATION
# =========================
def has_knife(val: str) -> bool:
    return val.strip() in ("1", "2")

def has_locker(val: str) -> bool:
    v = val.strip()
    if not v or v == "-":
        return False
    return True

# =========================
# COMMANDS
# =========================
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
    knife_yes = sum(has_knife(r.get("knife", "")) for r in data)
    knife_no = total - knife_yes
    locker_yes = sum(has_locker(r.get("locker", "")) for r in data)
    locker_no = total - locker_yes

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"❌ Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = [
        f"{r['surname']} — ніж"
        for r in rows
        if has_knife(r.get("knife", ""))
    ]
    await update.message.reply_text(
        "🔪 Прізвища з ножами:\n" + "\n".join(result)
        if result else "🔪 Прізвища з ножами:\nНемає даних"
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = [
        r["surname"]
        for r in rows
        if not has_knife(r.get("knife", ""))
    ]
    await update.message.reply_text(
        "❌ Без ножів:\n" + "\n".join(result)
        if result else "❌ Без ножів:\nНемає даних"
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = [
        f"{r['surname']} — шафка {r['locker']}"
        for r in rows
        if has_locker(r.get("locker", ""))
    ]
    await update.message.reply_text(
        "🗄 Прізвище + шафка:\n" + "\n".join(result)
        if result else "🗄 Прізвище + шафка:\nНемає даних"
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = [
        r["surname"]
        for r in rows
        if not has_locker(r.get("locker", ""))
    ]
    await update.message.reply_text(
        "❌ Без шафки:\n" + "\n".join(result)
        if result else "❌ Без шафки:\nНемає даних"
    )

# =========================
# BOT INIT
# =========================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("knife_list", knife_list))
app.add_handler(CommandHandler("no_knife_list", no_knife_list))
app.add_handler(CommandHandler("locker_list", locker_list))
app.add_handler(CommandHandler("no_locker_list", no_locker_list))

app.run_polling()
