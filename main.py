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
CACHE_TTL = 300  # 5 хвилин

LOCAL_DATA_FILE = os.getenv("LOCAL_DATA_FILE", "local_data.csv")

# ==============================
# 🔁 CSV CACHE
# ==============================

_csv_cache = {"data": [], "time": 0}


def ensure_local_file():
    if os.path.exists(LOCAL_DATA_FILE):
        return
    with open(LOCAL_DATA_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Adress", "surname", "knife", "locker"])
        w.writeheader()


def read_local_csv():
    ensure_local_file()
    with open(LOCAL_DATA_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_csv():
    """
    Loads remote CSV + local additions, with cache.
    """
    now = time.time()

    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_TTL:
        return _csv_cache["data"]

    response = requests.get(CSV_URL, timeout=15)
    response.encoding = "utf-8"

    reader = csv.DictReader(StringIO(response.text))
    remote = list(reader)

    local = read_local_csv()

    data = remote + local

    _csv_cache["data"] = data
    _csv_cache["time"] = now
    return data


def invalidate_cache():
    _csv_cache["data"] = []
    _csv_cache["time"] = 0


# ==============================
# 🧠 SAFE COLUMN ACCESS
# ==============================

def get_value(row: dict, field_name: str) -> str:
    field_name = field_name.strip().lower()
    for key, value in row.items():
        if key and key.strip().lower() == field_name:
            return (value or "").strip()
    return ""


def knife_status(value: str) -> str:
    """
    STRICT knife logic:
      "1" => yes
      "0" => no
      anything else (2, empty, text) => unknown
    """
    v = (value or "").strip()
    if v == "1":
        return "yes"
    if v == "0":
        return "no"
    return "unknown"


def has_locker(value: str) -> bool:
    if not value:
        return False
    v = value.strip()
    return v not in ("-", "—", "0")


def norm_locker(value: str) -> str:
    v = (value or "").strip()
    if v in ("", "-", "—"):
        return ""
    return v


# ==============================
# 📋 KEYBOARD
# ==============================

KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄️ З шафкою", "❌ Без шафки"],
        ["👥 Всі", "📊 Статистика"],
        ["➕ Додати працівника"],
    ],
    resize_keyboard=True
)

ADD_KNIFE_KB = ReplyKeyboardMarkup(
    [
        ["🔪 Є ніж", "🚫 Немає ножа"],
        ["❌ Скасувати"],
    ],
    resize_keyboard=True
)

CANCEL_KB = ReplyKeyboardMarkup(
    [["❌ Скасувати"]],
    resize_keyboard=True
)

# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # reset any flow
    context.user_data.pop("add_state", None)
    context.user_data.pop("add_data", None)

    await update.message.reply_text(
        "👋 Привіт! Обери фільтр або команду 👇",
        reply_markup=KEYBOARD
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    # count only rows with surname
    rows = [r for r in rows if get_value(r, "surname")]

    total = len(rows)
    knife_yes = knife_no = knife_unknown = 0
    locker_yes = locker_no = 0

    for r in rows:
        ks = knife_status(get_value(r, "knife"))
        if ks == "yes":
            knife_yes += 1
        elif ks == "no":
            knife_no += 1
        else:
            knife_unknown += 1

        if has_locker(get_value(r, "locker")):
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n"
        f"❓ Ніж не вказано: {knife_unknown}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}",
        reply_markup=KEYBOARD
    )


async def all_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [get_value(r, "surname") for r in rows if get_value(r, "surname")]

    if not result:
        await update.message.reply_text("👥 Всі:\n\nНемає даних.", reply_markup=KEYBOARD)
        return

    await update.message.reply_text("👥 Всі:\n\n" + "\n".join(result), reply_markup=KEYBOARD)


async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        surname = get_value(r, "surname")
        locker = get_value(r, "locker")
        if surname and has_locker(locker):
            result.append(f"{surname} — {locker}")

    if not result:
        await update.message.reply_text("🗄️ З шафкою:\n\nНемає даних.", reply_markup=KEYBOARD)
        return

    await update.message.reply_text("🗄️ З шафкою:\n\n" + "\n".join(result), reply_markup=KEYBOARD)


async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [get_value(r, "surname") for r in rows if get_value(r, "surname") and not has_locker(get_value(r, "locker"))]

    if not result:
        await update.message.reply_text("❌ Без шафки:\n\nНемає даних.", reply_markup=KEYBOARD)
        return

    await update.message.reply_text("❌ Без шафки:\n\n" + "\n".join(result), reply_markup=KEYBOARD)


