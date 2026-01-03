import os
import csv
import requests
import threading
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

NAME_FIELD = "Прізвище та імʼя"
KNIFE_FIELD = "Ніж"
LOCKER_FIELD = "Шафка"

YES_VALUES = {"yes", "y", "+", "1", "так", "true"}
NO_VALUES = {"no", "n", "-", "0", "ні", "false"}

# =========================
# HELPERS
# =========================

def normalize(value: str) -> str:
    return value.strip().lower()

def is_yes(value: str) -> bool:
    return normalize(value) in YES_VALUES

def is_no(value: str) -> bool:
    return normalize(value) in NO_VALUES

def load_rows():
    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()

    csv_data = StringIO(response.text)
    reader = csv.DictReader(csv_data)

    rows = []
    for row in reader:
        name = row.get(NAME_FIELD, "").strip()
        knife = row.get(KNIFE_FIELD, "").strip()
        locker = row.get(LOCKER_FIELD, "").strip()

        if name:
            rows.append({
                "name": name,
                "knife": knife,
                "locker": locker
            })

    return rows

# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/stats — загальна статистика\n"
        "/knife_list — прізвища з ножами\n"
        "/no_knife_list — прізвища без ножа\n"
        "/locker_list — прізвища з шафками\n"
        "/no_locker_list — прізвища без шафки"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()

    knife_yes = sum(1 for r in rows if is_yes(r["knife"]))
    knife_no = sum(1 for r in rows if is_no(r["knife"]))

    locker_yes = sum(1 for r in rows if is_yes(r["locker"]))
    locker_no = sum(1 for r in rows if is_no(r["locker"]))

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🔐 З шафкою: {locker_yes}\n"
        f"🚫 Без шафки: {locker_no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = [r["name"] for r in rows if is_yes(r["knife"])]

    if not result:
        await update.message.reply_text("🔪 Прізвища з ножами:\nНемає даних.")
        return

    text = "🔪 Прізвища з ножами:\n"
    for i, name in enumerate(result, 1):
        text += f"{i}. {name}\n"

    await update.message.reply_text(text)

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = [r["name"] for r in rows if is_no(r["knife"])]

    if not result:
        await update.message.reply_text("🚫 Прізвища без ножа:\nНемає даних.")
        return

    text = "🚫 Прізвища без ножа:\n"
    for i, name in enumerate(result, 1):
        text += f"{i}. {name}\n"

    await update.message.reply_text(text)

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = [r["name"] for r in rows if is_yes(r["locker"])]

    if not result:
        await update.message.reply_text("🔐 Прізвища з шафками:\nНемає даних.")
        return

    text = "🔐 Прізвища з шафками:\n"
    for i, name in enumerate(result, 1):
        text += f"{i}. {name}\n"

    await update.message.reply_text(text)

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = [r["name"] for r in rows if is_no(r["locker"])]

    if not result:
        await update.message.reply_text("🚫 Прізвища без шафки:\nНемає даних.")
        return

    text = "🚫 Прізвища без шафки:\n"
    for i, name in enumerate(result, 1):
        text += f"{i}. {name}\n"

    await update.message.reply_text(text)

# =========================
# RENDER KEEP-ALIVE
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_http():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()

# =========================
# MAIN
# =========================

def main():
    threading.Thread(target=run_http, daemon=True).start()

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
