import os
import csv
import threading
import time
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# 🔧 CONFIG
# ==================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

CACHE_REFRESH_SECONDS = 300  # 5 хв

# ==================================================
# 🌐 RENDER HEALTH CHECK
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
# 📦 CSV CACHE
# ==================================================

cached_rows = []
data_lock = threading.Lock()

def load_csv():
    global cached_rows
    try:
        resp = requests.get(CSV_URL, timeout=15)
        resp.raise_for_status()

        reader = csv.DictReader(StringIO(resp.text))
        rows = list(reader)

        with data_lock:
            cached_rows = rows

        print(f"CSV loaded: {len(rows)} rows")

    except Exception as e:
        print("CSV load error:", e)

def background_csv_refresher():
    while True:
        time.sleep(CACHE_REFRESH_SECONDS)
        load_csv()

# ==================================================
# 🧠 HELPERS
# ==================================================

def has_knife(value) -> bool:
    if value is None:
        return False

    v = str(value).strip().lower()

    if v == "":
        return False

    if v.isdigit():
        return int(v) > 0

    return v in {"yes", "y", "так", "true", "+", "є"}

def has_locker(value) -> bool:
    if value is None:
        return False

    v = str(value).strip().lower()

    if v == "" or v in {"-", "ні", "no", "0"}:
        return False

    if v.isdigit():
        return int(v) > 0

    return True

# ==================================================
# 🤖 COMMANDS
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
    with data_lock:
        rows = cached_rows

    total = len(rows)
    knife_yes = sum(1 for r in rows if has_knife(r.get("knife")))
    knife_no = total - knife_yes

    locker_yes = sum(1 for r in rows if has_locker(r.get("locker")))
    locker_no = total - locker_yes

    text = (
        "📊 Статистика:\n"
        f"Всього записів: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🔪 Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"🗄 Без шафки: {locker_no}"
    )

    await update.message.reply_text(text)

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with data_lock:
        rows = cached_rows

    with_knife = [r for r in rows if has_knife(r.get("knife"))]
    without_knife = [r for r in rows if not has_knife(r.get("knife"))]

    text = (
        "🔪 Ніж:\n"
        f"З ножем: {len(with_knife)}\n"
        f"Без ножа: {len(without_knife)}"
    )

    await update.message.reply_text(text)

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with data_lock:
        rows = cached_rows

    with_locker = [r for r in rows if has_locker(r.get("locker"))]
    without_locker = [r for r in rows if not has_locker(r.get("locker"))]

    text = (
        "🗄 Шафка:\n"
        f"З шафкою: {len(with_locker)}\n"
        f"Без шафки: {len(without_locker)}"
    )

    await update.message.reply_text(text)

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    # health server
    threading.Thread(target=run_health_server, daemon=True).start()

    # initial CSV load
    load_csv()

    # background refresh
    threading.Thread(target=background_csv_refresher, daemon=True).start()

    # bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("locker", locker))

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
