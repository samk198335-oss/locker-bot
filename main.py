import os
import csv
import re
import shutil
import threading
from datetime import datetime, timedelta
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, Document, InputFile
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

# New data files
SHIFTS_DB_PATH = os.getenv("SHIFTS_DB_PATH", "shifts.csv").strip()
PERF_DB_PATH = os.getenv("PERF_DB_PATH", "performance.csv").strip()

BACKUP_CHAT_ID_RAW = os.getenv("BACKUP_CHAT_ID", "").strip()
BACKUP_CHAT_ID = int(BACKUP_CHAT_ID_RAW) if BACKUP_CHAT_ID_RAW else None

BACKUP_DIR = os.getenv("BACKUP_DIR", "backups").strip()
os.makedirs(BACKUP_DIR, exist_ok=True)

WRITE_LOCK = threading.Lock()

# mtime caches
_db_cache = {"mtime": None, "rows": []}
_shifts_cache = {"mtime": None, "rows": []}
_perf_cache = {"mtime": None, "rows": []}

# ==============================
# 🧩 UI: MENUS
# ==============================

BTN_EMPLOYEE_MENU = "👤 Працівник"
BTN_WORK_MENU = "🏭 Організація роботи"
BTN_BACKUP = "💾 Backup бази"
BTN_SEED = "🧬 Seed з Google"
BTN_RESTORE = "♻️ Відновити з файлу"

BTN_BACK = "⬅️ Назад"
BTN_CANCEL = "❌ Скасувати"

MAIN_KB = ReplyKeyboardMarkup(
    [
        [BTN_EMPLOYEE_MENU, BTN_WORK_MENU],
        [BTN_BACKUP, BTN_SEED],
        [BTN_RESTORE],
    ],
    resize_keyboard=True
)

# EMPLOYEE submenu (your existing)
BTN_STATS = "📊 Статистика"
BTN_ALL = "👥 Всі"
BTN_WITH_LOCKER = "🗄️ З шафкою"
BTN_NO_LOCKER = "⛔ Без шафки"
BTN_WITH_KNIFE = "🔪 З ножем"
BTN_NO_KNIFE = "🚫 Без ножа"
BTN_ADD = "➕ Додати працівника"
BTN_EDIT = "✏️ Редагувати працівника"
BTN_DELETE = "🗑️ Видалити працівника"

EMPLOYEE_KB = ReplyKeyboardMarkup(
    [
        [BTN_STATS, BTN_ALL],
        [BTN_WITH_LOCKER, BTN_NO_LOCKER],
        [BTN_WITH_KNIFE, BTN_NO_KNIFE],
        [BTN_ADD, BTN_EDIT],
        [BTN_DELETE],
        [BTN_BACK],
    ],
    resize_keyboard=True
)

# WORK submenu
BTN_SHIFT_CREATE = "➕ Створити зміну"
BTN_GROUP_ADD_WORKERS = "👥 Додати працівників у групу"
BTN_AUTO_DISTRIBUTE = "🤖 Авто-розподіл по HALA 1–4"
BTN_SHIFT_SHOW = "📋 Показати зміну"
BTN_GROUP_SET_PERCENT = "📈 Внести % групи"
BTN_SORT_WORKERS = "📌 Сортування працівників"
BTN_EXPORT_TXT = "📝 Експорт зміни в TXT"
BTN_SHIFT_BACKUP = "💾 Backup зміни"

WORK_KB = ReplyKeyboardMarkup(
    [
        [BTN_SHIFT_CREATE, BTN_SHIFT_SHOW],
        [BTN_GROUP_ADD_WORKERS, BTN_AUTO_DISTRIBUTE],
        [BTN_GROUP_SET_PERCENT, BTN_SORT_WORKERS],
        [BTN_EXPORT_TXT],
        [BTN_SHIFT_BACKUP],
        [BTN_BACK],
    ],
    resize_keyboard=True
)

# ==============================
# 🧠 HELPERS
# ==============================

def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def today_ddmmyyyy() -> str:
    return datetime.now().strftime("%d.%m.%Y")

def date_from_keyword(text: str) -> str | None:
    """
    Accepts quick calendar keywords/buttons and returns DD.MM.YYYY.
    Supported:
      - "-" (today)
      - "сьогодні", "today"
      - "завтра", "tomorrow"
      - "вчора", "yesterday"
      - "📅 <DD.MM.YYYY>" buttons
    """
    t = normalize_text(text)
    tl = safe_lower(t)
    if t == "-" or tl in {"сьогодні", "today", "📅 сьогодні"}:
        return today_ddmmyyyy()
    if tl in {"завтра", "tomorrow", "📅 завтра"}:
        return (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    if tl in {"вчора", "yesterday", "📅 вчора"}:
        return (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})", t)
    if m:
        return m.group(1)
    return None

