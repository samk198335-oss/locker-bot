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
# CSV LOADER (with cache)
# =========================

_cached_rows = None

def load_csv():
    global _cached_rows
    if _cached_rows is not None:
        return _cached_rows

    response = requests.get(CSV_URL, timeout=10)
    response.raise_for_status()

    csv_data = StringIO(response.text)
    reader = csv.DictReader(csv_data)

    rows = []
    for row in reader:
        rows.append(row)

    _cached_rows = rows
    return rows

# =========================
# COMMANDS
# =========================

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    with_knife = 0
    without_knife = 0

    for row in rows:
        value = str(row.get("knife", "")).strip()
        if value.isdigit() and int(value) > 0:
            with_knife += int(value)
        else:
            without_knife += 1

    text = (
        "🔪 Ніж:\n"
        f"З ножем: {with_knife}\n"
        f"Без ножа: {without_knife}"
    )

    await update.message.reply_text(text)

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    knife_by_surname = {}

    for row in rows:
        surname = str(row.get("surname", "")).strip()
        knife_value = str(row.get("knife", "")).strip()

        if not surname:
            continue

        if knife_value.isdigit():
            count = int(knife_value)
            if count > 0:
                knife_by_surname[surname] = knife_by_surname.get(surname, 0) + count

    if not knife_by_surname:
        await update.message.reply_text("🔪 Немає даних по ножах.")
        return

    lines = ["🔪 Прізвища з ножами:"]
    for i, (surname, count) in enumerate(sorted(knife_by_surname.items()), start=1):
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
