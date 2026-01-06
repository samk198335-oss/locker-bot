import os
import csv
import time
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==============================
# 🔧 CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

CACHE_TTL = 300  # 5 хвилин

# ==============================
# 🔁 CSV CACHE
# ==============================

_csv_cache = {
    "data": [],
    "time": 0
}


def load_csv():
    now = time.time()

    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_TTL:
        return _csv_cache["data"]

    response = requests.get(CSV_URL, timeout=10)
    response.encoding = "utf-8"

    reader = csv.DictReader(StringIO(response.text))
    data = list(reader)

    _csv_cache["data"] = data
    _csv_cache["time"] = now

    return data


# ==============================
# 🧠 SAFE COLUMN ACCESS
# ==============================

def get_value(row: dict, field_name: str) -> str:
    """
    Безпечне отримання значення з CSV:
    ігнорує регістр, пробіли, BOM-символи
    """
    field_name = field_name.strip().lower()

    for key, value in row.items():
        if key and key.strip().lower() == field_name:
            return (value or "").strip()

    return ""


def is_yes(value: str) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("1", "yes", "y", "так", "є", "true", "+")


def has_locker(value: str) -> bool:
    if not value:
        return False
    return value.strip().lower() not in ("-", "ні", "no", "0")


# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Доступні команди:\n"
        "/stats\n"
        "/locker_list\n"
        "/no_locker_list\n"
        "/knife_list\n"
        "/no_knife_list"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    total = len(rows)
    knife_yes = 0
    knife_no = 0
    locker_yes = 0
    locker_no = 0

    for r in rows:
        if is_yes(get_value(r, "knife")):
            knife_yes += 1
        else:
            knife_no += 1

        if has_locker(get_value(r, "locker")):
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )


# ==============================
# 🗄️ LOCKERS — FIXED
# ==============================

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        surname = get_value(r, "surname")
        locker = get_value(r, "locker")

        if surname and has_locker(locker):
            result.append(f"{surname} — {locker}")

    if not result:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text(
        "🗄️ З шафкою:\n\n" + "\n".join(result)
    )


async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        surname = get_value(r, "surname")
        locker = get_value(r, "locker")

        if surname and not has_locker(locker):
            result.append(surname)

    if not result:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text(
        "❌ Без шафки:\n\n" + "\n".join(result)
    )


# ==============================
# 🔪 KNIFE (ще без правок)
# ==============================

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        if is_yes(get_value(r, "knife")):
            result.append(get_value(r, "surname"))

    if not result:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(result))


async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        if not is_yes(get_value(r, "knife")):
            result.append(get_value(r, "surname"))

    if not result:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text("🚫 Без ножа:\n\n" + "\n".join(result))


# ==============================
# 🌐 RENDER KEEP ALIVE
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")


def run_health_server():
    HTTPServer(("0.0.0.0", 10000), HealthHandler).serve_forever()


# ==============================
# 🚀 MAIN
# ==============================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))

    app.run_polling()


if __name__ == "__main__":
    main()
