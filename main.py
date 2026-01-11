import os
import csv
import re
import time
import shutil
import threading
from datetime import datetime
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, Document
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==============================
# 🔧 RENDER FREE STABILIZATION (HTTP PORT)
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ==============================
# 🔑 CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CSV_URL = os.getenv(
    "CSV_URL",
    "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
).strip()

LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", "local_data.csv").strip()

BACKUP_CHAT_ID_RAW = os.getenv("BACKUP_CHAT_ID", "").strip()
BACKUP_CHAT_ID = int(BACKUP_CHAT_ID_RAW) if BACKUP_CHAT_ID_RAW else None

BACKUP_DIR = os.getenv("BACKUP_DIR", "backups").strip()
os.makedirs(BACKUP_DIR, exist_ok=True)

CACHE_TTL = 3
_db_cache = {"time": 0.0, "rows": []}

# ==============================
# 🧩 UI
# ==============================

BTN_STATS = "📊 Статистика"
BTN_ALL = "👥 Всі"

BTN_WITH_LOCKER = "🗄️ З шафкою"
BTN_NO_LOCKER = "⛔ Без шафки"

BTN_WITH_KNIFE = "🔪 З ножем"
BTN_NO_KNIFE = "🚫 Без ножа"

BTN_ADD = "➕ Додати працівника"
BTN_EDIT = "✏️ Редагувати працівника"
BTN_DELETE = "🗑️ Видалити працівника"

BTN_BACKUP = "💾 Backup бази"
BTN_SEED = "🧬 Seed з Google"
BTN_RESTORE = "♻️ Відновити з файлу"

MAIN_KB = ReplyKeyboardMarkup(
    [
        [BTN_STATS, BTN_ALL],
        [BTN_WITH_LOCKER, BTN_NO_LOCKER],
        [BTN_WITH_KNIFE, BTN_NO_KNIFE],
        [BTN_ADD, BTN_EDIT],
        [BTN_DELETE],
        [BTN_BACKUP, BTN_SEED],
        [BTN_RESTORE],
    ],
    resize_keyboard=True
)

# ==============================
# 🧠 HELPERS
# ==============================

def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def safe_lower(s: str) -> str:
    return normalize_text(s).lower()

# ✅ ТІЛЬКИ ЦЕ МІНЯЄМО ПО ШАФКАХ
def locker_has_value(v: str) -> bool:
    v = normalize_text(v)
    if not v:
        return False
    v_low = safe_lower(v)
    if v_low in {"-", "—", "–", "нема", "нет", "ні", "no", "none"}:
        return False
    return True

# ✅ ТІЛЬКИ ЦЕ МІНЯЄМО ПО НОЖАХ
def knife_has(v: str) -> bool:
    v = normalize_text(v)
    return v in {"1", "2"}  # 1,2 = є ніж

def ensure_columns(row: dict) -> dict:
    """
    Жорстко тримаємось назв колонок:
    Address, surname, knife, locker

    Але для відновлення/імпорту підтримуємо випадки, коли хедери інші (case/назви).
    """
    if not isinstance(row, dict):
        row = {}

    # case-insensitive mapping
    norm = {safe_lower(k): (row.get(k) if k is not None else "") for k in row.keys()}

    def pick(*keys, default=""):
        for k in keys:
            if k in norm and norm[k] not in (None, ""):
                return norm[k]
        return default

    address = pick("address", "адреса", default=row.get("Address", ""))
    surname = pick("surname", "прізвище", "фио", "fio", default=row.get("surname", ""))
    knife = pick("knife", "ніж", "нож", default=row.get("knife", ""))
    locker = pick("locker", "шафка", "шкафчик", "шкаф", default=row.get("locker", ""))

    return {
        "Address": normalize_text(address),
        "surname": normalize_text(surname),
        "knife": normalize_text(knife),
        "locker": normalize_text(locker),
    }