def date_kb(days_forward: int = 7) -> ReplyKeyboardMarkup:
    """Simple 'calendar' keyboard: today + next N days."""
    base = datetime.now().date()
    buttons = [KeyboardButton(f"📅 {(base + timedelta(days=i)).strftime('%d.%m.%Y')}") for i in range(0, days_forward + 1)]
    rows = []
    # 2 per row to keep compact on iPhone
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i:i+2])
    rows.append([KeyboardButton(BTN_CANCEL)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def safe_lower(s: str) -> str:
    return normalize_text(s).lower()

def is_btn(text: str, keyword: str) -> bool:
    t = safe_lower(text)
    k = safe_lower(keyword)
    return (t == k) or (k in t)

def parse_ddmmyyyy(s: str):
    s = normalize_text(s)
    try:
        return datetime.strptime(s, "%d.%m.%Y")
    except Exception:
        return None

def parse_mmyyyy(s: str):
    s = normalize_text(s)
    try:
        return datetime.strptime("01." + s, "%d.%m.%Y")
    except Exception:
        return None

def month_key_from_date_str(date_str: str) -> str:
    dt = parse_ddmmyyyy(date_str)
    if not dt:
        return ""
    return dt.strftime("%m.%Y")

def emoji_by_percent(p: float) -> str:
    if p >= 100.0:
        return "🟢"
    if p >= 90.0:
        return "🟡"
    return "🔴"

def locker_has_value(v: str) -> bool:
    v = normalize_text(v)
    if not v:
        return False
    v_low = safe_lower(v)
    return v_low not in {"-", "—", "–", "нема", "нет", "ні", "no", "none"}

def knife_has(v: str) -> bool:
    v = normalize_text(v)
    return v in {"1", "2"}

def ensure_employee_columns(row: dict) -> dict:
    return {
        "Address": normalize_text(row.get("Address", "")),
        "surname": normalize_text(row.get("surname", "")),
        "knife": normalize_text(row.get("knife", "")),
        "locker": normalize_text(row.get("locker", "")),
    }

def ensure_shift_columns(row: dict) -> dict:
    return {
        "date": normalize_text(row.get("date", "")),
        "shift_type": normalize_text(row.get("shift_type", "")),  # day/night
        "hala": normalize_text(row.get("hala", "")),              # HALA 1..4
        "group": normalize_text(row.get("group", "")),            # G1...
        "surname": normalize_text(row.get("surname", "")),
    }

def ensure_perf_columns(row: dict) -> dict:
    return {
        "date": normalize_text(row.get("date", "")),
        "shift_type": normalize_text(row.get("shift_type", "")),
        "hala": normalize_text(row.get("hala", "")),
        "group": normalize_text(row.get("group", "")),
        "surname": normalize_text(row.get("surname", "")),
        "percent": normalize_text(row.get("percent", "")),
    }

def _file_mtime(path: str):
    try:
        return os.path.getmtime(path)
    except Exception:
        return None

def atomic_write_csv(path: str, fieldnames: list, rows: list):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    os.replace(tmp_path, path)

# ==============================
# 📁 DB: Employees
# ==============================

def read_local_db(force: bool = False):
    if not os.path.exists(LOCAL_DB_PATH):
        write_local_db([])
        return []

    mtime = _file_mtime(LOCAL_DB_PATH)
    if (not force) and _db_cache["mtime"] is not None and mtime == _db_cache["mtime"]:
        return _db_cache["rows"]

    rows = []
    with open(LOCAL_DB_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(ensure_employee_columns(r))

    _db_cache["rows"] = rows
    _db_cache["mtime"] = mtime
    return rows

def write_local_db(rows):
    with WRITE_LOCK:
        normalized = [ensure_employee_columns(r) for r in rows]
        atomic_write_csv(
            LOCAL_DB_PATH,
            fieldnames=["Address", "surname", "knife", "locker"],
            rows=normalized
        )
        _db_cache["rows"] = normalized
        _db_cache["mtime"] = _file_mtime(LOCAL_DB_PATH)

# ==============================
# 📁 DB: Shifts / Performance
# ==============================

def ensure_shifts_file():
    if os.path.exists(SHIFTS_DB_PATH):
        return
    with WRITE_LOCK:
        if os.path.exists(SHIFTS_DB_PATH):
            return
        atomic_write_csv(
            SHIFTS_DB_PATH,
            fieldnames=["date", "shift_type", "hala", "group", "surname"],
            rows=[]
        )

def ensure_perf_file():
    if os.path.exists(PERF_DB_PATH):
        return
    with WRITE_LOCK:
        if os.path.exists(PERF_DB_PATH):
            return
        atomic_write_csv(
            PERF_DB_PATH,
            fieldnames=["date", "shift_type", "hala", "group", "surname", "percent"],
            rows=[]
        )

def read_shifts_db(force: bool = False):
    ensure_shifts_file()
    mtime = _file_mtime(SHIFTS_DB_PATH)
    if (not force) and _shifts_cache["mtime"] is not None and mtime == _shifts_cache["mtime"]:
        return _shifts_cache["rows"]

    rows = []
    with open(SHIFTS_DB_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(ensure_shift_columns(r))

    _shifts_cache["rows"] = rows
    _shifts_cache["mtime"] = mtime
    return rows

def write_shifts_db(rows):
    ensure_shifts_file()
    with WRITE_LOCK:
        normalized = [ensure_shift_columns(r) for r in rows]
        atomic_write_csv(
            SHIFTS_DB_PATH,
            fieldnames=["date", "shift_type", "hala", "group", "surname"],
            rows=normalized
        )
        _shifts_cache["rows"] = normalized
        _shifts_cache["mtime"] = _file_mtime(SHIFTS_DB_PATH)

def read_perf_db(force: bool = False):
    ensure_perf_file()
    mtime = _file_mtime(PERF_DB_PATH)
    if (not force) and _perf_cache["mtime"] is not None and mtime == _perf_cache["mtime"]:
        return _perf_cache["rows"]

    rows = []
    with open(PERF_DB_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(ensure_perf_columns(r))

    _perf_cache["rows"] = rows
    _perf_cache["mtime"] = mtime
    return rows

def write_perf_db(rows):
    ensure_perf_file()
    with WRITE_LOCK:
        normalized = [ensure_perf_columns(r) for r in rows]
        atomic_write_csv(
            PERF_DB_PATH,
            fieldnames=["date", "shift_type", "hala", "group", "surname", "percent"],
            rows=normalized
        )
        _perf_cache["rows"] = normalized
        _perf_cache["mtime"] = _file_mtime(PERF_DB_PATH)

# ==============================
# UI helpers
# ==============================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Обери дію 👇"):
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def show_employee_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Меню: Працівник 👇"):
    await update.message.reply_text(text, reply_markup=EMPLOYEE_KB)

async def show_work_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "Меню: Організація роботи 👇"):
    await update.message.reply_text(text, reply_markup=WORK_KB)

def shift_type_label(st: str) -> str:
    return "нічна" if safe_lower(st) == "night" else "денна"

def normalize_shift_type(text: str) -> str:
    t = safe_lower(text)
    if t in {"night", "ніч", "нічна"}:
        return "night"
    if t in {"day", "день", "денна"}:
        return "day"
    return ""

def safe_float(s: str):
    s = normalize_text(s).replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None
        # ==============================
# 💾 BACKUP (all 3 db files)
# ==============================

def make_backup_files(reason: str) -> list:
    ts = now_ts()
    paths = []

    for p in [LOCAL_DB_PATH, SHIFTS_DB_PATH, PERF_DB_PATH]:
        if p == LOCAL_DB_PATH and not os.path.exists(LOCAL_DB_PATH):
            write_local_db([])
        if p == SHIFTS_DB_PATH:
            ensure_shifts_file()
        if p == PERF_DB_PATH:
            ensure_perf_file()

        base = os.path.basename(p)
        filename = f"backup_{ts}_{reason}__{base}"
        dst = os.path.join(BACKUP_DIR, filename)
        shutil.copyfile(p, dst)
        paths.append(dst)

    return paths

async def send_backup_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, file_path: str, caption: str):
    with open(file_path, "rb") as f:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=os.path.basename(file_path),
            caption=caption
        )

async def backup_everywhere(context: ContextTypes.DEFAULT_TYPE, trigger_chat_id: int, reason: str, caption_extra: str = "") -> list:
    paths = make_backup_files(reason=reason)
    for path in paths:
        caption = f"💾 Backup • {reason}\n{os.path.basename(path)}"
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
    return paths

# ==============================
# 🌱 SEED (employees only)
# ==============================

def fetch_google_csv_rows():
    resp = requests.get(CSV_URL, timeout=20)
    resp.encoding = "utf-8"
    content = resp.text
    reader = csv.DictReader(StringIO(content))
    rows = [ensure_employee_columns(r) for r in reader]
    return [r for r in rows if r["surname"]]

# ==============================
# 📊 EMPLOYEE LISTS
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
        if r["surname"] and (not knife_has(r["knife"])):
            out.append(r["surname"])
    out = sorted(out, key=lambda x: safe_lower(x))
    return "🚫 Без ножа:\n\n" + ("\n".join(out) if out else "Немає даних")

def format_stats(rows):
    only = [r for r in rows if r["surname"]]
    total = len(only)
    with_locker = len([r for r in only if locker_has_value(r["locker"])])
    no_locker = len([r for r in only if not locker_has_value(r["locker"])])
    with_knife = len([r for r in only if knife_has(r["knife"])])
    no_knife = len([r for r in only if not knife_has(r["knife"])])
    return (
        "📊 Статистика:\n\n"
        f"Всього: {total}\n"
        f"🗄️ З шафкою: {with_locker}\n"
        f"⛔ Без шафки: {no_locker}\n"
        f"🔪 З ножем: {with_knife}\n"
        f"🚫 Без ножа: {no_knife}"
    )

# ==============================
# 🏭 WORK: shift formatting + sorting + export txt
# ==============================

def format_shift(date_str: str, shift_type: str, shifts_rows: list) -> str:
    items = [r for r in shifts_rows if r["date"] == date_str and safe_lower(r["shift_type"]) == safe_lower(shift_type)]
    if not items:
        return "Немає даних по цій зміні."

    header = f"{date_str} ({shift_type_label(shift_type)} зміна)\n"
    items_sorted = sorted(items, key=lambda r: (safe_lower(r["hala"]), safe_lower(r["group"]), safe_lower(r["surname"])))

    blocks = []
    cur_key = None
    cur_lines = []
    for r in items_sorted:
        key = (r["hala"], r["group"])
        if cur_key != key:
            if cur_key and cur_lines:
                blocks.append("\n".join(cur_lines))
            cur_key = key
            cur_lines = [f"\n{r['hala']} / {r['group']}"]
        cur_lines.append(r["surname"])
    if cur_key and cur_lines:
        blocks.append("\n".join(cur_lines))

    return (header + "\n".join(blocks)).strip()

def compute_month_averages(perf_rows: list, month_mmyyyy: str) -> dict:
    sums, cnts = {}, {}
    for r in perf_rows:
        if month_key_from_date_str(r["date"]) != month_mmyyyy:
            continue
        p = safe_float(r.get("percent", ""))
        if p is None:
            continue
        name = r["surname"]
        if not name:
            continue
        sums[name] = sums.get(name, 0.0) + p
        cnts[name] = cnts.get(name, 0) + 1
    out = {}
    for name, s in sums.items():
        c = cnts.get(name, 0)
        if c > 0:
            out[name] = (s / c, c)
    return out

def format_sorted_workers(perf_rows: list, month_mmyyyy: str) -> str:
    avgs = compute_month_averages(perf_rows, month_mmyyyy)
    if not avgs:
        return f"Немає записів продуктивності за {month_mmyyyy}."

    low, mid, high = [], [], []
    for name, (avg, cnt) in avgs.items():
        if avg >= 100.0:
            high.append((avg, cnt, name))
        elif avg >= 90.0:
            mid.append((avg, cnt, name))
        else:
            low.append((avg, cnt, name))

    low.sort(key=lambda x: x[0])
    mid.sort(key=lambda x: x[0])
    high.sort(key=lambda x: -x[0])

    def lines(lst):
        return [f"{emoji_by_percent(avg)} {name} — avg {avg:.1f}% ({cnt} зм.)" for avg, cnt, name in lst]

    msg = [f"📌 Сортування працівників за {month_mmyyyy} (тільки з записами)\n"]
    if low:
        msg += ["🔴 < 90%"] + lines(low) + [""]
    if mid:
        msg += ["🟡 90–100%"] + lines(mid) + [""]
    if high:
        msg += ["🟢 ≥ 100%"] + lines(high)
    return "\n".join(msg).strip()

# ==============================
# 🧾 STATE
# ==============================

STATE = {"mode": None, "tmp": {}, "menu": "main", "active_shift": None}  # menu: main/employee/work

def reset_state():
    STATE["mode"] = None
    STATE["tmp"] = {}

def set_menu(menu_name: str):
    STATE["menu"] = menu_name

def is_cancel(text: str) -> bool:
    return safe_lower(text) in {safe_lower(BTN_CANCEL), "cancel", "скасувати"}

# ==============================
# COMMANDS
# ==============================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state()
    set_menu("main")
    await show_main_menu(update, context, "Готово ✅")

async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id = {update.effective_chat.id}")

# ==============================
# EMPLOYEE FLOWS (existing)
# ==============================

async def employee_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    rows = read_local_db()

    if STATE["mode"] == "add_wait_surname":
        if not text:
            await update.message.reply_text("Введи прізвище (не порожнє) або ❌ Скасувати.")
            return
        STATE["tmp"]["surname"] = text
        STATE["mode"] = "add_wait_locker"
        await update.message.reply_text("Введи номер шафки (або '-' якщо немає):")
        return

    if STATE["mode"] == "add_wait_locker":
        STATE["tmp"]["locker"] = text
        STATE["mode"] = "add_wait_knife"
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("0")], [KeyboardButton(BTN_CANCEL)]],
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
        rows.append(ensure_employee_columns(new_row))
        write_local_db(rows)

        await backup_everywhere(context, update.effective_chat.id, reason="add", caption_extra=f"Додано: {new_row['surname']}")
        reset_state()
        await show_employee_menu(update, context, f"✅ Додано: {new_row['surname']}")
        return

    if STATE["mode"] == "edit_wait_target":
        target = text
        matches = [i for i, r in enumerate(rows) if r["surname"] == target]
        if not matches:
            reset_state()
            await show_employee_menu(update, context, "❌ Не знайдено працівника.")
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
            [[KeyboardButton("1"), KeyboardButton("2"), KeyboardButton("0"), KeyboardButton("-")], [KeyboardButton(BTN_CANCEL)]],
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
        await show_employee_menu(update, context, "✅ Зміни збережено.")
        return

    if STATE["mode"] == "delete_wait_target":
        target = text
        idxs = [i for i, r in enumerate(rows) if r["surname"] == target]
        if not idxs:
            reset_state()
            await show_employee_menu(update, context, "❌ Не знайдено працівника.")
            return

        deleted = rows.pop(idxs[0])
        write_local_db(rows)

        await backup_everywhere(context, update.effective_chat.id, reason="delete", caption_extra=f"Видалено: {deleted['surname']}")
        reset_state()
        await show_employee_menu(update, context, f"🗑️ Видалено: {deleted['surname']}")
        return

    reset_state()
    await show_employee_menu(update, context)

