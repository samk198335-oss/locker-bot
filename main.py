import os
import csv
import time
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# ==============================
# 🔧 CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
CACHE_TTL = 300

# ==============================
# 🔁 CSV CACHE
# ==============================

_csv_cache = {"data": [], "time": 0}


def load_csv():
    now = time.time()
    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_TTL:
        return _csv_cache["data"]

    r = requests.get(CSV_URL, timeout=10)
    r.encoding = "utf-8"
    data = list(csv.DictReader(StringIO(r.text)))

    _csv_cache["data"] = data
    _csv_cache["time"] = now
    return data


# ==============================
# 🧠 HELPERS
# ==============================

def get_value(row: dict, field: str) -> str:
    field = field.lower().strip()
    for k, v in row.items():
        if k and k.lower().strip() == field:
            return (v or "").strip()
    return ""


def is_yes(v: str) -> bool:
    return v.lower() in ("1", "yes", "y", "так", "є", "true", "+")


def has_locker(v: str) -> bool:
    return v and v.lower() not in ("-", "ні", "no", "0")


# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "/stats\n"
        "/locker_list\n"
        "/no_locker_list\n"
        "/knife_list\n"
        "/no_knife_list\n"
        "/find <прізвище>\n"
        "/filter"
    )


# ==============================
# 🔍 FIND BY SURNAME
# ==============================

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Вкажи прізвище: /find Іванов")
        return

    query = " ".join(context.args).lower()
    rows = load_csv()
    result = []

    for r in rows:
        surname = get_value(r, "surname")
        if query in surname.lower():
            knife = "так" if is_yes(get_value(r, "knife")) else "ні"
            locker_val = get_value(r, "locker")
            locker = locker_val if has_locker(locker_val) else "немає"

            result.append(
                f"👤 {surname}\n"
                f"🔪 Ніж: {knife}\n"
                f"🗄️ Шафка: {locker}"
            )

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text("\n\n".join(result))


# ==============================
# 🎛️ FILTER BUTTONS
# ==============================

async def filter_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔪 З ножем", callback_data="knife_yes")],
        [InlineKeyboardButton("🚫 Без ножа", callback_data="knife_no")],
        [InlineKeyboardButton("🗄️ З шафкою", callback_data="locker_yes")],
        [InlineKeyboardButton("❌ Без шафки", callback_data="locker_no")],
        [InlineKeyboardButton("👥 Всі", callback_data="all")],
    ]
    await update.message.reply_text(
        "🔍 Обери фільтр:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    rows = load_csv()
    result = []

    for r in rows:
        surname = get_value(r, "surname")
        knife = is_yes(get_value(r, "knife"))
        locker = has_locker(get_value(r, "locker"))

        if query.data == "knife_yes" and knife:
            result.append(surname)
        elif query.data == "knife_no" and not knife:
            result.append(surname)
        elif query.data == "locker_yes" and locker:
            result.append(surname)
        elif query.data == "locker_no" and not locker:
            result.append(surname)
        elif query.data == "all":
            result.append(surname)

    if not result:
        await query.edit_message_text("❌ Немає даних")
        return

    await query.edit_message_text("\n".join(result))


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
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("filter", filter_menu))
    app.add_handler(CallbackQueryHandler(filter_handler))

    app.run_polling()


if __name__ == "__main__":
    main()
