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
    ContextTypes,
)

# ===============================
# CONFIG
# ===============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ===============================
# RENDER KEEP-ALIVE
# ===============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ===============================
# CSV PARSER
# ===============================

def load_data():
    resp = requests.get(CSV_URL, timeout=20)
    resp.raise_for_status()

    reader = csv.DictReader(StringIO(resp.text))
    data = []

    for row in reader:
        surname = (row.get("surname") or "").strip()
        knife_raw = (row.get("knife") or "").strip()
        locker_raw = (row.get("locker") or "").strip()

        # ----- KNIFE -----
        has_knife = False
        if knife_raw.isdigit():
            has_knife = int(knife_raw) > 0

        # ----- LOCKER -----
        locker_raw_l = locker_raw.lower()
        has_locker = False

        if locker_raw.isdigit():
            has_locker = True
        elif locker_raw_l in ["так", "є", "есть", "ключ є", "имеется", "имеется всё"]:
            has_locker = True

        data.append({
            "surname": surname,
            "has_knife": has_knife,
            "has_locker": has_locker,
        })

    return data

# ===============================
# COMMANDS
# ===============================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    knife_yes = sum(1 for x in data if x["has_knife"])
    knife_no = sum(1 for x in data if not x["has_knife"])

    locker_yes = sum(1 for x in data if x["has_locker"])
    locker_no = sum(1 for x in data if not x["has_locker"])

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
    names = [x["surname"] for x in data if x["has_knife"] and x["surname"]]

    if not names:
        await update.message.reply_text("🔪 Прізвища з ножами:\nНемає даних.")
        return

    await update.message.reply_text(
        "🔪 Прізвища з ножами:\n" + "\n".join(names)
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    names = [x["surname"] for x in data if not x["has_knife"] and x["surname"]]

    if not names:
        await update.message.reply_text("🚫 Прізвища без ножа:\nНемає даних.")
        return

    await update.message.reply_text(
        "🚫 Прізвища без ножа:\n" + "\n".join(names)
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    names = [x["surname"] for x in data if x["has_locker"] and x["surname"]]

    if not names:
        await update.message.reply_text("🔐 Прізвища з шафками:\nНемає даних.")
        return

    await update.message.reply_text(
        "🔐 Прізвища з шафками:\n" + "\n".join(names)
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    names = [x["surname"] for x in data if not x["has_locker"] and x["surname"]]

    if not names:
        await update.message.reply_text("🚫 Прізвища без шафки:\nНемає даних.")
        return

    await update.message.reply_text(
        "🚫 Прізвища без шафки:\n" + "\n".join(names)
    )

# ===============================
# MAIN
# ===============================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()

if __name__ == "__main__":
    main()
