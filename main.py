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
# 🔐 CONFIG
# ==================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

YES_VALUES = {"yes", "+", "так", "y", "true", "1"}
NO_VALUES = {"no", "-", "ні", "n", "false", "0"}

CACHE_REFRESH_SECONDS = 180  # 3 хвилини

# ==================================================
# 🧠 CACHE STORAGE
# ==================================================

cache_lock = threading.Lock()
cached_rows = []
cached_headers = []
last_update = None

# ==================================================
# 🩺 RENDER HEALTH CHECK
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ==================================================
# 📥 CSV LOADER (WITH CACHE)
# ==================================================

def normalize(value: str):
    if value is None:
        return None
    v = value.strip().lower()
    if v in YES_VALUES:
        return "yes"
    if v in NO_VALUES:
        return "no"
    return None

def refresh_cache():
    global cached_rows, cached_headers, last_update

    while True:
        try:
            response = requests.get(CSV_URL, timeout=20)
            response.raise_for_status()

            content = response.content.decode("utf-8-sig")
            reader = csv.DictReader(StringIO(content))
            rows = list(reader)

            with cache_lock:
                cached_rows = rows
                cached_headers = reader.fieldnames
                last_update = time.strftime("%Y-%m-%d %H:%M:%S")

            print(f"[CACHE] Updated: {len(rows)} rows")

        except Exception as e:
            print(f"[CACHE ERROR] {e}")

        time.sleep(CACHE_REFRESH_SECONDS)

def get_cached_rows():
    with cache_lock:
        return list(cached_rows)

# ==================================================
# 📊 COMMANDS
# ==================================================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_cached_rows()
    await update.message.reply_text(f"📊 Всього записів: {len(rows)}")

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_cached_rows()

    yes = 0
    no = 0

    for r in rows:
        val = normalize(r.get("Ніж"))
        if val == "yes":
            yes += 1
        elif val == "no":
            no += 1

    await update.message.reply_text(
        f"🔪 Ніж:\n"
        f"З ножем: {yes}\n"
        f"Без ножа: {no}"
    )

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_cached_rows()

    yes = 0
    no = 0

    for r in rows:
        val = normalize(r.get("Шафка"))
        if val == "yes":
            yes += 1
        elif val == "no":
            no += 1

    await update.message.reply_text(
        f"🗄 Шафка:\n"
        f"З шафкою: {yes}\n"
        f"Без шафки: {no}"
    )

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_cached_rows()
    msg = [
        "DEBUG CACHE",
        f"Rows: {len(rows)}",
        f"Last update: {last_update}"
    ]
    await update.message.reply_text("\n".join(msg))

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=refresh_cache, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("locker", locker))
    app.add_handler(CommandHandler("debug", debug))

    app.run_polling()

if __name__ == "__main__":
    main()
