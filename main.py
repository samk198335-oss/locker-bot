import os
import csv
import time
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ==============================
# 🔧 CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
CACHE_TTL = 300  # 5 хв

# ==============================
# 🔁 CSV CACHE
# ==============================

_csv_cache = {"data": [], "time": 0}


def load_csv():
    now = time.time()

    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_TTL:
        return _csv_cache["data"]

    r = requests.get(CSV_URL, timeout=15)
    r.encoding = "utf-8-sig"  # 🔥 ВАЖЛИВО: прибирає BOM

    reader = csv.DictReader(StringIO(r.text))

    data = []
    for row in reader:
        clean_row = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
        }
        data.append(clean_row)

    _csv_cache["data"] = data
    _csv_cache["time"] = now
    return data


# ==============================
# 🧠 HELPERS
# ==============================

def is_yes(value: str) -> bool:
    return value.lower() in ("1", "yes", "y", "так", "є", "true", "+")


def has_locker(value: str) -> bool:
    return value and value.lower() not in ("-", "ні", "no", "0")


# ==============================
# 📋 KEYBOARD
# ==============================

KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄️ З шафкою", "❌ Без шафки"],
        ["👥 Всі", "📊 Статистика"]
    ],
    resize_keyboard=True
)

# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Обери фільтр або команду 👇",
        reply_markup=KEYBOARD
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    total = len(rows)
    knife_yes = knife_no = locker_yes = locker_no = 0

    for r in rows:
        if is_yes(r.get("knife", "")):
            knife_yes += 1
        else:
            knife_no += 1

        if has_locker(r.get("locker", "")):
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


async def all_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    names = [r["surname"] for r in rows if r.get("surname")]
    await update.message.reply_text("👥 Всі:\n\n" + "\n".join(names))


async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    names = [r["surname"] for r in rows if is_yes(r.get("knife", ""))]
    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(names))


async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    names = [r["surname"] for r in rows if not is_yes(r.get("knife", ""))]
    await update.message.reply_text("🚫 Без ножа:\n\n" + "\n".join(names))


async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [
        f"{r['surname']} — {r['locker']}"
        for r in rows
        if r.get("surname") and has_locker(r.get("locker", ""))
    ]
    await update.message.reply_text("🗄️ З шафкою:\n\n" + "\n".join(result))


async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    names = [r["surname"] for r in rows if not has_locker(r.get("locker", ""))]
    await update.message.reply_text("❌ Без шафки:\n\n" + "\n".join(names))


# ==============================
# 🎛️ FILTER HANDLER
# ==============================

async def handle_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "🔪 З ножем":
        await knife_list(update, context)
    elif t == "🚫 Без ножа":
        await no_knife_list(update, context)
    elif t == "🗄️ З шафкою":
        await locker_list(update, context)
    elif t == "❌ Без шафки":
        await no_locker_list(update, context)
    elif t == "👥 Всі":
        await all_list(update, context)
    elif t == "📊 Статистика":
        await stats(update, context)


# ==============================
# 🌐 RENDER KEEP ALIVE
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filters))

    app.run_polling()


if __name__ == "__main__":
    main()
