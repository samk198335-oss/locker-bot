import os
import csv
import time
import threading
import requests
from io import StringIO
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Dict, Optional

from telegram import Update, ReplyKeyboardMarkup
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

BOT_TOKEN = os.getenv("BOT_TOKEN")

# стартове джерело (для /seed)
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# локальна база (на Render Free стирається після deploy)
LOCAL_DB = "local_data.csv"

# сюди (опціонально) зберігається file_id останнього backup (для поточної сесії)
LAST_BACKUP_CACHE_FILE = "last_backup_file_id.txt"

# Якщо задано в Render Env -> дозволяє "автоматично" відновити після deploy
# (бо env не стирається)
LAST_BACKUP_ENV = "LAST_BACKUP_FILE_ID"

# ==============================
# 🧩 HELPERS
# ==============================

REQUIRED_COLUMNS = {"Address", "surname", "knife", "locker"}

def normalize(s: str) -> str:
    return (s or "").strip()

def norm_lower(s: str) -> str:
    return normalize(s).lower()

def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def ensure_db_exists_with_header() -> None:
    if not os.path.exists(LOCAL_DB) or os.path.getsize(LOCAL_DB) == 0:
        with open(LOCAL_DB, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Address", "surname", "knife", "locker"])
            w.writeheader()

def is_db_empty() -> bool:
    if not os.path.exists(LOCAL_DB) or os.path.getsize(LOCAL_DB) == 0:
        return True
    try:
        with open(LOCAL_DB, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return len([r for r in rows if normalize(r.get("surname"))]) == 0
    except Exception:
        return True

def read_db() -> List[Dict]:
    ensure_db_exists_with_header()
    with open(LOCAL_DB, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_db(rows: List[Dict]) -> None:
    ensure_db_exists_with_header()
    with open(LOCAL_DB, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Address", "surname", "knife", "locker"])
        w.writeheader()
        for r in rows:
            w.writerow({
                "Address": normalize(r.get("Address")),
                "surname": normalize(r.get("surname")),
                "knife": normalize(r.get("knife")),
                "locker": normalize(r.get("locker")),
            })

def validate_csv_file(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fns = [normalize(x) for x in (r.fieldnames or [])]
    if not REQUIRED_COLUMNS.issubset(set(fns)):
        raise ValueError("CSV має містити колонки: Address, surname, knife, locker. Зараз: " + str(fns))

def parse_knife(value: str) -> Optional[int]:
    v = norm_lower(value)
    if v in {"1", "yes", "+", "так", "є", "true"}:
        return 1
    if v in {"0", "no", "-", "ні", "нема", "false"}:
        return 0
    return None

def has_locker(value: str) -> bool:
    v = norm_lower(value)
    if v == "" or v in {"0", "no", "ні", "нема", "none"}:
        return False
    return True

def stats_text(rows: List[Dict]) -> str:
    total = 0
    knife_yes = 0
    knife_no = 0
    knife_unknown = 0
    locker_yes = 0
    locker_no = 0

    for r in rows:
        name = normalize(r.get("surname"))
        if not name:
            continue
        total += 1

        k = parse_knife(r.get("knife"))
        if k == 1:
            knife_yes += 1
        elif k == 0:
            knife_no += 1
        else:
            knife_unknown += 1

        if has_locker(r.get("locker")):
            locker_yes += 1
        else:
            locker_no += 1

    return (
        "📊 Статистика:\n"
        f"Всього: {total}\n\n"
        "🔪 Ніж:\n"
        f"  ✅ Є: {knife_yes}\n"
        f"  🚫 Нема: {knife_no}\n"
        f"  ❔ Невідомо: {knife_unknown}\n\n"
        "🗄 Шафка:\n"
        f"  ✅ Є: {locker_yes}\n"
        f"  🚫 Нема: {locker_no}"
    )

def format_people(rows: List[Dict]) -> str:
    names = [normalize(r.get("surname")) for r in rows if normalize(r.get("surname"))]
    names = sorted(names, key=lambda x: x.lower())
    return "\n".join(names) if names else "Немає даних."

def format_locker_list(rows: List[Dict], with_locker: bool) -> str:
    items: List[str] = []
    for r in rows:
        name = normalize(r.get("surname"))
        locker = normalize(r.get("locker"))
        if not name:
            continue
        if with_locker:
            if has_locker(locker):
                items.append(f"{name} — 🗄 {locker}")
        else:
            if not has_locker(locker):
                items.append(name)
    items = sorted(items, key=lambda x: x.lower())
    return "\n".join(items) if items else "Немає даних."

def make_backup_file() -> str:
    ensure_db_exists_with_header()
    fname = f"base_data_{now_stamp()}.csv"
    with open(LOCAL_DB, "r", encoding="utf-8") as src, open(fname, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    return fname

def load_last_backup_file_id() -> Optional[str]:
    # 1) env (працює після deploy)
    env_val = normalize(os.getenv(LAST_BACKUP_ENV, ""))
    if env_val:
        return env_val

    # 2) локальний кеш (працює тільки в межах поточної сесії)
    try:
        if os.path.exists(LAST_BACKUP_CACHE_FILE):
            with open(LAST_BACKUP_CACHE_FILE, "r", encoding="utf-8") as f:
                v = normalize(f.read())
                return v if v else None
    except Exception:
        pass
    return None

def save_last_backup_file_id(file_id: str) -> None:
    try:
        with open(LAST_BACKUP_CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(file_id)
    except Exception:
        pass

# ==============================
# 🧠 UX STATE (restore wait is non-blocking)
# ==============================

def set_restore_wait(ctx: ContextTypes.DEFAULT_TYPE, on: bool) -> None:
    ctx.user_data["restore_wait"] = bool(on)

def is_restore_wait(ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(ctx.user_data.get("restore_wait"))

def clear_restore_wait(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("restore_wait", None)

def db_hint_prefix() -> str:
    return "⚠️ База порожня (після deploy на Render Free це нормально — файли стираються).\n\n"

# ==============================
# 🎛 Keyboards
# ==============================

def main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        ["📊 Статистика", "👥 Всі"],
        ["🔪 Є ніж", "🚫 Нема ножа"],
        ["🗄 Є шафка", "🚫 Нема шафки"],
        ["➕ Додати працівника", "✏️ Редагувати"],
        ["❌ Видалити", "💾 Backup"],
        ["♻️ Відновити з файлу", "⚡️ Оновити БД (ост. backup)"],
        ["🚑 /seed"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def recovery_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        ["🟢 Продовжити роботу"],
        ["⚡️ Оновити БД (ост. backup)", "♻️ Відновити з файлу"],
        ["🚑 /seed", "💾 Backup"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def restore_wait_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        ["⛔️ Скасувати відновлення", "🟢 Продовжити роботу"],
        ["⚡️ Оновити БД (ост. backup)", "🚑 /seed"],
        ["💾 Backup"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def flow_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["⛔️ Скасувати"]], resize_keyboard=True)

# ==============================
# 📌 COMMANDS
# ==============================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_db_empty():
        text = (
            db_hint_prefix() +
            "Можеш працювати одразу або відновити базу:\n"
            "🟢 Продовжити роботу — без відновлення\n"
            "⚡️ Оновити БД (ост. backup) — автоматично (якщо задано LAST_BACKUP_FILE_ID)\n"
            "♻️ Відновити з файлу — надіслати CSV як ДОКУМЕНТ\n"
            "🚑 /seed — підтягнути стартову базу з Google (тільки якщо база пуста)\n"
        )
        await update.message.reply_text(text, reply_markup=recovery_keyboard())
    else:
        await update.message.reply_text("Готово ✅ Обирай дію 👇", reply_markup=main_keyboard())

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    text = stats_text(rows)
    if is_db_empty():
        text = db_hint_prefix() + text
        await update.message.reply_text(text, reply_markup=recovery_keyboard())
    else:
        await update.message.reply_text(text, reply_markup=main_keyboard())

async def cmd_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_db_empty():
        await update.message.reply_text("ℹ️ База не пуста — /seed не потрібен.", reply_markup=main_keyboard())
        return

    try:
        resp = requests.get(CSV_URL, timeout=15)
        resp.encoding = "utf-8"
        reader = csv.DictReader(StringIO(resp.text))

        rows: List[Dict] = []
        for r in reader:
            rows.append({
                "Address": normalize(r.get("Address")),
                "surname": normalize(r.get("surname")),
                "knife": normalize(r.get("knife")),
                "locker": normalize(r.get("locker")),
            })

        write_db(rows)
        clear_restore_wait(context)
        await update.message.reply_text("✅ /seed виконано. База відновлена з Google.", reply_markup=main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ /seed помилка: {e}", reply_markup=recovery_keyboard())

async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    txt = "👥 Всі:\n\n" + format_people(rows)
    if is_db_empty():
        txt = db_hint_prefix() + txt
        await update.message.reply_text(txt, reply_markup=recovery_keyboard())
    else:
        await update.message.reply_text(txt, reply_markup=main_keyboard())

async def cmd_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    names = []
    for r in rows:
        name = normalize(r.get("surname"))
        if name and parse_knife(r.get("knife")) == 1:
            names.append(name)
    names = sorted(names, key=lambda x: x.lower())
    txt = "🔪 Є ніж:\n\n" + ("\n".join(names) if names else "Немає даних.")
    if is_db_empty():
        txt = db_hint_prefix() + txt
        await update.message.reply_text(txt, reply_markup=recovery_keyboard())
    else:
        await update.message.reply_text(txt, reply_markup=main_keyboard())

async def cmd_no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    names = []
    for r in rows:
        name = normalize(r.get("surname"))
        if name and parse_knife(r.get("knife")) == 0:
            names.append(name)
    names = sorted(names, key=lambda x: x.lower())
    txt = "🚫 Нема ножа:\n\n" + ("\n".join(names) if names else "Немає даних.")
    if is_db_empty():
        txt = db_hint_prefix() + txt
        await update.message.reply_text(txt, reply_markup=recovery_keyboard())
    else:
        await update.message.reply_text(txt, reply_markup=main_keyboard())

async def cmd_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    txt = "🗄 Є шафка:\n\n" + format_locker_list(rows, with_locker=True)
    if is_db_empty():
        txt = db_hint_prefix() + txt
        await update.message.reply_text(txt, reply_markup=recovery_keyboard())
    else:
        await update.message.reply_text(txt, reply_markup=main_keyboard())

async def cmd_no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    txt = "🚫 Нема шафки:\n\n" + format_locker_list(rows, with_locker=False)
    if is_db_empty():
        txt = db_hint_prefix() + txt
        await update.message.reply_text(txt, reply_markup=recovery_keyboard())
    else:
        await update.message.reply_text(txt, reply_markup=main_keyboard())

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fname = make_backup_file()
        msg = await update.message.reply_document(
            document=open(fname, "rb"),
            filename=fname,
            caption="💾 Backup бази"
        )

        # Спроба дістати file_id документа, який Telegram зберігає
        try:
            if msg and msg.document and msg.document.file_id:
                file_id = msg.document.file_id
                save_last_backup_file_id(file_id)

                await update.message.reply_text(
                    "✅ Backup збережено.\n\n"
                    "Щоб кнопка ⚡️ Оновити БД (ост. backup) працювала АВТОМАТИЧНО після deploy:\n"
                    f"1) Скопіюй це значення file_id:\n{file_id}\n"
                    f"2) Render → Service → Environment → додай змінну:\n{LAST_BACKUP_ENV} = (file_id)\n"
                    "3) Збережи і зроби deploy.\n\n"
                    "Після цього відновлення буде одним натиском кнопки.",
                    reply_markup=(main_keyboard() if not is_db_empty() else recovery_keyboard())
                )
        except Exception:
            pass

    except Exception as e:
        await update.message.reply_text(f"❌ Backup помилка: {e}")

# ==============================
# ♻️ Restore UX (non-blocking)
# ==============================

async def ask_restore_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_restore_wait(context, True)
    await update.message.reply_text(
        "♻️ Відновлення активне.\n"
        "Надішли CSV-файл бази (base_data_*.csv) як ДОКУМЕНТ — я перезапишу базу.\n\n"
        "⛔️ Скасувати — кнопка нижче.\n"
        "Команди бота НЕ блокуються.",
        reply_markup=restore_wait_keyboard()
    )

async def cancel_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_restore_wait(context)
    await update.message.reply_text(
        "✅ Відновлення скасовано.",
        reply_markup=(main_keyboard() if not is_db_empty() else recovery_keyboard())
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_restore_wait(context):
        await update.message.reply_text("Файл отримано, але режим відновлення не активний. Натисни ♻️ Відновити з файлу.")
        return

    doc = update.message.document
    if not doc:
        return

    try:
        ensure_db_exists_with_header()
        file = await doc.get_file()
        await file.download_to_drive(custom_path=LOCAL_DB)

        validate_csv_file(LOCAL_DB)

        clear_restore_wait(context)
        await update.message.reply_text("✅ Базу відновлено з файлу. Можна працювати 👇", reply_markup=main_keyboard())
    except Exception as e:
        await update.message.reply_text(
            f"❌ Помилка відновлення: {e}\nСпробуй надіслати CSV ще раз як ДОКУМЕНТ.",
            reply_markup=restore_wait_keyboard()
        )

# ==============================
# ⚡️ Auto restore from last backup file_id
# ==============================

async def auto_restore_last_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_db_empty():
        await update.message.reply_text("ℹ️ База не пуста — авто-відновлення не потрібне.", reply_markup=main_keyboard())
        return

    file_id = load_last_backup_file_id()
    if not file_id:
        await update.message.reply_text(
            "⚠️ Немає LAST_BACKUP_FILE_ID для автоматичного відновлення.\n\n"
            "Зроби так:\n"
            "1) Натисни 💾 Backup (коли база не пуста) — бот дасть file_id\n"
            f"2) Render → Environment додай змінну {LAST_BACKUP_ENV}\n"
            "3) Після наступного deploy кнопка ⚡️ буде відновлювати БД автоматично.\n\n"
            "А поки що можеш:\n"
            "♻️ Відновити з файлу (надіслати CSV як ДОКУМЕНТ)\n"
            "або 🚑 /seed",
            reply_markup=recovery_keyboard()
        )
        return

    try:
        tg_file = await context.bot.get_file(file_id)
        ensure_db_exists_with_header()
        await tg_file.download_to_drive(custom_path=LOCAL_DB)

        validate_csv_file(LOCAL_DB)

        clear_restore_wait(context)
        await update.message.reply_text("✅ Авто-відновлення виконано з останнього backup. Можна працювати 👇", reply_markup=main_keyboard())
    except Exception as e:
        await update.message.reply_text(
            "❌ Не вдалось авто-відновити з backup.\n"
            f"Причина: {e}\n\n"
            "Спробуй:\n"
            "1) ♻️ Відновити з файлу (надіслати CSV як ДОКУМЕНТ)\n"
            "2) або 🚑 /seed",
            reply_markup=recovery_keyboard()
        )

# ==============================
# ➕ / ✏️ / ❌ Simple flows (basic, but usable)
# ==============================

def find_by_surname(rows: List[Dict], surname: str) -> Optional[int]:
    s = norm_lower(surname)
    for idx, r in enumerate(rows):
        if norm_lower(r.get("surname")) == s:
            return idx
    return None

async def flow_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("flow", None)
    context.user_data.pop("step", None)
    context.user_data.pop("tmp", None)
    await update.message.reply_text(
        "Скасовано ✅",
        reply_markup=(main_keyboard() if not is_db_empty() else recovery_keyboard())
    )

async def add_worker_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["flow"] = "add"
    context.user_data["step"] = "surname"
    context.user_data["tmp"] = {}
    await update.message.reply_text("➕ Додати працівника\nВведи Прізвище та імʼя:", reply_markup=flow_cancel_keyboard())

async def edit_worker_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["flow"] = "edit"
    context.user_data["step"] = "who"
    context.user_data["tmp"] = {}
    await update.message.reply_text("✏️ Редагувати\nВведи ПРІЗВИЩЕ (точно як у базі), кого редагувати:", reply_markup=flow_cancel_keyboard())

async def delete_worker_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["flow"] = "delete"
    context.user_data["step"] = "who"
    context.user_data["tmp"] = {}
    await update.message.reply_text("❌ Видалити\nВведи ПРІЗВИЩЕ (точно як у базі), кого видалити:", reply_markup=flow_cancel_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = normalize(update.message.text)

    # Global buttons (work always, even if restore_wait)
    if text == "📊 Статистика":
        return await cmd_stats(update, context)
    if text == "👥 Всі":
        return await cmd_all(update, context)
    if text == "🔪 Є ніж":
        return await cmd_knife_list(update, context)
    if text == "🚫 Нема ножа":
        return await cmd_no_knife_list(update, context)
    if text == "🗄 Є шафка":
        return await cmd_locker_list(update, context)
    if text == "🚫 Нема шафки":
        return await cmd_no_locker_list(update, context)
    if text == "💾 Backup":
        return await cmd_backup(update, context)
    if text == "♻️ Відновити з файлу":
        return await ask_restore_file(update, context)
    if text == "⛔️ Скасувати відновлення":
        return await cancel_restore(update, context)
    if text == "⚡️ Оновити БД (ост. backup)":
        return await auto_restore_last_backup(update, context)
    if text == "🟢 Продовжити роботу":
        await update.message.reply_text(
            "Ок ✅ Можеш працювати. Якщо треба — відновлення доступне з меню.",
            reply_markup=(main_keyboard() if not is_db_empty() else recovery_keyboard())
        )
        return
    if text == "➕ Додати працівника":
        return await add_worker_start(update, context)
    if text == "✏️ Редагувати":
        return await edit_worker_start(update, context)
    if text == "❌ Видалити":
        return await delete_worker_start(update, context)
    if text == "⛔️ Скасувати":
        return await flow_cancel(update, context)

    # If user is in restore wait, do not block; just remind
    if is_restore_wait(context) and not context.user_data.get("flow"):
        await update.message.reply_text(
            "ℹ️ Відновлення активне: можеш надіслати CSV як ДОКУМЕНТ.\n"
            "Або натисни ⛔️ Скасувати відновлення.\n"
            "Або ⚡️ Оновити БД (ост. backup), якщо налаштовано.",
            reply_markup=restore_wait_keyboard()
        )
        return

    # Flows
    flow = context.user_data.get("flow")
    step = context.user_data.get("step")
    tmp = context.user_data.get("tmp", {})

    if flow == "add":
        if step == "surname":
            tmp["surname"] = text
            context.user_data["step"] = "locker"
            await update.message.reply_text("Введи номер шафки (або напиши: нема):", reply_markup=flow_cancel_keyboard())
            return
        if step == "locker":
            tmp["locker"] = text
            context.user_data["step"] = "knife"
            await update.message.reply_text("Ніж? Напиши: 1 (є) або 0 (нема) або порожньо:", reply_markup=flow_cancel_keyboard())
            return
        if step == "knife":
            tmp["knife"] = text
            rows = read_db()
            rows.append({
                "Address": "",
                "surname": tmp.get("surname", ""),
                "knife": tmp.get("knife", ""),
                "locker": tmp.get("locker", ""),
            })
            write_db(rows)

            # авто-вихід (база вже не пуста)
            context.user_data.pop("flow", None)
            context.user_data.pop("step", None)
            context.user_data.pop("tmp", None)

            await update.message.reply_text("✅ Працівника додано.", reply_markup=main_keyboard())
            return

    if flow == "edit":
        rows = read_db()
        if step == "who":
            idx = find_by_surname(rows, text)
            if idx is None:
                await update.message.reply_text("Не знайшов. Введи прізвище точно як у списку, або ⛔️ Скасувати.", reply_markup=flow_cancel_keyboard())
                return
            tmp["idx"] = idx
            context.user_data["step"] = "new_surname"
            await update.message.reply_text("Введи НОВЕ прізвище та імʼя (або '-' щоб не змінювати):", reply_markup=flow_cancel_keyboard())
            return

        if step == "new_surname":
            tmp["new_surname"] = text
            context.user_data["step"] = "new_locker"
            await update.message.reply_text("Введи НОВУ шафку (або '-' щоб не змінювати):", reply_markup=flow_cancel_keyboard())
            return

        if step == "new_locker":
            idx = tmp.get("idx")
            if idx is None or idx >= len(rows):
                await update.message.reply_text("❌ Помилка стану редагування. Почни знову.", reply_markup=main_keyboard())
                return

            if tmp.get("new_surname") and tmp["new_surname"] != "-":
                rows[idx]["surname"] = tmp["new_surname"]
            if text and text != "-":
                rows[idx]["locker"] = text

            write_db(rows)

            context.user_data.pop("flow", None)
            context.user_data.pop("step", None)
            context.user_data.pop("tmp", None)

            await update.message.reply_text("✅ Оновлено.", reply_markup=main_keyboard())
            return

    if flow == "delete":
        rows = read_db()
        if step == "who":
            idx = find_by_surname(rows, text)
            if idx is None:
                await update.message.reply_text("Не знайшов. Введи прізвище точно як у списку, або ⛔️ Скасувати.", reply_markup=flow_cancel_keyboard())
                return
            removed = rows.pop(idx)
            write_db(rows)

            context.user_data.pop("flow", None)
            context.user_data.pop("step", None)
            context.user_data.pop("tmp", None)

            await update.message.reply_text(f"✅ Видалено: {normalize(removed.get('surname'))}", reply_markup=main_keyboard())
            return

    await update.message.reply_text(
        "Не зрозумів. Натисни /start або кнопки меню.",
        reply_markup=(main_keyboard() if not is_db_empty() else recovery_keyboard())
    )

# ==============================
# 🚀 MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    ensure_db_exists_with_header()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("seed", cmd_seed))

    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