def read_local_db(force: bool = False):
    now = time.time()
    if (not force) and _db_cache["rows"] and (now - _db_cache["time"] < CACHE_TTL):
        return _db_cache["rows"]

    rows = []
    if os.path.exists(LOCAL_DB_PATH):
        with open(LOCAL_DB_PATH, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(ensure_columns(r))
    else:
        write_local_db([])

    _db_cache["rows"] = rows
    _db_cache["time"] = now
    return rows

def write_local_db(rows):
    with open(LOCAL_DB_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Address", "surname", "knife", "locker"])
        writer.writeheader()
        for r in rows:
            writer.writerow(ensure_columns(r))
    _db_cache["rows"] = rows
    _db_cache["time"] = time.time()

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Обери дію 👇"):
    await update.message.reply_text(text, reply_markup=MAIN_KB)

# ==============================
# 💾 BACKUP
# ==============================

def make_backup_file(reason: str) -> str:
    filename = f"backup_{now_ts()}_{reason}.csv"
    path = os.path.join(BACKUP_DIR, filename)
    # якщо бази ще нема — створимо
    if not os.path.exists(LOCAL_DB_PATH):
        write_local_db([])
    shutil.copyfile(LOCAL_DB_PATH, path)
    return path

async def send_backup_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, file_path: str, caption: str):
    with open(file_path, "rb") as f:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=os.path.basename(file_path),
            caption=caption
        )

async def backup_everywhere(context: ContextTypes.DEFAULT_TYPE, trigger_chat_id: int, reason: str, caption_extra: str = "") -> str:
    path = make_backup_file(reason=reason)
    caption = f"💾 Backup бази • {reason}\n{os.path.basename(path)}"
    if caption_extra:
        caption += f"\n{caption_extra}"

    if BACKUP_CHAT_ID:
        try:
            await send_backup_to_chat(context, BACKUP_CHAT_ID, path, caption)
        except Exception as e:
            await context.bot.send_message(
                chat_id=trigger_chat_id,
                text=f"⚠️ Backup у групу не відправився (BACKUP_CHAT_ID). Помилка: {e}"
            )

    return path

# ==============================
# 🌱 SEED
# ==============================

def fetch_google_csv_rows():
    resp = requests.get(CSV_URL, timeout=20)
    resp.encoding = "utf-8"
    content = resp.text
    reader = csv.DictReader(StringIO(content))
    rows = [ensure_columns(r) for r in reader]
    return [r for r in rows if r["surname"]]

# ==============================
# 📊 LISTS + STATS
# ==============================

def format_all(rows):
    names = [r["surname"] for r in rows if r["surname"]]
    names_sorted = sorted(names, key=lambda x: safe_lower(x))
    return "👥 Всі:\n\n" + ("\n".join(names_sorted) if names_sorted else "Немає даних")

def format_with_locker(rows):
    out = []
    for r in rows:
        if r["surname"] and locker_has_value(r["locker"]):
            out.append(f"{r['surname']} — {r['locker']}")
    out = sorted(out, key=lambda x: safe_lower(x))
    return "🗄️ З шафкою:\n\n" + ("\n".join(out) if out else "Немає даних")

def format_no_locker(rows):
    out = []
    for r in rows:
        if r["surname"] and (not locker_has_value(r["locker"])):
            out.append(r["surname"])
    out = sorted(out, key=lambda x: safe_lower(x))
    return "⛔ Без шафки:\n\n" + ("\n".join(out) if out else "Немає даних")

def format_with_knife(rows):
    out = []
    for r in rows:
        if r["surname"] and knife_has(r["knife"]):
            out.append(r["surname"])
    out = sorted(out, key=lambda x: safe_lower(x))
    return "🔪 З ножем:\n\n" + ("\n".join(out) if out else "Немає даних")

def format_no_knife(rows):
    out = []
    for r in rows:
        if r["surname"] and (not knife_has(r["knife"])):  # 0 або пусто = без ножа
            out.append(r["surname"])
    out = sorted(out, key=lambda x: safe_lower(x))
    return "🚫 Без ножа:\n\n" + ("\n".join(out) if out else "Немає даних")

def format_stats(rows):
    only = [r for r in rows if r["surname"]]
    total = len(only)
    with_locker = len([r for r in only if locker_has_value(r["locker"])])
    no_locker = len([r for r in only if not locker_has_value(r["locker"])])
    with_knife = len([r for r in only if knife_has(r["knife"])])       # 1/2
    no_knife = len([r for r in only if not knife_has(r["knife"])])     # 0/пусто
    return (
        "📊 Статистика:\n\n"
        f"Всього: {total}\n"
        f"🗄️ З шафкою: {with_locker}\n"
        f"⛔ Без шафки: {no_locker}\n"
        f"🔪 З ножем: {with_knife}\n"
        f"🚫 Без ножа: {no_knife}"
    )

# ==============================
# 🧾 FLOWS
# ==============================

