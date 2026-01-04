import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===============================
# CONFIG
# ===============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI"
    "/export?format=csv"
)

# ===============================
# RENDER HEALTHCHECK
# ===============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ===============================
# CSV LOADING (CORRECT UTF-8)
# ===============================

def load_csv():
    r = requests.get(CSV_URL, timeout=15)
    r.raise_for_status()

    text = r.content.decode("utf-8")
    reader = csv.DictReader(StringIO(text))

    return list(reader)

# ===============================
# NORMALIZATION
# ===============================

def normalize_knife(value):
    if value is None:
        return None
    v = str(value).strip()
    if v in {"1", "2"}:
        return 1
    if v == "0":
        return 0
    return None

def normalize_locker(value):
    if value is None:
        return None
    v = str(value).strip()
    if v in {"", "-", "0"}:
        return None
    return v

# ===============================
# COMMANDS
# ===============================

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
    rows = load_csv()

    total = len(rows)
    knife_yes = sum(1 for r in rows if normalize_knife(r["knife"]) == 1)
    knife_no = sum(1 for r in rows if normalize_knife(r["knife"]) == 0)
    locker_yes = sum(1 for r in rows if normalize_locker(r["locker"]))
    locker_no = total - locker_yes

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"❌ Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        f"{r['surname']} — є ніж"
        for r in rows
        if normalize_knife(r["knife"]) == 1 and r["surname"]
    ]

    await update.message.reply_text(
        "🔪 Прізвища з ножами:\n" + "\n".join(data)
        if data else "🔪 Прізвища з ножами:\nНемає даних"
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        r["surname"]
        for r in rows
        if normalize_knife(r["knife"]) == 0 and r["surname"]
    ]

    await update.message.reply_text(
        "❌ Без ножів:\n" + "\n".join(data)
        if data else "❌ Без ножів:\nНемає даних"
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        f"{r['surname']} — шафка {normalize_locker(r['locker'])}"
        for r in rows
        if normalize_locker(r["locker"]) and r["surname"]
    ]

    await update.message.reply_text(
        "🗄 Прізвище + шафка:\n" + "\n".join(data)
        if data else "🗄 Прізвище + шафка:\nНемає даних"
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        r["surname"]
        for r in rows
        if not normalize_locker(r["locker"]) and r["surname"]
    ]

    await update.message.reply_text(
        "❌ Без шафки:\n" + "\n".join(data)
        if data else "❌ Без шафки:\nНемає даних"
    )

# ===============================
# MAIN
# ===============================

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
