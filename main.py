import os
import csv
import time
import threading
import requests
import re
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

LOCAL_DATA_FILE = os.getenv("LOCAL_DATA_FILE", "local_data.csv")
LOCAL_OPS_FILE = os.getenv("LOCAL_OPS_FILE", "local_ops.csv")

# ==============================
# 🔁 CACHE
# ==============================

_csv_cache = {"data": [], "time": 0}


def invalidate_cache():
    _csv_cache["data"] = []
    _csv_cache["time"] = 0


# ==============================
# 🧠 NORMALIZATION
# ==============================

def normalize_text(s: str) -> str:
    # NBSP -> space, collapse spaces, strip
    s = (s or "").replace("\u00A0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm_key(s: str) -> str:
    return normalize_text(s).lower()


def norm_name(s: str) -> str:
    # name matching uses normalized lowercase
    return norm_key(s)


# ==============================
# 🧠 SAFE COLUMN ACCESS / SET
# ==============================

def get_value(row: dict, field_name: str) -> str:
    want = norm_key(field_name)
    for k, v in row.items():
        if k and norm_key(k) == want:
            return normalize_text(v)
    return ""


def set_value(row: dict, field_name: str, new_value: str):
    """
    Set value using the actual key existing in row (case/space insensitive).
    If not found, sets with canonical key.
    """
    want = norm_key(field_name)
    for k in list(row.keys()):
        if k and norm_key(k) == want:
            row[k] = new_value
            return
    # fallback
    row[field_name] = new_value


def same_name(a: str, b: str) -> bool:
    return norm_name(a) == norm_name(b)


def knife_status(value: str) -> str:
    v = normalize_text(value)
    if v == "1":
        return "yes"
    if v == "0":
        return "no"
    return "unknown"


def has_locker(value: str) -> bool:
    v = normalize_text(value)
    if not v:
        return False
    return v not in ("-", "—", "0")


def norm_locker(value: str) -> str:
    v = normalize_text(value)
    if v in ("", "-", "—"):
        return ""
    return v


# ==============================
# 💾 LOCAL FILES
# ==============================

def ensure_local_file():
    if os.path.exists(LOCAL_DATA_FILE):
        return
    with open(LOCAL_DATA_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Adress", "surname", "knife", "locker"])
        w.writeheader()


def read_local_csv():
    ensure_local_file()
    with open(LOCAL_DATA_FILE, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_local_row(surname: str, locker: str, knife: str):
    ensure_local_file()
    with open(LOCAL_DATA_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Adress", "surname", "knife", "locker"])
        w.writerow({"Adress": "", "surname": surname, "knife": knife, "locker": locker})


def ensure_ops_file():
    if os.path.exists(LOCAL_OPS_FILE):
        return
    with open(LOCAL_OPS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["op", "target", "new_surname", "knife", "locker"])
        w.writeheader()


def read_ops():
    ensure_ops_file()
    with open(LOCAL_OPS_FILE, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_op(op: str, target: str, new_surname: str = "", knife: str = "", locker: str = ""):
    ensure_ops_file()
    with open(LOCAL_OPS_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["op", "target", "new_surname", "knife", "locker"])
        w.writerow({
            "op": op,
            "target": normalize_text(target),
            "new_surname": normalize_text(new_surname),
            "knife": normalize_text(knife),
            "locker": normalize_text(locker),
        })


# ==============================
# 🧩 APPLY OPS
# ==============================

def apply_ops(rows: list, ops: list) -> list:
    for op in ops:
        kind = norm_key(op.get("op", ""))
        target = normalize_text(op.get("target", ""))
        if not target:
            continue

        if kind == "rename":
            new_surname = normalize_text(op.get("new_surname", ""))
            if not new_surname:
                continue
            for r in rows:
                if same_name(get_value(r, "surname"), target):
                    set_value(r, "surname", new_surname)
            continue

        if kind == "set":
            knife = normalize_text(op.get("knife", ""))
            locker = normalize_text(op.get("locker", ""))

            for r in rows:
                if same_name(get_value(r, "surname"), target):
                    # knife: "1"/"0"/"-"(clear)
                    if knife != "":
                        set_value(r, "knife", knife)
                    # locker: value or "-" clear marker
                    if locker != "":
                        set_value(r, "locker", locker)
            continue

    return rows


# ==============================
# 📥 LOAD CSV (remote + local + ops)
# ==============================

def load_csv():
    now = time.time()
    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_TTL:
        return _csv_cache["data"]

    response = requests.get(CSV_URL, timeout=15)
    response.encoding = "utf-8"

    reader = csv.DictReader(StringIO(response.text))
    remote = list(reader)

    local = read_local_csv()
    ops = read_ops()

    data = remote + local
    data = apply_ops(data, ops)

    _csv_cache["data"] = data
    _csv_cache["time"] = now
    return data


# ==============================
# 📋 KEYBOARDS
# ==============================

KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄️ З шафкою", "❌ Без шафки"],
        ["👥 Всі", "📊 Статистика"],
        ["➕ Додати працівника"],
        ["✏️ Змінити прізвище", "🗄️ Редагувати шафку", "🔪 Редагувати ніж"],
    ],
    resize_keyboard=True
)

ADD_KNIFE_KB = ReplyKeyboardMarkup(
    [["🔪 Є ніж", "🚫 Немає ножа"], ["❌ Скасувати"]],
    resize_keyboard=True
)

EDIT_KNIFE_KB = ReplyKeyboardMarkup(
    [["🔪 Є ніж", "🚫 Немає ножа"], ["❓ Очистити (не вказано)"], ["❌ Скасувати"]],
    resize_keyboard=True
)

CANCEL_KB = ReplyKeyboardMarkup([["❌ Скасувати"]], resize_keyboard=True)


async def back_to_menu(update: Update, text: str = "✅ Готово. Обери дію 👇"):
    # hard reset flow + always restore keyboard
    if update.message:
        await update.message.reply_text(text, reply_markup=KEYBOARD)


# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👋 Привіт! Обери фільтр або команду 👇", reply_markup=KEYBOARD)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [r for r in load_csv() if get_value(r, "surname")]
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
    await update.message.reply_text("👥 Всі:\n\n" + ("\n".join(result) if result else "Немає даних."), reply_markup=KEYBOARD)


async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []
    for r in rows:
        surname = get_value(r, "surname")
        locker = get_value(r, "locker")
        if surname and has_locker(locker):
            result.append(f"{surname} — {locker}")
    await update.message.reply_text("🗄️ З шафкою:\n\n" + ("\n".join(result) if result else "Немає даних."), reply_markup=KEYBOARD)


async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [get_value(r, "surname") for r in rows if get_value(r, "surname") and not has_locker(get_value(r, "locker"))]
    await update.message.reply_text("❌ Без шафки:\n\n" + ("\n".join(result) if result else "Немає даних."), reply_markup=KEYBOARD)


async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [get_value(r, "surname") for r in rows if get_value(r, "surname") and knife_status(get_value(r, "knife")) == "yes"]
    await update.message.reply_text("🔪 З ножем:\n\n" + ("\n".join(result) if result else "Немає даних."), reply_markup=KEYBOARD)


async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = [get_value(r, "surname") for r in rows if get_value(r, "surname") and knife_status(get_value(r, "knife")) == "no"]
    await update.message.reply_text("🚫 Без ножа:\n\n" + ("\n".join(result) if result else "Немає даних."), reply_markup=KEYBOARD)


# ==============================
# ➕ ADD EMPLOYEE
# ==============================

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "add"
    context.user_data["state"] = "surname"
    context.user_data["data"] = {}
    await update.message.reply_text("➕ Додати працівника\n\nВведіть прізвище та імʼя:", reply_markup=CANCEL_KB)


async def add_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_text(update.message.text)

    if text == "❌ Скасувати":
        context.user_data.clear()
        await back_to_menu(update, "Скасовано. Обери дію 👇")
        return

    state = context.user_data.get("state")
    data = context.user_data.get("data", {})

    if state == "surname":
        if not text:
            await update.message.reply_text("Введіть прізвище та імʼя:", reply_markup=CANCEL_KB)
            return
        data["surname"] = text
        context.user_data["data"] = data
        context.user_data["state"] = "locker"
        await update.message.reply_text("Введіть номер шафки або `-` якщо немає:", reply_markup=CANCEL_KB)
        return

    if state == "locker":
        data["locker"] = norm_locker(text)
        context.user_data["data"] = data
        context.user_data["state"] = "knife"
        await update.message.reply_text("Оберіть ніж кнопкою:", reply_markup=ADD_KNIFE_KB)
        return

    if state == "knife":
        if text not in ("🔪 Є ніж", "🚫 Немає ножа"):
            await update.message.reply_text("Оберіть варіант кнопкою 👇", reply_markup=ADD_KNIFE_KB)
            return

        knife = "1" if text == "🔪 Є ніж" else "0"
        surname = data.get("surname", "")
        locker = data.get("locker", "")

        append_local_row(surname=surname, locker=locker, knife=knife)
        invalidate_cache()
        context.user_data.clear()

        await back_to_menu(update, f"✅ Додано: {surname}" + (f" — {locker}" if locker else "") + f"\nНіж: {'Є' if knife=='1' else 'Немає'}")
        return


# ==============================
# ✏️ RENAME SURNAME
# ==============================

async def rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "rename"
    context.user_data["state"] = "old"
    context.user_data["data"] = {}
    await update.message.reply_text("✏️ Змінити прізвище\n\nВведіть ПОТОЧНЕ прізвище та імʼя:", reply_markup=CANCEL_KB)


async def rename_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_text(update.message.text)

    if text == "❌ Скасувати":
        context.user_data.clear()
        await back_to_menu(update, "Скасовано. Обери дію 👇")
        return

    state = context.user_data.get("state")
    data = context.user_data.get("data", {})

    if state == "old":
        data["old"] = text
        context.user_data["data"] = data
        context.user_data["state"] = "new"
        await update.message.reply_text("Введіть НОВЕ прізвище та імʼя:", reply_markup=CANCEL_KB)
        return

    if state == "new":
        old = data.get("old", "")
        new = text
        append_op(op="rename", target=old, new_surname=new)
        invalidate_cache()
        context.user_data.clear()
        await back_to_menu(update, f"✅ Змінено:\n{old} ➜ {new}")
        return


# ==============================
# 🗄️ EDIT LOCKER
# ==============================

async def edit_locker_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "edit_locker"
    context.user_data["state"] = "who"
    context.user_data["data"] = {}
    await update.message.reply_text("🗄️ Редагувати шафку\n\nВведіть прізвище та імʼя:", reply_markup=CANCEL_KB)


async def edit_locker_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_text(update.message.text)

    if text == "❌ Скасувати":
        context.user_data.clear()
        await back_to_menu(update, "Скасовано. Обери дію 👇")
        return

    state = context.user_data.get("state")
    data = context.user_data.get("data", {})

    if state == "who":
        data["who"] = text
        context.user_data["data"] = data
        context.user_data["state"] = "locker"
        await update.message.reply_text("Введіть новий номер шафки або `-` щоб прибрати:", reply_markup=CANCEL_KB)
        return

    if state == "locker":
        who = data.get("who", "")
        locker = norm_locker(text)
        locker_to_store = locker if locker else "-"  # "-" forces clearing
        append_op(op="set", target=who, locker=locker_to_store)
        invalidate_cache()
        context.user_data.clear()
        await back_to_menu(update, f"✅ Шафку оновлено для: {who}\nНова шафка: {locker if locker else 'немає'}")
        return


# ==============================
# 🔪 EDIT KNIFE
# ==============================

async def edit_knife_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["flow"] = "edit_knife"
    context.user_data["state"] = "who"
    context.user_data["data"] = {}
    await update.message.reply_text("🔪 Редагувати ніж\n\nВведіть прізвище та імʼя:", reply_markup=CANCEL_KB)


async def edit_knife_handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_text(update.message.text)

    if text == "❌ Скасувати":
        context.user_data.clear()
        await back_to_menu(update, "Скасовано. Обери дію 👇")
        return

    state = context.user_data.get("state")
    data = context.user_data.get("data", {})

    if state == "who":
        data["who"] = text
        context.user_data["data"] = data
        context.user_data["state"] = "knife"
        await update.message.reply_text("Оберіть ніж кнопкою:", reply_markup=EDIT_KNIFE_KB)
        return

    if state == "knife":
        who = data.get("who", "")

        if text not in ("🔪 Є ніж", "🚫 Немає ножа", "❓ Очистити (не вказано)"):
            await update.message.reply_text("Оберіть варіант кнопкою 👇", reply_markup=EDIT_KNIFE_KB)
            return

        knife = "1" if text == "🔪 Є ніж" else ("0" if text == "🚫 Немає ножа" else "-")
        append_op(op="set", target=who, knife=knife)
        invalidate_cache()
        context.user_data.clear()

        shown = "Є" if knife == "1" else ("Немає" if knife == "0" else "не вказано")
        await back_to_menu(update, f"✅ Ніж оновлено для: {who}\nНіж: {shown}")
        return


# ==============================
# 🎛️ MAIN HANDLER
# ==============================

async def handle_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_text(update.message.text)
    flow = context.user_data.get("flow")

    if flow == "add":
        await add_handle(update, context)
        return
    if flow == "rename":
        await rename_handle(update, context)
        return
    if flow == "edit_locker":
        await edit_locker_handle(update, context)
        return
    if flow == "edit_knife":
        await edit_knife_handle(update, context)
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
    elif text == "✏️ Змінити прізвище":
        await rename_start(update, context)
    elif text == "🗄️ Редагувати шафку":
        await edit_locker_start(update, context)
    elif text == "🔪 Редагувати ніж":
        await edit_knife_start(update, context)


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
