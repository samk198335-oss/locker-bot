import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

# ==============================
# CONFIG
# ==============================
TOKEN = os.environ.get("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ==============================
# RENDER KEEP-ALIVE
# ==============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ==============================
# CSV PARSER
# ==============================
def load_data():
    response = requests.get(CSV_URL, timeout=15)
    response.encoding = "utf-8"

    reader = csv.DictReader(StringIO(response.text))
    data = []

    for row in reader:
        surname = (row.get("surname") or "").strip()
        knife_raw = (row.get("knife") or "").strip()
        locker_raw = (row.get("locker") or "").strip()

        if not surname:
            continue

        # ----- KNIFE -----
        knife = None
        if knife_raw.isdigit():
            knife = int(knife_raw)

        # ----- LOCKER -----
        locker = None
        locker_low = locker_raw.lower()

        if locker_raw.isdigit():
            locker = int(locker_raw)
        elif locker_low in ["tak", "yes", "є", "есть", "ключ є", "ключ"]:
            locker = 1
        elif locker_low in ["0", "-", "ні", "no"]:
            locker = 0

        data.append({
            "surname": surname,
            "knife": knife,
            "locker": locker
        })

    return data

# ==============================
# COMMANDS
# ==============================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    knife_yes = sum(1 for x in data if x["knife"] is not None and x["knife"] > 0)
    knife_no  = sum(1 for x in data if x["knife"] == 0)

    locker_yes = sum(1 for x in data if x["locker"] is not None and x["locker"] > 0)
    locker_no  = sum(1 for x in data if x["locker"] == 0)

    text = (
        "📊 Статистика:\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🔐 З шафкою: {locker_yes}\n"
        f"🚫 Без шафки: {locker_no}"
    )

    await update.message.reply_text(text)

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    names = [x["surname"] for x in data if x["knife"] is not None and x["knife"] > 0]

    await update.message.reply_text(
        "🔪 Прізвища з ножами:\n" + "\n".join(names)
        if names else "🔪 Прізвища з ножами:\nНемає даних."
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    names = [x["surname"] for x in data if x["knife"] == 0]

    await update.message.reply_text(
        "🚫 Прізвища без ножа:\n" + "\n".join(names)
        if names else "🚫 Прізвища без ножа:\nНемає даних."
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    names = [x["surname"] for x in data if x["locker"] is not None and x["locker"] > 0]

    await update.message.reply_text(
        "🔐 Прізвища з шафками:\n" + "\n".join(names)
        if names else "🔐 Прізвища з шафками:\nНемає даних."
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    names = [x["surname"] for x in data if x["locker"] == 0]

    await update.message.reply_text(
        "🚫 Прізвища без шафки:\n" + "\n".join(names)
        if names else "🚫 Прізвища без шафки:\nНемає даних."
    )

# ==============================
# START BOT
# ==============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()

if __name__ == "__main__":
    main()