STATE = {"mode": None, "tmp": {}}

def reset_state():
    STATE["mode"] = None
    STATE["tmp"] = {}

def is_btn(text: str, keyword: str) -> bool:
    """
    Робимо кнопки "невбиваними":
    якщо Telegram/айфон підставив інші символи — все одно впізнаємо.
    """
    t = safe_lower(text)
    k = safe_lower(keyword)
    return (t == k) or (k in t)

# ---------- /start ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state()
    await show_main_menu(update, context, "Готово ✅")

# ---------- /chatid ----------
async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id = {update.effective_chat.id}")

# ---------- Text handler ----------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize_text(update.message.text)

    # якщо чекаємо файл для restore
    if STATE["mode"] == "restore_wait_file":
        await update.message.reply_text("❗️Надішли CSV файлом (документом).")
        return

    # flow modes
    if STATE["mode"] in {
        "add_wait_surname", "add_wait_locker", "add_wait_knife",
        "edit_wait_target", "edit_wait_new_surname", "edit_wait_new_locker", "edit_wait_new_knife",
        "delete_wait_target"
    }:
        await flow_handler(update, context, text)
        return

    rows = read_local_db()

    # кнопки (робимо через contains)
    if is_btn(text, "Статистика"):
        await update.message.reply_text(format_stats(rows), reply_markup=MAIN_KB)
        return
    if is_btn(text, "Всі"):
        await update.message.reply_text(format_all(rows), reply_markup=MAIN_KB)
        return
    if is_btn(text, "З шафкою"):
        await update.message.reply_text(format_with_locker(rows), reply_markup=MAIN_KB)
        return
    if is_btn(text, "Без шафки"):
        await update.message.reply_text(format_no_locker(rows), reply_markup=MAIN_KB)
        return
    if is_btn(text, "З ножем"):
        await update.message.reply_text(format_with_knife(rows), reply_markup=MAIN_KB)
        return
    if is_btn(text, "Без ножа"):
        await update.message.reply_text(format_no_knife(rows), reply_markup=MAIN_KB)
        return

    if is_btn(text, "Backup"):
        path = await backup_everywhere(context, update.effective_chat.id, reason="manual")
        await update.message.reply_text(f"💾 Backup зроблено: {os.path.basename(path)}", reply_markup=MAIN_KB)
        return

    if is_btn(text, "Seed"):
        if os.path.exists(LOCAL_DB_PATH):
            await backup_everywhere(context, update.effective_chat.id, reason="pre_seed")

        rows2 = fetch_google_csv_rows()
        write_local_db(rows2)

        await backup_everywhere(context, update.effective_chat.id, reason="after_seed")
        await show_main_menu(update, context, f"🧬 Seed завершено ✅\nЗаписів: {len(rows2)}")
        return

    # ✅ ВІДНОВЛЕННЯ — головний фікс
    if is_btn(text, "Відновити"):
        STATE["mode"] = "restore_wait_file"
        STATE["tmp"] = {}
        await update.message.reply_text("♻️ Надішли CSV файлом (документом) — я відновлю базу.")
        return

    if is_btn(text, "Додати працівника"):
        STATE["mode"] = "add_wait_surname"
        STATE["tmp"] = {}
        await update.message.reply_text("➕ Введи прізвище та ім'я працівника:")
        return

    if is_btn(text, "Редагувати працівника"):
        STATE["mode"] = "edit_wait_target"
        STATE["tmp"] = {}
        await update.message.reply_text("✏️ Введи прізвище працівника (точно як у списку):")
        return

    if is_btn(text, "Видалити працівника"):
        STATE["mode"] = "delete_wait_target"
        STATE["tmp"] = {}
        await update.message.reply_text("🗑️ Введи прізвище працівника (точно як у списку):")
        return

    await show_main_menu(update, context)

