import os
import csv
import time
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# CONFIG
# ==================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

YES_VALUES = {"yes", "+", "так", "y", "true", "1"}
NO_VALUES = {"no", "-", "ні", "n", "false", "0"}

CACHE_REFRESH_SECONDS = 180

# ==================================================
# CACHE
# ==================================================

cache_lock = threading.Lock()
cached_rows = []
last_update = None

# ==================================================
# HEALTH CHECK
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ==================================================
# CSV + CACHE
# ==================================================

def normalize(value):
    if not value:
        return None
    v = value.strip().lower()
    if v in YES_VALUES:
        return "yes"
    if v in NO_VALUES:
        return "no"
    return None

def load_csv_once():
    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()
    content = response.content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(content))
    return list(reader)

def refresh_cache_loop():
    global cached_rows, last_update

    while True:
        try:
            rows = load_csv_once()
            with cache_lock:
                cached_rows = rows
                last_update = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[CACHE] refreshed: {len(rows)} rows")
        except Exception as e:
            print("[CACHE ERROR]", e)

        time.sleep(CACHE_REFRESH_SECONDS)

def get_rows():
    with cache_lock:
        return list(cached_rows)

# ==================================================
# COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! 👋\n\n"
        "Доступні команди:\n"
        "/stats — загальна статистика\n"
        "/knife — хто з ножем\n"
        "/locker — хто з шафкою"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_rows()
    await update.message.reply_text(f"📊 Всього записів: {len(rows)}")

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yes = no = 0
    for r in get_rows():
        val = normalize(r.get("Ніж"))
        if val == "yes":
            yes += 1
        elif val == "no":
            no += 1

    await update.message.reply_text(
        f"🔪 Ніж:\nЗ ножем: {yes}\nБез ножа: {no}"
    )

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yes = no = 0
    for r in get_rows():
        val = normalize(r.get("Шафка"))
        if val == "yes":
            yes += 1
        elif val == "no":
            no += 1

    await update.message.reply_text(
        f"🗄 Шафка:\nЗ шафкою: {yes}\nБез шафки: {no}"
    )

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"DEBUG\nRows: {len(get_rows())}\nLast update: {last_update}"
    )

# ==================================================
# MAIN
# ==================================================

def main():
    # health
    threading.Thread(target=run_health_server, daemon=True).start()

    # initial load (ВАЖЛИВО)
    initial_rows = load_csv_once()
    with cache_lock:
        global cached_rows, last_update
        cached_rows = initial_rows
        last_update = time.strftime("%Y-%m-%d %H:%M:%S")

    # background refresh
    threading.Thread(target=refresh_cache_loop, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("locker", locker))
    app.add_handler(CommandHandler("debug", debug))

    app.run_polling()

if __name__ == "__main__":
    main()
