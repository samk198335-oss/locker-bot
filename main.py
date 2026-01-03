import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# 🔧 CONFIG
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

CACHE_SECONDS = 300  # 5 хв

# ==================================================
# 🔧 RENDER FREE STABILIZATION (HTTP SERVER)
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_http_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ==================================================
# 📦 CSV CACHE
# ==================================================

_csv_cache = {
    "data": None,
    "time": 0
}

def load_csv():
    import time
    now = time.time()

    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_SECONDS:
        return _csv_cache["data"]

    r = requests.get(CSV_URL, timeout=15)

    # 🔑 КЛЮЧОВЕ МІСЦЕ: utf-8-sig (виправляє кирилицю)
    text = r.content.decode("utf-8-sig")

    f = StringIO(text)
    reader = csv.DictReader(f)

    rows = []
    for row in reader:
        clean_row = {}
        for k, v in row.items():
            if k is None:
                continue
            key = k.strip()
            val = v.strip() if isinstance(v, str) else ""
            clean_row[key] = val
        rows.append(clean_row)

    _csv_cache["data"] = rows
    _csv_cache["time"] = now
    return rows

# ==================================================
# 🔪 HELPERS
# ==================================================

def is_yes(value: str) -> bool:
    if not value:
        return False
    v = value.strip().lower()
    return v in ["1", "yes", "y", "так", "+", "true"]

def parse_int(value: str) -> int:
    try:
        return int(value)
    except:
        return 0

# ==================================================
# 🤖 COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Alexpuls_bot працює\n\n"
        "/knife_list — прізвища з ножами\n"
        "/stats — загальна статистика"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    result = []
    for row in rows:
        surname = row.get("surname", "")
        knife_raw = row.get("knife", "")

        knives = parse_int(knife_raw)
        if knives <= 0 and is_yes(knife_raw):
            knives = 1

        if knives > 0 and surname:
            result.append((surname, knives))

    if not result:
        await update.message.reply_text("❌ Немає записів з ножами")
        return

    text = "🔪 Прізвища з ножами:\n"
    for i, (name, count) in enumerate(result, start=1):
        text += f"{i}. {name} — {count}\n"

    await update.message.reply_text(text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    total = len(rows)
    knife_yes = 0
    knife_no = 0

    for row in rows:
        knife_raw = row.get("knife", "")
        knives = parse_int(knife_raw)
        if knives <= 0 and is_yes(knife_raw):
            knives = 1

        if knives > 0:
            knife_yes += 1
        else:
            knife_no += 1

    await update.message.reply_text(
        f"📊 Статистика:\n"
        f"Всього записів: {total}\n"
        f"З ножем: {knife_yes}\n"
        f"Без ножа: {knife_no}"
    )

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("stats", stats))

    print("🤖 Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