# ---------- Flow handler ----------
async def flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    rows = read_local_db()

    # ADD
    if STATE["mode"] == "add_wait_surname":
        if not text:
            await update.message.reply_text("Введи прізвище (не порожнє).")
            return
        STATE["tmp"]["surname"] = text
        STATE["mode"] = "add_wait_locker"
        await update.message.reply_text("Введи номер шафки (або '-' якщо немає):")
        return

    if STATE["mode"] == "add_wait_locker":
        STATE["tmp"]["locker"] = text
        STATE["mode"] = "add_wait_knife"
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("0")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text("Ніж: 1 або 2 = є, 0 = немає", reply_markup=kb)
        return

    if STATE["mode"] == "add_wait_knife":
        knife_val = text.strip()
        if knife_val not in {"0", "1", "2"}:
            await update.message.reply_text("Введи 1 або 2 або 0.")
            return

        new_row = {
            "Address": "",
            "surname": STATE["tmp"].get("surname", ""),
            "knife": knife_val,
            "locker": STATE["tmp"].get("locker", ""),
        }
        rows.append(ensure_columns(new_row))
        write_local_db(rows)

        await backup_everywhere(context, update.effective_chat.id, reason="add", caption_extra=f"Додано: {new_row['surname']}")
        reset_state()
        await show_main_menu(update, context, f"✅ Додано: {new_row['surname']}")
        return

    # EDIT
    if STATE["mode"] == "edit_wait_target":
        target = text
        matches = [i for i, r in enumerate(rows) if r["surname"] == target]
        if not matches:
            reset_state()
            await show_main_menu(update, context, "❌ Не знайдено працівника.")
            return
        STATE["tmp"]["idx"] = matches[0]
        STATE["mode"] = "edit_wait_new_surname"
        await update.message.reply_text("Нове прізвище (або '-' щоб не змінювати):")
        return

    if STATE["mode"] == "edit_wait_new_surname":
        if text != "-":
            rows[STATE["tmp"]["idx"]]["surname"] = text
        STATE["mode"] = "edit_wait_new_locker"
        await update.message.reply_text("Нова шафка (або '-' щоб не змінювати):")
        return

    if STATE["mode"] == "edit_wait_new_locker":
        if text != "-":
            rows[STATE["tmp"]["idx"]]["locker"] = text
        STATE["mode"] = "edit_wait_new_knife"
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("0"), KeyboardButton("-")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text("Ніж: 1/2/0 або '-' щоб не змінювати", reply_markup=kb)
        return

    if STATE["mode"] == "edit_wait_new_knife":
        if text != "-":
            if text not in {"0", "1", "2"}:
                await update.message.reply_text("Введи 1 або 2 або 0 або '-'.")
                return
            rows[STATE["tmp"]["idx"]]["knife"] = text

        write_local_db(rows)
        await backup_everywhere(context, update.effective_chat.id, reason="edit", caption_extra=f"Редаговано: {rows[STATE['tmp']['idx']]['surname']}")
        reset_state()
        await show_main_menu(update, context, "✅ Зміни збережено.")
        return

    # DELETE
    if STATE["mode"] == "delete_wait_target":
        target = text
        idxs = [i for i, r in enumerate(rows) if r["surname"] == target]
        if not idxs:
            reset_state()
            await show_main_menu(update, context, "❌ Не знайдено працівника.")
            return

        deleted = rows.pop(idxs[0])
        write_local_db(rows)

        await backup_everywhere(context, update.effective_chat.id, reason="delete", caption_extra=f"Видалено: {deleted['surname']}")
        reset_state()
        await show_main_menu(update, context, f"🗑️ Видалено: {deleted['surname']}")
        return

    reset_state()
    await show_main_menu(update, context)

# ---------- Document handler (RESTORE) ----------
async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if STATE["mode"] != "restore_wait_file":
        await update.message.reply_text("Я отримав файл, але зараз не в режимі відновлення. Натисни ♻️ Відновити з файлу.")
        return

    doc: Document = update.message.document
    if not (doc.file_name or "").lower().endswith(".csv"):
        await update.message.reply_text("❌ Потрібен CSV файл.")
        return

    # pre-restore backup
    if os.path.exists(LOCAL_DB_PATH):
        await backup_everywhere(context, update.effective_chat.id, reason="pre_restore")

    file = await doc.get_file()
    content = await file.download_as_bytearray()
    text = content.decode("utf-8", errors="replace")

    reader = csv.DictReader(StringIO(text))
    rows = [ensure_columns(r) for r in reader]
    rows = [r for r in rows if r["surname"]]

    write_local_db(rows)
    await backup_everywhere(context, update.effective_chat.id, reason="after_restore", caption_extra=f"Записів: {len(rows)}")

    reset_state()
    await show_main_menu(update, context, f"♻️ Відновлено ✅\nЗаписів: {len(rows)}")

# ==============================
# 🚀 MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("chatid", cmd_chatid))

    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
