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
LOCAL_DB = []  # наша локальна база

# ==============================
# 📥 LOAD CSV
# ==============================

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


def build_local_db():
    global LOCAL_DB
    rows = load_csv()
    LOCAL_DB = []

    for r in rows:
        LOCAL_DB.append({
            "surname": get_value(r, "surname"),
            "knife": get_value(r, "knife"),
            "locker": get_value(r, "locker"),
        })

# ==============================
# 🧠 HELPERS
# ==============================

def get_value(row: dict, field_name: str) -> str:
    field_name = field_name.strip().lower()
    for key, value in row.items():
        if key and key.strip().lower() == field_name:
            return (value or "").strip()
    return ""


def is_yes(value: str) -> bool:
    return value.strip().lower() in ("1", "yes", "y", "так", "є", "+", "true")


def has_locker(value: str) -> bool:
    if not value:
        return False
    return value.strip().lower() not in ("-", "ні", "no", "0")

# ==============================
# 📋 KEYBOARDS
# ==============================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄️ З шафкою", "❌ Без шафки"],
        ["➕ Додати працівника"],
        ["✏️ Змінити прізвище"],
        ["👥 Всі", "📊 Статистика"]
    ],
    resize_keyboard=True
)

KNIFE_KEYBOARD = ReplyKeyboardMarkup(
    [["🔪 Є ніж", "🚫 Немає ножа"]],
    resize_keyboard=True
)

# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    build_local_db()
    await update.message.reply_text(
        "👋 Бот готовий. Обери дію 👇",
        reply_markup=MAIN_KEYBOARD
    )

# ==============================
# 📊 STATS & LISTS
# ==============================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = len(LOCAL_DB)
    knife_yes = sum(1 for r in LOCAL_DB if is_yes(r["knife"]))
    knife_no = total - knife_yes
    locker_yes = sum(1 for r in LOCAL_DB if has_locker(r["locker"]))
    locker_no = total - locker_yes

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )


async def list_filtered(update, title, condition):
    result = [
        r["surname"] + (f" — {r['locker']}" if has_locker(r["locker"]) else "")
        for r in LOCAL_DB if condition(r)
    ]
    await update.message.reply_text(f"{title}:\n\n" + "\n".join(result))


# ==============================
# ➕ ADD EMPLOYEE FLOW
# ==============================

async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "surname"
    await update.message.reply_text("✍️ Введи прізвище та імʼя працівника:")


async def handle_add_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "surname":
        context.user_data["surname"] = update.message.text
        context.user_data["step"] = "locker"
        await update.message.reply_text("🗄️ Введи номер шафки або -")
        return

    if step == "locker":
        context.user_data["locker"] = update.message.text
        context.user_data["step"] = "knife"
        await update.message.reply_text("🔪 Є ніж?", reply_markup=KNIFE_KEYBOARD)
        return

    if step == "knife":
        knife = "1" if "Є" in update.message.text else "0"

        LOCAL_DB.append({
            "surname": context.user_data["surname"],
            "locker": context.user_data["locker"],
            "knife": knife
        })

        context.user_data.clear()
        await update.message.reply_text(
            "✅ Працівника додано",
            reply_markup=MAIN_KEYBOARD
        )

# ==============================
# ✏️ RENAME
# ==============================

async def rename_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "old"
    await update.message.reply_text("✏️ Введи старе прізвище:")


async def handle_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "old":
        context.user_data["old"] = update.message.text
        context.user_data["step"] = "new"
        await update.message.reply_text("✏️ Введи нове прізвище:")
        return

    if step == "new":
        old = context.user_data["old"]
        new = update.message.text

        for r in LOCAL_DB:
            if r["surname"] == old:
                r["surname"] = new

        context.user_data.clear()
        await update.message.reply_text("✅ Прізвище змінено", reply_markup=MAIN_KEYBOARD)

# ==============================
# 🎛️ HANDLER
# ==============================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if context.user_data.get("step"):
        if context.user_data["step"] in ("surname", "locker", "knife"):
            await handle_add_flow(update, context)
        else:
            await handle_rename(update, context)
        return

    if text == "📊 Статистика":
        await stats(update, context)
    elif text == "➕ Додати працівника":
        await add_employee(update, context)
    elif text == "✏️ Змінити прізвище":
        await rename_employee(update, context)
    elif text == "🔪 З ножем":
        await list_filtered(update, "🔪 З ножем", lambda r: is_yes(r["knife"]))
    elif text == "🚫 Без ножа":
        await list_filtered(update, "🚫 Без ножа", lambda r: not is_yes(r["knife"]))
    elif text == "🗄️ З шафкою":
        await list_filtered(update, "🗄️ З шафкою", lambda r: has_locker(r["locker"]))
    elif text == "❌ Без шафки":
        await list_filtered(update, "❌ Без шафки", lambda r: not has_locker(r["locker"]))
    elif text == "👥 Всі":
        await list_filtered(update, "👥 Всі", lambda r: True)

# ==============================
# 🌐 RENDER
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling()

if __name__ == "__main__":
    main()
