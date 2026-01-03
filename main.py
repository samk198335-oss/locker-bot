import os
import csv
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
# 📥 CSV LOADER
# ==================================================

def load_csv():
    response = requests.get(CSV_URL, timeout=15)
    response.raise_for_status()

    content = response.content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(content))

    rows = list(reader)
    return rows, reader.fieldnames

def normalize(value: str):
    if value is None:
        return None
    v = value.strip().lower()
    if v in YES_VALUES:
        return "yes"
    if v in NO_VALUES:
        return "no"
    return None

# ==================================================
# 📊 COMMANDS
# ==================================================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows, _ = load_csv()
    await update.message.reply_text(f"📊 Всього записів: {len(rows)}")

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows, _ = load_csv()

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
    rows, _ = load_csv()

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

# ==================================================
# 🐞 DEBUG COMMAND
# ==================================================

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows, headers = load_csv()

    msg = []
    msg.append(f"DEBUG INFO")
    msg.append(f"Rows count: {len(rows)}")
    msg.append(f"Headers: {headers}")

    if rows:
        sample = rows[0]
        msg.append("First row:")
        for k, v in sample.items():
            msg.append(f"{k} = '{v}'")

    await update.message.reply_text("\n".join(msg))

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("locker", locker))
    app.add_handler(CommandHandler("debug", debug))

    app.run_polling()

if __name__ == "__main__":
    main()
