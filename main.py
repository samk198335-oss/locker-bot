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
# 🔧 CONFIG
# ===============================

TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

PORT = int(os.environ.get("PORT", 10000))


# ===============================
# 🔧 RENDER KEEP-ALIVE
# ===============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()


# ===============================
# 📥 CSV LOADER
# ===============================

def load_csv():
    response = requests.get(CSV_URL, timeout=10)
    response.raise_for_status()
    content = response.content.decode("utf-8")
    reader = csv.DictReader(StringIO(content))
    return list(reader)


def normalize(value: str) -> str:
    if not value:
        return ""
    return value.strip().lower()


def is_yes(value: str) -> bool:
    return normalize(value) in ["yes", "y", "так", "+", "1"]


def is_no(value: str) -> bool:
    return normalize(value) in ["no", "n", "ні", "-", "0"]


# ===============================
# 📊 LOGIC
# ===============================

def get_stats():
    rows = load_csv()

    total = 0
    knife_yes = 0
    knife_no = 0
    locker_yes = 0
    locker_no = 0

    for r in rows:
        total += 1

        knife = r.get("Ніж", "")
        locker = r.get("Шафка", "")

        if is_yes(knife):
            knife_yes += 1
        elif is_no(knife):
            knife_no += 1

        if is_yes(locker):
            locker_yes += 1
        elif is_no(locker):
            locker_no += 1

    return total, knife_yes, knife_no, locker_yes, locker_no


def get_list(filter_key: str, need_yes: bool):
    rows = load_csv()
    result = []

    for r in rows:
        name = r.get("Прізвище", "").strip()
        value = r.get(filter_key, "")

        if not name:
            continue

        if need_yes and is_yes(value):
            result.append(name)
        if not need_yes and is_no(value):
            result.append(name)

    return result


# ===============================
# 🤖 COMMANDS
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Бот працює.\n\n"
        "Команди:\n"
        "/stats — статистика\n"
        "/knife_list — з ножами\n"
        "/no_knife_list — без ножів\n"
        "/locker_list — з шафками\n"
        "/no_locker_list — без шафок"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total, ky, kn, ly, ln = get_stats()

    text = (
        f"📊 Статистика:\n\n"
        f"Всього записів: {total}\n\n"
        f"🔪 З ножем: {ky}\n"
        f"❌ Без ножа: {kn}\n\n"
        f"🗄 З шафкою: {ly}\n"
        f"❌ Без шафки: {ln}"
    )

    await update.message.reply_text(text)


async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = get_list("Ніж", True)
    text = "🔪 З ножами:\n" + ("\n".join(items) if items else "Немає даних")
    await update.message.reply_text(text)


async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = get_list("Ніж", False)
    text = "❌ Без ножів:\n" + ("\n".join(items) if items else "Немає даних")
    await update.message.reply_text(text)


async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = get_list("Шафка", True)
    text = "🗄 З шафками:\n" + ("\n".join(items) if items else "Немає даних")
    await update.message.reply_text(text)


async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = get_list("Шафка", False)
    text = "❌ Без шафок:\n" + ("\n".join(items) if items else "Немає даних")
    await update.message.reply_text(text)


# ===============================
# 🚀 MAIN
# ===============================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()


if __name__ == "__main__":
    main()
