import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# =========================
# RENDER KEEP-ALIVE
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
# CSV LOADER (CACHE)
# =========================

_cached_rows = None

def load_csv():
    global _cached_rows
    if _cached_rows is not None:
        return _cached_rows

    response = requests.get(CSV_URL, timeout=10)
    response.raise_for_status()

    reader = csv.DictReader(StringIO(response.text))
    _cached_rows = list(reader)
    return _cached_rows

# =========================
# HELPERS
# =========================

def safe_int(value):
    try:
        return int(str(value).strip())
    except:
        return 0

# =========================
# COMMANDS
# =========================

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    with_knife = 0
    without_knife = 0

    for row in rows:
        count = safe_int(row.get("knife"))
        if count > 0:
            with_knife += count
        else:
            without_knife += 1

    await update.message.reply_text(
        "🔪 Ніж:\n"
        f"З ножем: {with_knife}\n"
        f"Без ножа: {without_knife}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for row in rows:
        surname = str(row.get("surname", "")).strip()
        count = safe_int(row.get("knife"))

        if surname and count > 0:
            result.append((surname, count))

    if not result:
        await update.message.reply_text("🔪 Немає даних по ножах.")
        return

    lines = ["🔪 Прізвища з ножами:"]
    for i, (surname, count) in enumerate(result, start=1):
        lines.append(f"{i}. {surname} — {count}")

    await update.message.reply_text("\n".join(lines))

# =========================
# APP START
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("knife_list", knife_list))

    app.run_polling()

if __name__ == "__main__":
    main()