async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [get_value(r, "surname") for r in rows if get_value(r, "surname") and knife_status(get_value(r, "knife")) == "yes"]

    if not result:
        await update.message.reply_text("🔪 З ножем:\n\nНемає даних.", reply_markup=KEYBOARD)
        return

    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(result), reply_markup=KEYBOARD)


async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [get_value(r, "surname") for r in rows if get_value(r, "surname") and knife_status(get_value(r, "knife")) == "no"]

    if not result:
        await update.message.reply_text("🚫 Без ножа:\n\nНемає даних.", reply_markup=KEYBOARD)
        return

    await update.message.reply_text("🚫 Без ножа:\n\n" + "\n".join(result), reply_markup=KEYBOARD)


# ==============================
# ➕ ADD EMPLOYEE (simple state)
# ==============================

def append_local_row(surname: str, locker: str, knife: str):
    ensure_local_file()
    with open(LOCAL_DATA_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Adress", "surname", "knife", "locker"])
        w.writerow({
            "Adress": "",
            "surname": surname.strip(),
            "knife": knife.strip(),
            "locker": locker.strip(),
        })


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["add_state"] = "surname"
    context.user_data["add_data"] = {}
    await update.message.reply_text(
        "➕ Додати працівника\n\nВведіть прізвище та імʼя (як у таблиці):",
        reply_markup=CANCEL_KB
    )


async def add_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # cancel
    if text == "❌ Скасувати":
        context.user_data.pop("add_state", None)
        context.user_data.pop("add_data", None)
        await update.message.reply_text("Скасовано.", reply_markup=KEYBOARD)
        return

    state = context.user_data.get("add_state")
    data = context.user_data.get("add_data", {})

    if state == "surname":
        if not text:
            await update.message.reply_text("Введіть прізвище та імʼя:", reply_markup=CANCEL_KB)
            return
        data["surname"] = text
        context.user_data["add_data"] = data
        context.user_data["add_state"] = "locker"
        await update.message.reply_text(
            "Введіть номер шафки або `-` якщо немає:",
            reply_markup=CANCEL_KB
        )
        return

    if state == "locker":
        locker = norm_locker(text)
        data["locker"] = locker
        context.user_data["add_data"] = data
        context.user_data["add_state"] = "knife"
        await update.message.reply_text(
            "Оберіть ніж кнопкою:",
            reply_markup=ADD_KNIFE_KB
        )
        return

    if state == "knife":
        if text not in ("🔪 Є ніж", "🚫 Немає ножа"):
            await update.message.reply_text("Оберіть варіант кнопкою нижче 👇", reply_markup=ADD_KNIFE_KB)
            return

        knife = "1" if text == "🔪 Є ніж" else "0"
        surname = data.get("surname", "").strip()
        locker = data.get("locker", "")

        if not surname:
            # safety fallback
            context.user_data.pop("add_state", None)
            context.user_data.pop("add_data", None)
            await update.message.reply_text("Помилка: не знайдено прізвище. Спробуйте ще раз.", reply_markup=KEYBOARD)
            return

        append_local_row(surname=surname, locker=locker, knife=knife)
        invalidate_cache()

        context.user_data.pop("add_state", None)
        context.user_data.pop("add_data", None)

        msg = f"✅ Додано: {surname}"
        if locker:
            msg += f" — {locker}"
        msg += f"\nНіж: {'Є' if knife == '1' else 'Немає'}"

        await update.message.reply_text(msg, reply_markup=KEYBOARD)
        return


# ==============================
# 🎛️ FILTER HANDLER (КЛЮЧОВЕ!)
# ==============================

async def handle_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # if we are in add flow - handle it first
    if context.user_data.get("add_state"):
        await add_handle(update, context)
        return

    if text == "🔪 З ножем":
        await knife_list(update, context)
    elif text == "🚫 Без ножа":
        await no_knife_list(update, context)
    elif text == "🗄️ З шафкою":
        await locker_list(update, context)
    elif text == "❌ Без шафки":
        await no_locker_list(update, context)
    elif text == "👥 Всі":
        await all_list(update, context)
    elif text == "📊 Статистика":
        await stats(update, context)
    elif text == "➕ Додати працівника":
        await add_start(update, context)


# ==============================
# 🌐 RENDER KEEP ALIVE
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def run_health_server():
    port = int(os.getenv("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


# ==============================
# 🚀 MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filters))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
