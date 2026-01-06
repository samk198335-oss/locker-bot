import os
import csv
import time
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
CACHE_TTL = 300

LOCAL_DB = "local_db.csv"

# ==============================
# 🔁 CSV CACHE
# ==============================

_csv_cache = {"data": [], "time": 0}


def load_csv():
    now = time.time()
    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_TTL:
        return _csv_cache["data"]

    data = []

    # Google CSV
    response = requests.get(CSV_URL, timeout=10)
    response.encoding = "utf-8"
    data.extend(list(csv.DictReader(StringIO(response.text))))

    # Local CSV
    if os.path.exists(LOCAL_DB):
        with open(LOCAL_DB, newline="", encoding="utf-8") as f:
            data.extend(list(csv.DictReader(f)))

    _csv_cache["data"] = data
    _csv_cache["time"] = now
    return data


def reset_cache():
    _csv_cache["data"] = []
    _csv_cache["time"] = 0


# ==============================
# 🧠 HELPERS
# ==============================

def get_value(row, field):
    field = field.lower()
    for k, v in row.items():
        if k and k.lower() == field:
            return (v or "").strip()
    return ""


def is_yes(v):
    return v.lower() in ("1", "так", "yes", "y", "true", "+")


def has_locker(v):
    return v and v.lower() not in ("-", "ні", "no", "0")


# ==============================
# 📋 KEYBOARDS
# ==============================

MAIN_KB = ReplyKeyboardMarkup(
    [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄️ З шафкою", "❌ Без шафки"],
        ["👥 Всі", "📊 Статистика"],
        ["➕ Додати працівника"]
    ],
    resize_keyboard=True
)

YES_NO_KB = ReplyKeyboardMarkup(
    [["Так", "Ні"]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Обери дію 👇", reply_markup=MAIN_KB)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    total = len(rows)
    knife_yes = sum(is_yes(get_value(r, "knife")) for r in rows)
    locker_yes = sum(has_locker(get_value(r, "locker")) for r in rows)

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {total - knife_yes}\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {total - locker_yes}"
    )


async def all_list(update, context):
    rows = load_csv()
    names = [get_value(r, "surname") for r in rows if get_value(r, "surname")]
    await update.message.reply_text("👥 Всі:\n\n" + "\n".join(names))


async def locker_list(update, context):
    rows = load_csv()
    res = [
        f"{get_value(r,'surname')} — {get_value(r,'locker')}"
        for r in rows if has_locker(get_value(r, "locker"))
    ]
    await update.message.reply_text("🗄️ З шафкою:\n\n" + "\n".join(res))


async def no_locker_list(update, context):
    rows = load_csv()
    res = [get_value(r, "surname") for r in rows if not has_locker(get_value(r, "locker"))]
    await update.message.reply_text("❌ Без шафки:\n\n" + "\n".join(res))


async def knife_list(update, context):
    rows = load_csv()
    res = [get_value(r, "surname") for r in rows if is_yes(get_value(r, "knife"))]
    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(res))


async def no_knife_list(update, context):
    rows = load_csv()
    res = [get_value(r, "surname") for r in rows if not is_yes(get_value(r, "knife"))]
    await update.message.reply_text("🚫 Без ножа:\n\n" + "\n".join(res))


# ==============================
# ➕ ADD WORKER FLOW
# ==============================

async def add_worker_start(update, context):
    context.user_data.clear()
    await update.message.reply_text("Введи прізвище та імʼя:", reply_markup=ReplyKeyboardRemove())
    context.user_data["step"] = "surname"


async def add_worker_flow(update, context):
    step = context.user_data.get("step")

    if step == "surname":
        context.user_data["surname"] = update.message.text.strip()
        context.user_data["step"] = "locker"
        await update.message.reply_text("Введи номер шафки або `-`:")

    elif step == "locker":
        context.user_data["locker"] = update.message.text.strip()
        context.user_data["step"] = "knife"
        await update.message.reply_text("Ніж є?", reply_markup=YES_NO_KB)

    elif step == "knife":
        knife = "1" if update.message.text.lower() == "так" else "0"

        row = {
            "Address": "LOCAL",
            "surname": context.user_data["surname"],
            "knife": knife,
            "locker": context.user_data["locker"]
        }

        write_header = not os.path.exists(LOCAL_DB)
        with open(LOCAL_DB, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if write_header:
                writer.writeheader()
            writer.writerow(row)

        reset_cache()

        await update.message.reply_text(
            "✅ Працівника додано!",
            reply_markup=MAIN_KB
        )
        context.user_data.clear()


# ==============================
# 🎛️ FILTER HANDLER
# ==============================

async def handle_filters(update, context):
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
    elif t == "➕ Додати працівника":
        await add_worker_start(update, context)
    elif context.user_data.get("step"):
        await add_worker_flow(update, context)


# ==============================
# 🌐 HEALTH
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def run_health():
    HTTPServer(("0.0.0.0", 10000), HealthHandler).serve_forever()


# ==============================
# 🚀 MAIN
# ==============================

def main():
    threading.Thread(target=run_health, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filters))

    app.run_polling()


if __name__ == "__main__":
    main()