# ==============================
# WORK FLOWS
# ==============================

def hala_kb():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("HALA 1"), KeyboardButton("HALA 2")],
            [KeyboardButton("HALA 3"), KeyboardButton("HALA 4")],
            [KeyboardButton(BTN_CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def shift_type_kb():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("day"), KeyboardButton("night")],
            [KeyboardButton(BTN_CANCEL)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

async def work_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    shifts_rows = read_shifts_db()
    perf_rows = read_perf_db()
    employees = read_local_db()

    # create shift context
    if STATE["mode"] == "work_create_shift_wait_date":
        d = date_from_keyword(text)
        if not d or parse_ddmmyyyy(d) is None:
            await update.message.reply_text("❌ Дата має бути DD.MM.YYYY або '-' для сьогодні.")
            return
        STATE["tmp"]["date"] = d
        STATE["mode"] = "work_create_shift_wait_type"
        await update.message.reply_text("Тип зміни: day або night", reply_markup=shift_type_kb())
        return

    if STATE["mode"] == "work_create_shift_wait_type":
        st = normalize_shift_type(text)
        if not st:
            await update.message.reply_text("Введи day або night (або ❌ Скасувати).")
            return

        date_str = STATE["tmp"].get("date")
        # активна зміна зберігається поза tmp, щоб не зникала після reset_state()
        STATE["active_shift"] = {"date": date_str, "shift_type": st}

        reset_state()
        await show_work_menu(update, context, f"✅ Активна зміна: {date_str} ({shift_type_label(st)})")
        return

    # show shift
    if STATE["mode"] == "work_show_shift_wait_date":
        d = date_from_keyword(text)
        if not d or parse_ddmmyyyy(d) is None:
            await update.message.reply_text("❌ Дата має бути DD.MM.YYYY або '-'")
            return
        STATE["tmp"]["date"] = d
        STATE["mode"] = "work_show_shift_wait_type"
        await update.message.reply_text("Тип зміни: day або night", reply_markup=shift_type_kb())
        return

    if STATE["mode"] == "work_show_shift_wait_type":
        st = normalize_shift_type(text)
        if not st:
            await update.message.reply_text("Введи day або night.")
            return

        date_str = STATE["tmp"].get("date")
        STATE["active_shift"] = {"date": date_str, "shift_type": st}

        shifts_rows = read_shifts_db(force=True)
        reset_state()
        await update.message.reply_text(format_shift(date_str, st, shifts_rows), reply_markup=WORK_KB)
        return

    # add workers: hala -> group -> list
    if STATE["mode"] == "work_add_workers_wait_hala":
        hala = normalize_text(text)
        if hala not in {"HALA 1", "HALA 2", "HALA 3", "HALA 4"}:
            await update.message.reply_text("Обери HALA 1–4 кнопкою.", reply_markup=hala_kb())
            return
        STATE["tmp"]["hala"] = hala
        STATE["mode"] = "work_add_workers_wait_group"
        await update.message.reply_text("Введи назву групи (наприклад G1):", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
        return

    if STATE["mode"] == "work_add_workers_wait_group":
        group = normalize_text(text)
        if not group:
            await update.message.reply_text("Введи назву групи або ❌ Скасувати.")
            return
        STATE["tmp"]["group"] = group
        STATE["mode"] = "work_add_workers_wait_list"
        await update.message.reply_text(
            "Встав список працівників (кожен з нового рядка).",
            reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)
        )
        return

    if STATE["mode"] == "work_add_workers_wait_list":
        active = STATE.get("active_shift")
        if not active:
            reset_state()
            await show_work_menu(update, context, "❗ Спочатку створи/обери зміну: ➕ Створити зміну або 📋 Показати зміну")
            return

        hala = STATE["tmp"]["hala"]
        group = STATE["tmp"]["group"]
        date_str = active["date"]
        st = active["shift_type"]

        raw = update.message.text or ""
        names = [normalize_text(x) for x in raw.splitlines() if normalize_text(x)]
        if not names:
            await update.message.reply_text("Не бачу прізвищ у повідомленні.")
            return

        emp_set = {r["surname"] for r in employees if r["surname"]}
        missing = [n for n in names if n not in emp_set]

        new_rows = shifts_rows[:]
        added = 0
        for n in names:
            if n not in emp_set:
                continue
            exists = any(
                r["date"] == date_str and safe_lower(r["shift_type"]) == st and r["hala"] == hala and r["group"] == group and r["surname"] == n
                for r in new_rows
            )
            if exists:
                continue
            new_rows.append(ensure_shift_columns({
                "date": date_str,
                "shift_type": st,
                "hala": hala,
                "group": group,
                "surname": n
            }))
            added += 1

        write_shifts_db(new_rows)
        await backup_everywhere(context, update.effective_chat.id, reason="shift_add_workers",
                                caption_extra=f"{date_str} {st} {hala}/{group} +{added}")

        reset_state()
        msg = f"✅ Додано у {hala}/{group}: {added} працівників."
        if missing:
            msg += "\n\n⚠️ Не знайдені у базі працівників:\n" + "\n".join(missing[:30])
        await show_work_menu(update, context, msg)
        return


    # auto distribute: paste names -> choose halas -> group size -> write
    if STATE["mode"] == "work_auto_wait_names":
        active = STATE.get("active_shift")
        if not active:
            reset_state()
            await show_work_menu(update, context, "❗ Спочатку створи/обери зміну: ➕ Створити зміну або 📋 Показати зміну")
            return

        raw = update.message.text or ""
        names = [normalize_text(x) for x in raw.splitlines() if normalize_text(x)]
        if not names:
            await update.message.reply_text("Не бачу прізвищ у повідомленні. Встав список (кожен з нового рядка).")
            return

        emp_set = {r["surname"] for r in employees if r["surname"]}
        ok = [n for n in names if n in emp_set]
        missing = [n for n in names if n not in emp_set]

        if not ok:
            await update.message.reply_text("❌ Жодного прізвища не знайдено у базі працівників.")
            return

        STATE["tmp"]["names_ok"] = ok
        STATE["tmp"]["missing"] = missing
        STATE["mode"] = "work_auto_wait_halas"
        kb = ReplyKeyboardMarkup(
            [
                [KeyboardButton("ALL"), KeyboardButton("HALA 1,2,3,4")],
                [KeyboardButton("HALA 1,2"), KeyboardButton("HALA 3,4")],
                [KeyboardButton(BTN_CANCEL)],
            ],
            resize_keyboard=True
        )
        await update.message.reply_text(
            "Які зали використовуємо?\n"
            "Варіанти: ALL або напиши, наприклад: HALA 1,2,4",
            reply_markup=kb
        )
        return

    if STATE["mode"] == "work_auto_wait_halas":
        t = safe_lower(text).replace(" ", "")
        if t in {"all", "hala1,2,3,4", "hala1-4"}:
            halas = ["HALA 1", "HALA 2", "HALA 3", "HALA 4"]
        else:
            # accept "hala1,2,4" or "1,2,4"
            t2 = t.replace("hala", "")
            nums = [x for x in re.split(r"[^0-9]+", t2) if x]
            halas = []
            for n in nums:
                if n in {"1", "2", "3", "4"}:
                    halas.append(f"HALA {n}")
            halas = list(dict.fromkeys(halas))  # unique preserve order
        if not halas:
            await update.message.reply_text("❌ Не зрозумів зали. Приклад: ALL або HALA 1,2,4")
            return

        STATE["tmp"]["halas"] = halas
        STATE["mode"] = "work_auto_wait_group_size"
        await update.message.reply_text(
            "Вкажи розмір групи (скільки людей в одній групі).\n"
            "Наприклад: 7",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("7"), KeyboardButton("8")],[KeyboardButton(BTN_CANCEL)]], resize_keyboard=True)
        )
        return

    if STATE["mode"] == "work_auto_wait_group_size":
        try:
            size = int(re.sub(r"[^0-9]", "", text))
        except Exception:
            size = 0
        if size <= 0 or size > 50:
            await update.message.reply_text("❌ Розмір групи має бути числом (1–50). Наприклад: 7")
            return

        active = STATE.get("active_shift")
        if not active:
            reset_state()
            await show_work_menu(update, context, "❗ Спочатку створи/обери зміну: ➕ Створити зміну або 📋 Показати зміну")
            return

        date_str = active["date"]
        st = active["shift_type"]
        halas = STATE["tmp"]["halas"]
        names_ok = STATE["tmp"]["names_ok"]
        missing = STATE["tmp"]["missing"]

        # round-robin across halas, chunk into groups per hala
        buckets = {h: [] for h in halas}
        for i, n in enumerate(names_ok):
            h = halas[i % len(halas)]
            buckets[h].append(n)

        new_rows = shifts_rows[:]
        added = 0
        for hala, arr in buckets.items():
            # groups: G1, G2, ...
            gnum = 1
            for i in range(0, len(arr), size):
                group = f"G{gnum}"
                gnum += 1
                chunk = arr[i:i+size]
                for n in chunk:
                    exists = any(
                        r["date"] == date_str and safe_lower(r["shift_type"]) == st and r["hala"] == hala and r["group"] == group and r["surname"] == n
                        for r in new_rows
                    )
                    if exists:
                        continue
                    new_rows.append(ensure_shift_columns({
                        "date": date_str,
                        "shift_type": st,
                        "hala": hala,
                        "group": group,
                        "surname": n
                    }))
                    added += 1

        write_shifts_db(new_rows)
        await backup_everywhere(
            context,
            update.effective_chat.id,
            reason="shift_auto_distribute",
            caption_extra=f"{date_str} {st} auto +{added}"
        )

        reset_state()

        # summary
        lines = [f"✅ Авто-розподіл готовий: додано {added} записів.",
                 f"Зміна: {date_str} ({shift_type_label(st)})",
                 f"Зали: {', '.join(halas)}",
                 f"Розмір групи: {size}"]
        for h in halas:
            cnt = len(buckets.get(h, []))
            if cnt:
                lines.append(f"• {h}: {cnt} людей")
        if missing:
            lines.append("\n⚠️ Не знайдені у базі працівників:")
            lines.extend(missing[:30])

        await show_work_menu(update, context, "\n".join(lines))
        return
    # set group percent
    if STATE["mode"] == "work_set_percent_wait_hala":
        hala = normalize_text(text)
        if hala not in {"HALA 1", "HALA 2", "HALA 3", "HALA 4"}:
            await update.message.reply_text("Обери HALA 1–4 кнопкою.", reply_markup=hala_kb())
            return
        STATE["tmp"]["hala"] = hala
        STATE["mode"] = "work_set_percent_wait_group"
        await update.message.reply_text("Введи назву групи (наприклад G1):", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
        return

    if STATE["mode"] == "work_set_percent_wait_group":
        group = normalize_text(text)
        if not group:
            await update.message.reply_text("Введи назву групи.")
            return
        STATE["tmp"]["group"] = group
        STATE["mode"] = "work_set_percent_wait_value"
        await update.message.reply_text("Введи % (наприклад 102 або 99.5):", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
        return

    if STATE["mode"] == "work_set_percent_wait_value":
        p = safe_float(text)
        if p is None:
            await update.message.reply_text("❌ Не схоже на число. Приклад: 102 або 99.5")
            return

        active = STATE.get("active_shift")
        if not active:
            reset_state()
            await show_work_menu(update, context, "❗ Спочатку обери зміну: 📋 Показати зміну або ➕ Створити зміну")
            return

        date_str = active["date"]
        st = active["shift_type"]
        hala = STATE["tmp"]["hala"]
        group = STATE["tmp"]["group"]

        shifts_rows2 = read_shifts_db(force=True)
        members = [r["surname"] for r in shifts_rows2 if r["date"] == date_str and safe_lower(r["shift_type"]) == st and r["hala"] == hala and r["group"] == group and r["surname"]]
        if not members:
            reset_state()
            await show_work_menu(update, context, f"❌ Немає працівників у {hala}/{group} для {date_str}.")
            return

        perf_rows2 = read_perf_db(force=True)
        member_set = set(members)
        filtered = []
        for r in perf_rows2:
            same = (r["date"] == date_str and safe_lower(r["shift_type"]) == st and r["hala"] == hala and r["group"] == group and r["surname"] in member_set)
            if same:
                continue
            filtered.append(r)

        for name in members:
            filtered.append(ensure_perf_columns({
                "date": date_str,
                "shift_type": st,
                "hala": hala,
                "group": group,
                "surname": name,
                "percent": str(p)
            }))

        write_perf_db(filtered)
        await backup_everywhere(context, update.effective_chat.id, reason="group_percent",
                                caption_extra=f"{date_str} {st} {hala}/{group} = {p}")

        reset_state()
        await show_work_menu(update, context, f"✅ Записано {p}% для {hala}/{group}\nПрацівників: {len(members)}")
        return

    # sort workers (month)
    if STATE["mode"] == "work_sort_wait_month":
        if text == "-" or safe_lower(text) == "поточний":
            month = datetime.now().strftime("%m.%Y")
        else:
            dt = parse_mmyyyy(text)
            if dt is None:
                await update.message.reply_text("❌ Формат: MM.YYYY (наприклад 02.2025) або '-' для поточного.")
                return
            month = dt.strftime("%m.%Y")

        perf_rows2 = read_perf_db(force=True)
        reset_state()
        await update.message.reply_text(format_sorted_workers(perf_rows2, month), reply_markup=WORK_KB)
        return

    # export txt (date+type)
    if STATE["mode"] == "work_export_wait_date":
        d = date_from_keyword(text)
        if not d or parse_ddmmyyyy(d) is None:
            await update.message.reply_text("❌ Дата має бути DD.MM.YYYY або '-'")
            return
        STATE["tmp"]["date"] = d
        STATE["mode"] = "work_export_wait_type"
        await update.message.reply_text("Тип зміни: day або night", reply_markup=shift_type_kb())
        return

    if STATE["mode"] == "work_export_wait_type":
        st = normalize_shift_type(text)
        if not st:
            await update.message.reply_text("Введи day або night.")
            return

        date_str = STATE["tmp"]["date"]
        shifts_rows2 = read_shifts_db(force=True)
        content = format_shift(date_str, st, shifts_rows2)

        filename = f"shift_{date_str.replace('.','-')}_{st}.txt"
        path = os.path.join(BACKUP_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content + "\n")

        reset_state()
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=InputFile(path, filename=filename),
            caption=f"📝 План зміни TXT: {date_str} ({shift_type_label(st)})"
        )
        await show_work_menu(update, context, "Готово ✅")
        return

    reset_state()
    await show_work_menu(update, context)

# ==============================
# TEXT HANDLER
# ==============================

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not getattr(update.message, "text", None):
        return

    text = normalize_text(update.message.text)

    # Cancel inside flows
    if STATE["mode"] and is_cancel(text):
        reset_state()
        if STATE["menu"] == "employee":
            await show_employee_menu(update, context, "Скасовано ✅")
        elif STATE["menu"] == "work":
            await show_work_menu(update, context, "Скасовано ✅")
        else:
            await show_main_menu(update, context, "Скасовано ✅")
        return

    # Restore expects file
    if STATE["mode"] == "restore_wait_file":
        await update.message.reply_text("❗️Надішли CSV файлом (документом).")
        return

    # Route flow
    if STATE["mode"]:
        if STATE["menu"] == "employee":
            await employee_flow_handler(update, context, text)
            return
        if STATE["menu"] == "work":
            await work_flow_handler(update, context, text)
            return

    # MAIN MENU
    if is_btn(text, BTN_EMPLOYEE_MENU):
        set_menu("employee")
        reset_state()
        await show_employee_menu(update, context, "Меню: Працівник ✅")
        return

    if is_btn(text, BTN_WORK_MENU):
        set_menu("work")
        reset_state()
        await show_work_menu(update, context, "Меню: Організація роботи ✅\n\nСпочатку створи/обери зміну.")
        return

    if is_btn(text, "Backup"):
        paths = await backup_everywhere(context, update.effective_chat.id, reason="manual")
        names = "\n".join([os.path.basename(p) for p in paths])
        await update.message.reply_text(f"💾 Backup зроблено:\n{names}", reply_markup=MAIN_KB)
        return

    if is_btn(text, "Seed"):
        if os.path.exists(LOCAL_DB_PATH):
            await backup_everywhere(context, update.effective_chat.id, reason="pre_seed")
        rows2 = fetch_google_csv_rows()
        write_local_db(rows2)
        await backup_everywhere(context, update.effective_chat.id, reason="after_seed")
        await show_main_menu(update, context, f"🧬 Seed завершено ✅\nЗаписів: {len(rows2)}")
        return

    if is_btn(text, "Відновити"):
        STATE["mode"] = "restore_wait_file"
        STATE["tmp"] = {}
        set_menu("main")
        await update.message.reply_text("♻️ Надішли CSV файлом (документом) — я відновлю базу працівників (local_data.csv).")
        return

    # EMPLOYEE MENU buttons
    if STATE["menu"] == "employee":
        rows = read_local_db()

        if is_btn(text, "Статистика"):
            await update.message.reply_text(format_stats(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Всі"):
            await update.message.reply_text(format_all(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "З шафкою"):
            await update.message.reply_text(format_with_locker(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Без шафки"):
            await update.message.reply_text(format_no_locker(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "З ножем"):
            await update.message.reply_text(format_with_knife(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Без ножа"):
            await update.message.reply_text(format_no_knife(rows), reply_markup=EMPLOYEE_KB); return

        if is_btn(text, "Додати працівника"):
            STATE["mode"] = "add_wait_surname"; STATE["tmp"] = {}
            await update.message.reply_text("➕ Введи прізвище та ім'я працівника:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
            return
        if is_btn(text, "Редагувати працівника"):
            STATE["mode"] = "edit_wait_target"; STATE["tmp"] = {}
            await update.message.reply_text("✏️ Введи прізвище працівника (точно як у списку):", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
            return
        if is_btn(text, "Видалити працівника"):
            STATE["mode"] = "delete_wait_target"; STATE["tmp"] = {}
            await update.message.reply_text("🗑️ Введи прізвище працівника (точно як у списку):", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
            return

        if is_btn(text, BTN_BACK):
            set_menu("main"); reset_state()
            await show_main_menu(update, context, "Назад ✅"); return

        await show_employee_menu(update, context); return

    # WORK MENU buttons
    if STATE["menu"] == "work":
        if is_btn(text, "Створити зміну"):
            STATE["mode"] = "work_create_shift_wait_date"; STATE["tmp"] = {}
            await update.message.reply_text("Обери дату кнопкою (календар) або введи DD.MM.YYYY:", reply_markup=date_kb())
            return

        if is_btn(text, "Показати зміну"):
            STATE["mode"] = "work_show_shift_wait_date"; STATE["tmp"] = {}
            await update.message.reply_text("Обери дату кнопкою (календар) або введи DD.MM.YYYY:", reply_markup=date_kb())
            return

        if is_btn(text, "Додати працівників"):
            active = STATE.get("active_shift")
            if not active:
                await show_work_menu(update, context, "❗ Спочатку створи зміну: ➕ Створити зміну"); return
            STATE["mode"] = "work_add_workers_wait_hala"
            await update.message.reply_text("Обери зал:", reply_markup=hala_kb())
            return

        if is_btn(text, "Авто-розподіл"):
            active = STATE.get("active_shift")
            if not active:
                await show_work_menu(update, context, "❗ Спочатку створи зміну: ➕ Створити зміну"); return
            STATE["mode"] = "work_auto_wait_names"
            STATE["tmp"] = {}
            await update.message.reply_text(
                "Встав список працівників (кожен з нового рядка).\n\nПотім я автоматично розкладу по HALA 1–4.",
                reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)
            )
            return
        if is_btn(text, "Внести %"):
            active = STATE.get("active_shift")
            if not active:
                await show_work_menu(update, context, "❗ Спочатку обери зміну: 📋 Показати зміну або ➕ Створити зміну"); return
            STATE["mode"] = "work_set_percent_wait_hala"
            await update.message.reply_text("Обери зал:", reply_markup=hala_kb())
            return

        if is_btn(text, "Сортування"):
            STATE["mode"] = "work_sort_wait_month"; STATE["tmp"] = {}
            await update.message.reply_text("Введи місяць MM.YYYY (02.2025) або '-' для поточного:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
            return

        if is_btn(text, "Backup зміни"):
            paths = await backup_everywhere(context, update.effective_chat.id, reason="manual_shift")
            names = "\n".join([os.path.basename(p) for p in paths])
            await update.message.reply_text(f"💾 Backup зміни зроблено:\n{names}", reply_markup=WORK_KB)
            return

        if is_btn(text, "Експорт"):
            STATE["mode"] = "work_export_wait_date"; STATE["tmp"] = {}
            await update.message.reply_text("Обери дату кнопкою (календар) або введи DD.MM.YYYY:", reply_markup=date_kb())
            return

        if is_btn(text, BTN_BACK):
            set_menu("main"); reset_state()
            await show_main_menu(update, context, "Назад ✅"); return

        await show_work_menu(update, context); return

    await show_main_menu(update, context)

# ==============================
# DOCUMENT HANDLER (restore employees)
# ==============================

async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if STATE["mode"] != "restore_wait_file":
        await update.message.reply_text("Я отримав файл, але зараз не в режимі відновлення. Натисни ♻️ Відновити з файлу.")
        return

    doc: Document = update.message.document
    if not (doc.file_name or "").lower().endswith(".csv"):
        await update.message.reply_text("❌ Потрібен CSV файл.")
        return

    if os.path.exists(LOCAL_DB_PATH):
        await backup_everywhere(context, update.effective_chat.id, reason="pre_restore")

    file = await doc.get_file()
    content = await file.download_as_bytearray()
    text = content.decode("utf-8", errors="replace")

    reader = csv.DictReader(StringIO(text))
    rows = [ensure_employee_columns(r) for r in reader]
    rows = [r for r in rows if r["surname"]]

    write_local_db(rows)
    await backup_everywhere(context, update.effective_chat.id, reason="after_restore", caption_extra=f"Записів: {len(rows)}")

    reset_state()
    set_menu("main")
    await show_main_menu(update, context, f"♻️ Відновлено ✅\nЗаписів: {len(rows)}")

# ==============================
# MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    ensure_shifts_file()
    ensure_perf_file()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
