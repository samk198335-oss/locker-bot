import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ===============================
# Render keep-alive
# ===============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ===============================
# Helpers
# ===============================
YES_VALUES = {"1", "2", "yes", "y", "так", "є", "true", "+"}
NO_VALUES = {"0", "no", "n", "ні", "нет", "-", ""}

def norm(val: str) -> str:
    return val.strip().lower()

def load_data():
    resp = requests.get(CSV_URL, timeout=15)
    resp.encoding = "utf-8"
    reader = csv.DictReader(StringIO(resp.text))
    return list(reader)

# ===============================
# Commands
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команди:\n"
        "/stats\n"
        "/knife_list – прізвище + ніж\n"
        "/no_knife_list – без ножа\n"
        "/locker_list – прізвище + шафка\n"
        "/no_locker_list – без шафки"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()

    total = len(rows)
    knife_yes = knife_no = locker_yes = locker_no = 0

    for r in rows:
        knife = norm(r.get("knife", ""))
        locker = norm(r.get("locker", ""))

        if knife in YES_VALUES:
            knife_yes += 1
        elif knife in NO_VALUES:
            knife_no += 1

        if locker not in NO_VALUES:
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"❌ Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = []

    for r in rows:
        if norm(r.get("knife", "")) in YES_VALUES:
            result.append(r.get("surname", "").strip())

    await update.message.reply_text(
        "\n".join(result) if result else "Немає даних"
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = []

    for r in rows:
        if norm(r.get("knife", "")) in NO_VALUES:
            result.append(r.get("surname", "").strip())

    await update.message.reply_text(
        "\n".join(result) if result else "Немає даних"
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = []

    for r in rows:
        locker_raw = r.get("locker", "").strip()
        if norm(locker_raw) not in NO_VALUES:
            result.append(f"{r.get('surname','').strip()} — {locker_raw}")

    await update.message.reply_text(
        "\n".join(result) if result else "Немає даних"
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    result = []

    for r in rows:
        if norm(r.get("locker", "")) in NO_VALUES:
            result.append(r.get("surname", "").strip())

    await update.message.reply_text(
        "\n".join(result) if result else "Немає даних"
    )

# ===============================
# App
# ===============================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("knife_list", knife_list))
app.add_handler(CommandHandler("no_knife_list", no_knife_list))
app.add_handler(CommandHandler("locker_list", locker_list))
app.add_handler(CommandHandler("no_locker_list", no_locker_list))

app.run_polling()
