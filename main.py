import os
import csv
import re
import zipfile
import threading
from datetime import datetime, timedelta
from io import StringIO
import io
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
# RENDER HEALTH PORT
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
# CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CSV_URL = os.getenv(
    "CSV_URL",
    "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
).strip()

EMPLOYEES_DB_PATH = os.getenv("EMPLOYEES_DB_PATH", "employees.csv").strip()
OLD_LOCAL_DB_PATH = os.getenv("LOCAL_DB_PATH", "local_data.csv").strip()

SHIFTS_DB_PATH = os.getenv("SHIFTS_DB_PATH", "shifts.csv").strip()
PERF_DB_PATH = os.getenv("PERF_DB_PATH", "performance.csv").strip()
SHIFT_SUMMARY_DB_PATH = os.getenv("SHIFT_SUMMARY_DB_PATH", "shift_summary.csv").strip()

BACKUP_CHAT_ID_RAW = os.getenv("BACKUP_CHAT_ID", "").strip()
BACKUP_CHAT_ID = int(BACKUP_CHAT_ID_RAW) if BACKUP_CHAT_ID_RAW else None

BACKUP_DIR = os.getenv("BACKUP_DIR", "backups").strip()
os.makedirs(BACKUP_DIR, exist_ok=True)

WRITE_LOCK = threading.RLock()

_employee_cache = {"mtime": None, "rows": []}
_shift_cache = {"mtime": None, "rows": []}
_perf_cache = {"mtime": None, "rows": []}
_summary_cache = {"mtime": None, "rows": []}

# ==============================
# FIXED SAP LIST
# ==============================

SEED_SAP_LIST = """
51010777 - BABAKHANOVA OLHA
51011125 - BEREZIUK ALINA
51011091 - FITENKO NASTASIIA
51010373 - FITENKO NATALIA
51010279 - HANCHARYK TATSIANA
51009485 - HAVRYLIUK YULIIA
51011117 - HLABUS SOFIIA
51011047 - HRYSHCHUK ARTEM
51010539 - HUNKA VLADYSLAV
51010062 - ISAKOVA VALENTYNA
51010970 - KOBETS KATERYNA
51010773 - KONONOVYCH SNIZHANA
51011078 - KONOPLITSKA SVITLANA
51011043 - KOROLENKO VALENTYN
51010667 - KUFLOVSKYI DEMIAN
51010744 - KUZ VALERII
51010372 - KUZMINA OLHA
51011054 - KUZOVKIN DMYTRO
51010775 - KYDUN SOFIIA
51010446 - LAKHTIUK OLEH
51009922 - LAPCHUK TETIANA
51011075 - LEBEDKO SERHII
51011118 - LENCHUK ANZHELA
51010825 - MARCHENKO OLEKSANDR
51010281 - MARUSHKO YARYNA
51009619 - MELNIKAU DZMITRY
51011028 - MISIUK MARIIA
51010828 - MOROZ VLADYSLAV
51010801 - MUKHOV DANYLO
51010937 - MUSHYNSKA TETIANA
51010972 - MUSIIENKO VALERIIA
51010936 - MUZYKA ILONA
51011127 - NIKOLAIEVA MARIIA
51010909 - NIKOLTSIV MYKHAILO
51010908 - NIKOLTSIV NADIIA
51010939 - OSTAPCHUK SVITLANA
51010881 - PETRIV DMYTRO
51011124 - PIDHURSKYI VITALII
51010826 - POLISHCHUK IVAN
51010447 - PRYIMACHUK ANHELINA
51010971 - RUDCHYK IRYNA
51010852 - SAFRONIUK NATALIIA
51011071 - SAMKOV OLEKSANDR
51009998 - SAMOLIUK YULIIA
51011126 - SAVYCH YEVHENIIA
51009288 - SHKURYNSKA NATALIIA
51011116 - SOLTYS SOLOMIIA
51010668 - SPALYLO MYKHAILO
51011120 - STOIANOVSKA YELYZAVETA
51011048 - TKACHENKO KIRA
51011074 - TOMASHEVYCH STANISLAV
51011107 - TRETIAKOV OLEKSANDR
51010002 - TROKHYMETS DMYTRO
51010827 - TYMOSHEVSKYI ANDRII
51010776 - ULOSHVAI ARTEM
51010540 - VOVK ANNA
51010853 - YAKYMCHUK STEPAN
51010774 - YURASHKEVYCH YURII
51010938 - YURKIV VIKTORIIA
51010541 - ZALEVSKYI NAZAR
""".strip()

# ==============================
# UI
# ==============================

BTN_EMPLOYEE_MENU = "👤 Працівник"
BTN_WORK_MENU = "🏭 Організація роботи"
BTN_BACKUP = "💾 Backup бази"
BTN_SEED_SAP = "🧬 Seed SAP"
BTN_RESTORE = "♻️ Відновити з файлу"
BTN_BACK = "⬅️ Назад"
BTN_CANCEL = "❌ Скасувати"

MAIN_KB = ReplyKeyboardMarkup(
    [[BTN_EMPLOYEE_MENU, BTN_WORK_MENU], [BTN_BACKUP, BTN_SEED_SAP], [BTN_RESTORE]],
    resize_keyboard=True
)

BTN_STATS = "📊 Статистика"
BTN_ALL = "👥 Всі"
BTN_CARD = "🔎 Картка працівника"
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
        [BTN_CARD],
        [BTN_WITH_LOCKER, BTN_NO_LOCKER],
        [BTN_WITH_KNIFE, BTN_NO_KNIFE],
        [BTN_ADD, BTN_EDIT],
        [BTN_DELETE],
        [BTN_BACK],
    ],
    resize_keyboard=True
)

BTN_SHIFT_CREATE = "➕ Створити зміну"
BTN_SHIFT_SHOW = "📋 Показати зміну"
BTN_GROUP_ADD_WORKERS = "👥 Додати працівників у групу"
BTN_IMPORT_PERCENT = "📥 Імпорт % SAP"
BTN_GROUP_SET_PERCENT = "📈 Внести % групи"
BTN_SORT_WORKERS = "📌 Сортування працівників"
BTN_EXPORT_TXT = "📝 Експорт зміни TXT"
BTN_SHIFT_SUMMARY = "📊 % по зміні"
BTN_SHIFT_BACKUP = "💾 Backup зміни"

WORK_KB = ReplyKeyboardMarkup(
    [
        [BTN_SHIFT_CREATE, BTN_SHIFT_SHOW],
        [BTN_GROUP_ADD_WORKERS],
        [BTN_IMPORT_PERCENT, BTN_GROUP_SET_PERCENT],
        [BTN_SHIFT_SUMMARY],
        [BTN_SORT_WORKERS],
        [BTN_EXPORT_TXT, BTN_SHIFT_BACKUP],
        [BTN_BACK],
    ],
    resize_keyboard=True
)

# ==============================
# HELPERS
# ==============================

def normalize_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def safe_lower(s: str) -> str:
    return normalize_text(s).lower()

def is_btn(text: str, keyword: str) -> bool:
    return safe_lower(text) == safe_lower(keyword) or safe_lower(keyword) in safe_lower(text)

def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def today_ddmmyyyy() -> str:
    return datetime.now().strftime("%d.%m.%Y")

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

def parse_ddmmyyyy(s: str):
    try:
        return datetime.strptime(normalize_text(s), "%d.%m.%Y")
    except Exception:
        return None

def parse_mmyyyy(s: str):
    try:
        return datetime.strptime("01." + normalize_text(s), "%d.%m.%Y")
    except Exception:
        return None

def month_key_from_date_str(date_str: str) -> str:
    dt = parse_ddmmyyyy(date_str)
    return dt.strftime("%m.%Y") if dt else ""

def extract_date_from_btn(text: str) -> str:
    t = normalize_text(text)
    if t == "-":
        return today_ddmmyyyy()
    return normalize_text(t.replace("📅", ""))

def date_kb(days_back: int = 14, days_forward: int = 7):
    today = datetime.now().date()
    dates = []
    for d in range(days_back, 0, -1):
        dates.append((today - timedelta(days=d)).strftime("%d.%m.%Y"))
    dates.append(today.strftime("%d.%m.%Y"))
    for d in range(1, days_forward + 1):
        dates.append((today + timedelta(days=d)).strftime("%d.%m.%Y"))

    rows, row = [], []
    for s in dates:
        row.append(KeyboardButton(f"📅 {s}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(BTN_CANCEL)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def normalize_shift_type(text: str) -> str:
    t = safe_lower(text)
    if t in {"night", "ніч", "нічна"}:
        return "night"
    if t in {"day", "день", "денна"}:
        return "day"
    return ""

def shift_type_label(st: str) -> str:
    return "нічна" if safe_lower(st) == "night" else "денна"

def shift_type_kb():
    return ReplyKeyboardMarkup([[KeyboardButton("day"), KeyboardButton("night")], [KeyboardButton(BTN_CANCEL)]], resize_keyboard=True)

def hala_kb():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("HALA 1"), KeyboardButton("HALA 2")],
         [KeyboardButton("HALA 3"), KeyboardButton("HALA 4")],
         [KeyboardButton(BTN_CANCEL)]],
        resize_keyboard=True
    )

def safe_float(s: str):
    try:
        return float(normalize_text(s).replace("%", "").replace(",", "."))
    except Exception:
        return None

def fmt_percent(p):
    val = safe_float(str(p))
    if val is None:
        return "-"
    return f"{val:.2f}".replace(".", ",")

def emoji_by_percent(p: float) -> str:
    if p >= 100:
        return "🟢"
    if p >= 90:
        return "🟡"
    return "🔴"

def locker_has_value(v: str) -> bool:
    v = normalize_text(v)
    if not v:
        return False
    return safe_lower(v) not in {"-", "—", "–", "нема", "нет", "ні", "no", "none"}

def knife_has(v: str) -> bool:
    return normalize_text(v) in {"1", "2", "yes", "так", "є"}

def parse_sap_name_line(line: str):
    line = normalize_text(line)
    if not line:
        return None
    m = re.match(r"^(\d{6,12})\s*[-–—]\s*(.+)$", line)
    if m:
        return m.group(1), normalize_text(m.group(2)).upper()
    m = re.match(r"^(.+?)\s+(\d{6,12})$", line)
    if m:
        return m.group(2), normalize_text(m.group(1)).upper()
    return None

def parse_sap_percent_line(line: str):
    line = normalize_text(line)
    if not line:
        return None
    m = re.match(r"^(\d{6,12})\s*[-–—\s]\s*([0-9]+(?:[,.][0-9]+)?)\s*%?$", line)
    if not m:
        return None
    return m.group(1), str(safe_float(m.group(2)))

# ==============================
# CSV COLUMNS
# ==============================

EMPLOYEE_FIELDS = ["sap", "surname", "locker", "knife", "shoe_size", "shoe_type", "address", "status"]
SHIFT_FIELDS = ["date", "shift_type", "hala", "group", "sap", "surname"]
PERF_FIELDS = ["date", "shift_type", "hala", "group", "sap", "surname", "percent"]
SUMMARY_FIELDS = ["date", "shift_type", "total_percent", "agency_percent"]

def ensure_employee_columns(r: dict) -> dict:
    sap = normalize_text(r.get("sap", "") or r.get("SAP", ""))
    return {
        "sap": sap,
        "surname": normalize_text(r.get("surname", "") or r.get("name", "")).upper(),
        "locker": normalize_text(r.get("locker", "")),
        "knife": normalize_text(r.get("knife", "")),
        "shoe_size": normalize_text(r.get("shoe_size", "")),
        "shoe_type": normalize_text(r.get("shoe_type", "")) or "unknown",
        "address": normalize_text(r.get("address", "") or r.get("Address", "")),
        "status": normalize_text(r.get("status", "")) or "active",
    }

def ensure_shift_columns(r: dict) -> dict:
    return {
        "date": normalize_text(r.get("date", "")),
        "shift_type": normalize_shift_type(r.get("shift_type", "")) or normalize_text(r.get("shift_type", "")),
        "hala": normalize_text(r.get("hala", "")),
        "group": normalize_text(r.get("group", "")),
        "sap": normalize_text(r.get("sap", "")),
        "surname": normalize_text(r.get("surname", "")).upper(),
    }

def ensure_perf_columns(r: dict) -> dict:
    return {
        "date": normalize_text(r.get("date", "")),
        "shift_type": normalize_shift_type(r.get("shift_type", "")) or normalize_text(r.get("shift_type", "")),
        "hala": normalize_text(r.get("hala", "")),
        "group": normalize_text(r.get("group", "")),
        "sap": normalize_text(r.get("sap", "")),
        "surname": normalize_text(r.get("surname", "")).upper(),
        "percent": normalize_text(r.get("percent", "")),
    }

def ensure_summary_columns(r: dict) -> dict:
    return {
        "date": normalize_text(r.get("date", "")),
        "shift_type": normalize_shift_type(r.get("shift_type", "")) or normalize_text(r.get("shift_type", "")),
        "total_percent": normalize_text(r.get("total_percent", "")),
        "agency_percent": normalize_text(r.get("agency_percent", "")),
    }

# ==============================
# DB
# ==============================

def ensure_file(path, fields):
    if os.path.exists(path):
        return
    with WRITE_LOCK:
        if not os.path.exists(path):
            atomic_write_csv(path, fields, [])

def ensure_all_files():
    ensure_file(EMPLOYEES_DB_PATH, EMPLOYEE_FIELDS)
    ensure_file(SHIFTS_DB_PATH, SHIFT_FIELDS)
    ensure_file(PERF_DB_PATH, PERF_FIELDS)
    ensure_file(SHIFT_SUMMARY_DB_PATH, SUMMARY_FIELDS)

def read_csv_cached(path, fields, cache, normalizer, force=False):
    ensure_file(path, fields)
    mtime = _file_mtime(path)
    if not force and cache["mtime"] is not None and cache["mtime"] == mtime:
        return cache["rows"]
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(normalizer(r))
    cache["rows"] = rows
    cache["mtime"] = mtime
    return rows

def write_csv_db(path, fields, rows, cache, normalizer):
    with WRITE_LOCK:
        norm = [normalizer(r) for r in rows]
        atomic_write_csv(path, fields, norm)
        cache["rows"] = norm
        cache["mtime"] = _file_mtime(path)

def read_employees(force=False):
    return read_csv_cached(EMPLOYEES_DB_PATH, EMPLOYEE_FIELDS, _employee_cache, ensure_employee_columns, force)

def write_employees(rows):
    write_csv_db(EMPLOYEES_DB_PATH, EMPLOYEE_FIELDS, rows, _employee_cache, ensure_employee_columns)

def read_shifts(force=False):
    return read_csv_cached(SHIFTS_DB_PATH, SHIFT_FIELDS, _shift_cache, ensure_shift_columns, force)

def write_shifts(rows):
    write_csv_db(SHIFTS_DB_PATH, SHIFT_FIELDS, rows, _shift_cache, ensure_shift_columns)

def read_perf(force=False):
    return read_csv_cached(PERF_DB_PATH, PERF_FIELDS, _perf_cache, ensure_perf_columns, force)

def write_perf(rows):
    write_csv_db(PERF_DB_PATH, PERF_FIELDS, rows, _perf_cache, ensure_perf_columns)

def read_summary(force=False):
    return read_csv_cached(SHIFT_SUMMARY_DB_PATH, SUMMARY_FIELDS, _summary_cache, ensure_summary_columns, force)

def write_summary(rows):
    write_csv_db(SHIFT_SUMMARY_DB_PATH, SUMMARY_FIELDS, rows, _summary_cache, ensure_summary_columns)

def employee_by_sap(rows, sap: str):
    sap = normalize_text(sap)
    for r in rows:
        if r["sap"] == sap:
            return r
    return None

def find_employees(rows, q: str):
    q = safe_lower(q)
    if not q:
        return []
    return [r for r in rows if q in safe_lower(r["sap"]) or q in safe_lower(r["surname"])]

def upsert_employee(rows, emp):
    emp = ensure_employee_columns(emp)
    out = []
    found = False
    for r in rows:
        if r["sap"] and emp["sap"] and r["sap"] == emp["sap"]:
            merged = r.copy()
            for k, v in emp.items():
                if v != "":
                    merged[k] = v
            out.append(ensure_employee_columns(merged))
            found = True
        else:
            out.append(r)
    if not found:
        out.append(emp)
    return out

# ==============================
# SEED / MIGRATION
# ==============================

def seed_sap_rows():
    rows = []
    for line in SEED_SAP_LIST.splitlines():
        parsed = parse_sap_name_line(line)
        if parsed:
            sap, name = parsed
            rows.append(ensure_employee_columns({"sap": sap, "surname": name}))
    return rows

def merge_seed_sap():
    rows = read_employees(force=True)
    for emp in seed_sap_rows():
        rows = upsert_employee(rows, emp)
    write_employees(rows)
    return len(rows)

def migrate_old_local_if_needed():
    if os.path.exists(EMPLOYEES_DB_PATH):
        return
    if not os.path.exists(OLD_LOCAL_DB_PATH):
        ensure_file(EMPLOYEES_DB_PATH, EMPLOYEE_FIELDS)
        return
    old_rows = []
    with open(OLD_LOCAL_DB_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            old_rows.append(ensure_employee_columns({
                "surname": r.get("surname", ""),
                "locker": r.get("locker", ""),
                "knife": r.get("knife", ""),
                "address": r.get("Address", ""),
            }))
    seed = seed_sap_rows()
    by_name = {safe_lower(e["surname"]): e for e in seed}
    migrated = []
    for old in old_rows:
        s = safe_lower(old["surname"])
        if s in by_name:
            emp = by_name[s].copy()
            emp["locker"] = old["locker"]
            emp["knife"] = old["knife"]
            emp["address"] = old["address"]
            migrated.append(emp)
        else:
            migrated.append(old)
    write_employees(migrated)

def fetch_google_csv_rows():
    resp = requests.get(CSV_URL, timeout=20)
    resp.encoding = "utf-8"
    reader = csv.DictReader(StringIO(resp.text))
    rows = []
    seed = {safe_lower(e["surname"]): e for e in seed_sap_rows()}
    for r in reader:
        name = normalize_text(r.get("surname", "")).upper()
        if not name:
            continue
        emp = seed.get(safe_lower(name), {}).copy()
        emp.update({
            "surname": name,
            "locker": normalize_text(r.get("locker", "")),
            "knife": normalize_text(r.get("knife", "")),
            "address": normalize_text(r.get("Address", "")),
        })
        rows.append(ensure_employee_columns(emp))
    return rows

# ==============================
# BACKUP
# ==============================

def make_backup_zip(reason: str) -> str:
    ensure_all_files()
    path = os.path.join(BACKUP_DIR, f"backup_{now_ts()}_{reason}.zip")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in [EMPLOYEES_DB_PATH, SHIFTS_DB_PATH, PERF_DB_PATH, SHIFT_SUMMARY_DB_PATH]:
            if os.path.exists(p):
                z.write(p, arcname=os.path.basename(p))
    return path

async def send_backup_to_chat(context, chat_id, file_path, caption):
    with open(file_path, "rb") as f:
        await context.bot.send_document(chat_id=chat_id, document=f, filename=os.path.basename(file_path), caption=caption)

async def backup_everywhere(context, trigger_chat_id: int, reason: str, caption_extra: str = ""):
    path = make_backup_zip(reason)
    caption = f"💾 Backup • {reason}\n{os.path.basename(path)}"
    if caption_extra:
        caption += f"\n{caption_extra}"
    if BACKUP_CHAT_ID:
        try:
            await send_backup_to_chat(context, BACKUP_CHAT_ID, path, caption)
        except Exception as e:
            await context.bot.send_message(chat_id=trigger_chat_id, text=f"⚠️ Backup у групу не відправився: {e}")
    return [path]

# ==============================
# FORMATTERS
# ==============================

def emp_display(e):
    return f"{e['sap'] or 'NO SAP'} — {e['surname']}"

def shoe_display(e):
    st = safe_lower(e.get("shoe_type", "unknown"))
    label = "своє" if st == "own" else "видано агенцією" if st == "agency" else "не вказано"
    size = e.get("shoe_size", "")
    if size and st != "unknown":
        return f"{size}, {label}"
    if size:
        return size
    return label

def format_employee_card(emp, perf_rows):
    vals = [r for r in perf_rows if r["sap"] == emp["sap"] and safe_float(r["percent"]) is not None]
    vals_sorted = sorted(vals, key=lambda r: (parse_ddmmyyyy(r["date"]) or datetime.min), reverse=True)
    last = vals_sorted[0] if vals_sorted else None
    avg = None
    if vals:
        nums = [safe_float(r["percent"]) for r in vals]
        avg = sum(nums) / len(nums)

    return (
        "👤 Картка працівника\n\n"
        f"SAP: {emp['sap'] or '-'}\n"
        f"Працівник: {emp['surname'] or '-'}\n"
        f"Шафка: {emp['locker'] or '-'}\n"
        f"Ніж: {'є' if knife_has(emp['knife']) else 'немає'}\n"
        f"Взуття: {shoe_display(emp)}\n"
        f"Статус: {emp['status'] or 'active'}\n\n"
        "📊 Продуктивність:\n"
        f"Остання: {(last['date'] + ' — ' + fmt_percent(last['percent']) + '%') if last else '-'}\n"
        f"Середня: {(fmt_percent(avg) + '%') if avg is not None else '-'}"
    )

def format_all(rows):
    items = sorted([emp_display(r) for r in rows if r["surname"]], key=safe_lower)
    return "👥 Всі:\n\n" + ("\n".join(items) if items else "Немає даних")

def format_with_locker(rows):
    items = [f"{emp_display(r)} — шафка {r['locker']}" for r in rows if r["surname"] and locker_has_value(r["locker"])]
    return "🗄️ З шафкою:\n\n" + ("\n".join(sorted(items, key=safe_lower)) if items else "Немає даних")

def format_no_locker(rows):
    items = [emp_display(r) for r in rows if r["surname"] and not locker_has_value(r["locker"])]
    return "⛔ Без шафки:\n\n" + ("\n".join(sorted(items, key=safe_lower)) if items else "Немає даних")

def format_with_knife(rows):
    items = [emp_display(r) for r in rows if r["surname"] and knife_has(r["knife"])]
    return "🔪 З ножем:\n\n" + ("\n".join(sorted(items, key=safe_lower)) if items else "Немає даних")

def format_no_knife(rows):
    items = [emp_display(r) for r in rows if r["surname"] and not knife_has(r["knife"])]
    return "🚫 Без ножа:\n\n" + ("\n".join(sorted(items, key=safe_lower)) if items else "Немає даних")

def format_stats(rows):
    only = [r for r in rows if r["surname"]]
    return (
        "📊 Статистика:\n\n"
        f"Всього: {len(only)}\n"
        f"З SAP: {len([r for r in only if r['sap']])}\n"
        f"Без SAP: {len([r for r in only if not r['sap']])}\n"
        f"🗄️ З шафкою: {len([r for r in only if locker_has_value(r['locker'])])}\n"
        f"⛔ Без шафки: {len([r for r in only if not locker_has_value(r['locker'])])}\n"
        f"🔪 З ножем: {len([r for r in only if knife_has(r['knife'])])}\n"
        f"🚫 Без ножа: {len([r for r in only if not knife_has(r['knife'])])}"
    )

def get_shift_summary(summary_rows, date_str, shift_type):
    for r in summary_rows:
        if r["date"] == date_str and safe_lower(r["shift_type"]) == safe_lower(shift_type):
            return r
    return None

def compute_shift_avg(perf_rows, date_str, st):
    vals = [safe_float(r["percent"]) for r in perf_rows if r["date"] == date_str and safe_lower(r["shift_type"]) == st and safe_float(r["percent"]) is not None]
    return sum(vals) / len(vals) if vals else None

def format_shift(date_str, st, shifts_rows, perf_rows, summary_rows):
    items = [r for r in shifts_rows if r["date"] == date_str and safe_lower(r["shift_type"]) == safe_lower(st)]
    header = f"{date_str} ({shift_type_label(st)} зміна)\n"
    summ = get_shift_summary(summary_rows, date_str, st)
    if summ:
        header += f"Загальний %: {summ['total_percent'] or '-'} | Агенція %: {summ['agency_percent'] or '-'}\n"
    avg = compute_shift_avg(perf_rows, date_str, st)
    if avg is not None:
        header += f"Середній % по SAP: {fmt_percent(avg)}%\n"
    if not items:
        return header + "Немає працівників у зміні."

    perf_map = {(r["sap"], r["hala"], r["group"]): r["percent"] for r in perf_rows if r["date"] == date_str and safe_lower(r["shift_type"]) == safe_lower(st)}
    items = sorted(items, key=lambda r: (safe_lower(r["hala"]), safe_lower(r["group"]), safe_lower(r["surname"])))
    blocks = []
    cur = None
    lines = []
    for r in items:
        key = (r["hala"], r["group"])
        if cur != key:
            if lines:
                blocks.append("\n".join(lines))
            cur = key
            lines = [f"\n{r['hala']} / {r['group']}"]
        p = perf_map.get((r["sap"], r["hala"], r["group"]))
        tail = f" — {fmt_percent(p)}%" if p else ""
        lines.append(f"{r['sap']} — {r['surname']}{tail}")
    if lines:
        blocks.append("\n".join(lines))
    return (header + "\n".join(blocks)).strip()

def compute_month_averages(perf_rows, month):
    sums, cnts, names = {}, {}, {}
    for r in perf_rows:
        if month_key_from_date_str(r["date"]) != month:
            continue
        p = safe_float(r["percent"])
        if p is None or not r["sap"]:
            continue
        sums[r["sap"]] = sums.get(r["sap"], 0) + p
        cnts[r["sap"]] = cnts.get(r["sap"], 0) + 1
        names[r["sap"]] = r["surname"]
    return {sap: (sums[sap] / cnts[sap], cnts[sap], names.get(sap, "")) for sap in sums}

def format_sorted_workers(perf_rows, month):
    avgs = compute_month_averages(perf_rows, month)
    if not avgs:
        return f"Немає записів продуктивності за {month}."
    rows = sorted([(avg, cnt, sap, name) for sap, (avg, cnt, name) in avgs.items()], key=lambda x: x[0])
    return "📌 Сортування працівників за " + month + "\n\n" + "\n".join(
        f"{emoji_by_percent(avg)} {sap} — {name} — avg {fmt_percent(avg)}% ({cnt} зм.)"
        for avg, cnt, sap, name in rows
    )

# ==============================
# STATE PER USER
# ==============================

def st(context):
    ud = context.user_data
    ud.setdefault("mode", None)
    ud.setdefault("tmp", {})
    ud.setdefault("menu", "main")
    ud.setdefault("active_shift", None)
    return ud

def reset_state(context):
    ud = st(context)
    ud["mode"] = None
    ud["tmp"] = {}

def set_menu(context, menu):
    st(context)["menu"] = menu

def is_cancel(text):
    return safe_lower(text) in {safe_lower(BTN_CANCEL), "cancel", "скасувати"}

async def show_main_menu(update, context, text="Обери дію 👇"):
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def show_employee_menu(update, context, text="Меню: Працівник 👇"):
    await update.message.reply_text(text, reply_markup=EMPLOYEE_KB)

async def show_work_menu(update, context, text="Меню: Організація роботи 👇"):
    await update.message.reply_text(text, reply_markup=WORK_KB)

# ==============================
# COMMANDS
# ==============================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state(context)
    set_menu(context, "main")
    await show_main_menu(update, context, "Готово ✅")

async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id = {update.effective_chat.id}")

# ==============================
# EMPLOYEE FLOW
# ==============================

async def employee_flow(update, context, text):
    ud = st(context)
    rows = read_employees()

    if ud["mode"] == "add_wait_sap":
        if not re.fullmatch(r"\d{6,12}", text):
            await update.message.reply_text("SAP має бути тільки цифри, наприклад 51011071.")
            return
        if employee_by_sap(rows, text):
            await update.message.reply_text("❌ Такий SAP вже є в базі.")
            return
        ud["tmp"]["sap"] = text
        ud["mode"] = "add_wait_surname"
        await update.message.reply_text("Введи прізвище та ім'я:")
        return

    if ud["mode"] == "add_wait_surname":
        ud["tmp"]["surname"] = text.upper()
        ud["mode"] = "add_wait_locker"
        await update.message.reply_text("Шафка або '-' якщо немає:")
        return

    if ud["mode"] == "add_wait_locker":
        ud["tmp"]["locker"] = "" if text == "-" else text
        ud["mode"] = "add_wait_knife"
        await update.message.reply_text("Ніж: 1/2 = є, 0 = немає", reply_markup=ReplyKeyboardMarkup([["1", "2", "0"], [BTN_CANCEL]], resize_keyboard=True))
        return

    if ud["mode"] == "add_wait_knife":
        if text not in {"0", "1", "2"}:
            await update.message.reply_text("Введи 1, 2 або 0.")
            return
        ud["tmp"]["knife"] = text
        ud["mode"] = "add_wait_shoe_size"
        await update.message.reply_text("Розмір взуття або '-' якщо не вказано:")
        return

    if ud["mode"] == "add_wait_shoe_size":
        ud["tmp"]["shoe_size"] = "" if text == "-" else text
        ud["mode"] = "add_wait_shoe_type"
        await update.message.reply_text("Взуття: own = своє, agency = видано агенцією, unknown = не вказано",
                                        reply_markup=ReplyKeyboardMarkup([["own", "agency", "unknown"], [BTN_CANCEL]], resize_keyboard=True))
        return

    if ud["mode"] == "add_wait_shoe_type":
        if safe_lower(text) not in {"own", "agency", "unknown"}:
            await update.message.reply_text("Обери own / agency / unknown.")
            return
        ud["tmp"]["shoe_type"] = safe_lower(text)
        new_emp = ensure_employee_columns(ud["tmp"])
        write_employees(upsert_employee(rows, new_emp))
        await backup_everywhere(context, update.effective_chat.id, "add_employee", emp_display(new_emp))
        reset_state(context)
        await show_employee_menu(update, context, f"✅ Додано:\n{emp_display(new_emp)}")
        return

    if ud["mode"] == "card_wait_query":
        matches = find_employees(rows, text)
        if not matches:
            reset_state(context)
            await show_employee_menu(update, context, "❌ Не знайдено.")
            return
        if len(matches) > 1:
            await update.message.reply_text("Знайдено кілька. Введи точніше або SAP:\n\n" + "\n".join(emp_display(x) for x in matches[:20]))
            return
        reset_state(context)
        await update.message.reply_text(format_employee_card(matches[0], read_perf(force=True)), reply_markup=EMPLOYEE_KB)
        return

    if ud["mode"] == "edit_wait_query":
        matches = find_employees(rows, text)
        if not matches:
            reset_state(context)
            await show_employee_menu(update, context, "❌ Не знайдено.")
            return
        if len(matches) > 1:
            await update.message.reply_text("Знайдено кілька. Введи точніше або SAP:\n\n" + "\n".join(emp_display(x) for x in matches[:20]))
            return
        ud["tmp"]["sap"] = matches[0]["sap"]
        ud["mode"] = "edit_wait_surname"
        await update.message.reply_text("Нове прізвище або '-' без змін:")
        return

    if ud["mode"] == "edit_wait_surname":
        ud["tmp"]["surname"] = "" if text == "-" else text.upper()
        ud["mode"] = "edit_wait_locker"
        await update.message.reply_text("Нова шафка або '-' без змін:")
        return

    if ud["mode"] == "edit_wait_locker":
        ud["tmp"]["locker"] = "" if text == "-" else text
        ud["tmp"]["locker_keep"] = text == "-"
        ud["mode"] = "edit_wait_knife"
        await update.message.reply_text("Ніж: 1/2/0 або '-' без змін", reply_markup=ReplyKeyboardMarkup([["1", "2", "0", "-"], [BTN_CANCEL]], resize_keyboard=True))
        return

    if ud["mode"] == "edit_wait_knife":
        if text not in {"0", "1", "2", "-"}:
            await update.message.reply_text("Введи 1, 2, 0 або '-'.")
            return
        ud["tmp"]["knife"] = "" if text == "-" else text
        ud["mode"] = "edit_wait_shoe_size"
        await update.message.reply_text("Розмір взуття або '-' без змін:")
        return

    if ud["mode"] == "edit_wait_shoe_size":
        ud["tmp"]["shoe_size"] = "" if text == "-" else text
        ud["mode"] = "edit_wait_shoe_type"
        await update.message.reply_text("Взуття: own / agency / unknown або '-' без змін",
                                        reply_markup=ReplyKeyboardMarkup([["own", "agency", "unknown", "-"], [BTN_CANCEL]], resize_keyboard=True))
        return

    if ud["mode"] == "edit_wait_shoe_type":
        if safe_lower(text) not in {"own", "agency", "unknown", "-"}:
            await update.message.reply_text("Обери own / agency / unknown або '-'.")
            return
        emp = {"sap": ud["tmp"]["sap"]}
        for k in ["surname", "knife", "shoe_size"]:
            if ud["tmp"].get(k):
                emp[k] = ud["tmp"][k]
        if not ud["tmp"].get("locker_keep") and "locker" in ud["tmp"]:
            emp["locker"] = ud["tmp"]["locker"]
        if text != "-":
            emp["shoe_type"] = safe_lower(text)
        rows2 = upsert_employee(rows, emp)
        write_employees(rows2)
        await backup_everywhere(context, update.effective_chat.id, "edit_employee", f"SAP {emp['sap']}")
        reset_state(context)
        await show_employee_menu(update, context, "✅ Зміни збережено.")
        return

    if ud["mode"] == "delete_wait_query":
        matches = find_employees(rows, text)
        if not matches:
            reset_state(context)
            await show_employee_menu(update, context, "❌ Не знайдено.")
            return
        if len(matches) > 1:
            await update.message.reply_text("Знайдено кілька. Введи точніше або SAP:\n\n" + "\n".join(emp_display(x) for x in matches[:20]))
            return
        deleted = matches[0]
        write_employees([r for r in rows if r["sap"] != deleted["sap"]])
        await backup_everywhere(context, update.effective_chat.id, "delete_employee", emp_display(deleted))
        reset_state(context)
        await show_employee_menu(update, context, f"🗑️ Видалено:\n{emp_display(deleted)}")
        return

# ==============================
# WORK FLOW
# ==============================

async def work_flow(update, context, text):
    ud = st(context)
    employees = read_employees()
    shifts = read_shifts()
    perf = read_perf()

    if ud["mode"] == "work_create_date":
        date = extract_date_from_btn(text)
        if not parse_ddmmyyyy(date):
            await update.message.reply_text("Дата має бути DD.MM.YYYY.", reply_markup=date_kb())
            return
        ud["tmp"]["date"] = date
        ud["mode"] = "work_create_type"
        await update.message.reply_text("Тип зміни:", reply_markup=shift_type_kb())
        return

    if ud["mode"] == "work_create_type":
        typ = normalize_shift_type(text)
        if not typ:
            await update.message.reply_text("Обери day або night.", reply_markup=shift_type_kb())
            return
        ud["active_shift"] = {"date": ud["tmp"]["date"], "shift_type": typ}
        reset_state(context)
        await show_work_menu(update, context, f"✅ Активна зміна: {ud['active_shift']['date']} ({shift_type_label(typ)})")
        return

    if ud["mode"] == "work_show_date":
        date = extract_date_from_btn(text)
        if not parse_ddmmyyyy(date):
            await update.message.reply_text("Дата має бути DD.MM.YYYY.", reply_markup=date_kb())
            return
        ud["tmp"]["date"] = date
        ud["mode"] = "work_show_type"
        await update.message.reply_text("Тип зміни:", reply_markup=shift_type_kb())
        return

    if ud["mode"] == "work_show_type":
        typ = normalize_shift_type(text)
        if not typ:
            await update.message.reply_text("Обери day або night.")
            return
        date = ud["tmp"]["date"]
        ud["active_shift"] = {"date": date, "shift_type": typ}
        reset_state(context)
        await update.message.reply_text(format_shift(date, typ, read_shifts(True), read_perf(True), read_summary(True)), reply_markup=WORK_KB)
        return

    if ud["mode"] == "work_add_hala":
        hala = normalize_text(text)
        if hala not in {"HALA 1", "HALA 2", "HALA 3", "HALA 4"}:
            await update.message.reply_text("Обери HALA 1–4.", reply_markup=hala_kb())
            return
        ud["tmp"]["hala"] = hala
        ud["mode"] = "work_add_group"
        await update.message.reply_text("Введи групу/робоче місце, наприклад G1 або LINIA 2:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True))
        return

    if ud["mode"] == "work_add_group":
        ud["tmp"]["group"] = text
        ud["mode"] = "work_add_list"
        await update.message.reply_text("Встав список SAP або SAP - PRIZVYSHCHE IMIA, кожен з нового рядка:")
        return

    if ud["mode"] == "work_add_list":
        active = ud.get("active_shift")
        if not active:
            reset_state(context)
            await show_work_menu(update, context, "Спочатку створи/обери зміну.")
            return
        emp_by_sap = {e["sap"]: e for e in employees if e["sap"]}
        lines = [normalize_text(x) for x in (update.message.text or "").splitlines() if normalize_text(x)]
        added, missing = 0, []
        rows = read_shifts(True)
        for line in lines:
            parsed = parse_sap_name_line(line)
            sap = parsed[0] if parsed else normalize_text(line)
            emp = emp_by_sap.get(sap)
            if not emp:
                missing.append(line)
                continue
            exists = any(r["date"] == active["date"] and r["shift_type"] == active["shift_type"] and r["hala"] == ud["tmp"]["hala"] and r["group"] == ud["tmp"]["group"] and r["sap"] == sap for r in rows)
            if exists:
                continue
            rows.append(ensure_shift_columns({
                "date": active["date"],
                "shift_type": active["shift_type"],
                "hala": ud["tmp"]["hala"],
                "group": ud["tmp"]["group"],
                "sap": sap,
                "surname": emp["surname"],
            }))
            added += 1
        write_shifts(rows)
        await backup_everywhere(context, update.effective_chat.id, "shift_add_workers", f"+{added}")
        reset_state(context)
        msg = f"✅ Додано: {added}"
        if missing:
            msg += "\n\n⚠️ Не знайдено SAP:\n" + "\n".join(missing[:30])
        await show_work_menu(update, context, msg)
        return

    if ud["mode"] == "import_percent_wait_text":
        active = ud.get("active_shift")
        if not active:
            reset_state(context)
            await show_work_menu(update, context, "Спочатку створи/обери зміну.")
            return
        emp_by_sap = {e["sap"]: e for e in employees if e["sap"]}
        shift_rows = [r for r in read_shifts(True) if r["date"] == active["date"] and r["shift_type"] == active["shift_type"]]
        group_by_sap = {r["sap"]: (r["hala"], r["group"]) for r in shift_rows}
        parsed, bad, missing = [], [], []
        for line in (update.message.text or "").splitlines():
            p = parse_sap_percent_line(line)
            if not p:
                if normalize_text(line):
                    bad.append(line)
                continue
            sap, percent = p
            emp = emp_by_sap.get(sap)
            if not emp:
                missing.append(sap)
                continue
            hala, group = group_by_sap.get(sap, ("", ""))
            parsed.append({"date": active["date"], "shift_type": active["shift_type"], "hala": hala, "group": group, "sap": sap, "surname": emp["surname"], "percent": percent})

        if not parsed:
            await update.message.reply_text("Не знайшов рядків формату: 51009998 - 156,44")
            return

        # replace existing same shift + SAP
        old = read_perf(True)
        sap_set = {r["sap"] for r in parsed}
        kept = [r for r in old if not (r["date"] == active["date"] and r["shift_type"] == active["shift_type"] and r["sap"] in sap_set)]
        write_perf(kept + [ensure_perf_columns(r) for r in parsed])
        await backup_everywhere(context, update.effective_chat.id, "import_percent", f"{active['date']} {active['shift_type']} записів {len(parsed)}")
        reset_state(context)

        preview = "\n".join(f"{r['sap']} — {r['surname']} — {fmt_percent(r['percent'])}%" for r in parsed[:25])
        msg = f"✅ Імпортовано %: {len(parsed)}\n\n{preview}"
        if len(parsed) > 25:
            msg += f"\n... ще {len(parsed)-25}"
        if missing:
            msg += "\n\n⚠️ SAP не знайдено:\n" + "\n".join(missing[:20])
        if bad:
            msg += "\n\n⚠️ Не розпізнано рядки:\n" + "\n".join(bad[:10])
        await show_work_menu(update, context, msg)
        return

    if ud["mode"] == "work_set_group_hala":
        hala = normalize_text(text)
        if hala not in {"HALA 1", "HALA 2", "HALA 3", "HALA 4"}:
            await update.message.reply_text("Обери HALA 1–4.", reply_markup=hala_kb())
            return
        ud["tmp"]["hala"] = hala
        ud["mode"] = "work_set_group_name"
        await update.message.reply_text("Введи групу/робоче місце:")
        return

    if ud["mode"] == "work_set_group_name":
        ud["tmp"]["group"] = text
        ud["mode"] = "work_set_group_percent"
        await update.message.reply_text("Введи % для всієї групи:")
        return

    if ud["mode"] == "work_set_group_percent":
        p = safe_float(text)
        if p is None:
            await update.message.reply_text("Не схоже на число.")
            return
        active = ud.get("active_shift")
        rows_shift = [r for r in read_shifts(True) if r["date"] == active["date"] and r["shift_type"] == active["shift_type"] and r["hala"] == ud["tmp"]["hala"] and r["group"] == ud["tmp"]["group"]]
        old = read_perf(True)
        sap_set = {r["sap"] for r in rows_shift}
        kept = [r for r in old if not (r["date"] == active["date"] and r["shift_type"] == active["shift_type"] and r["sap"] in sap_set)]
        new = [{"date": active["date"], "shift_type": active["shift_type"], "hala": r["hala"], "group": r["group"], "sap": r["sap"], "surname": r["surname"], "percent": str(p)} for r in rows_shift]
        write_perf(kept + new)
        await backup_everywhere(context, update.effective_chat.id, "group_percent", f"{ud['tmp']['hala']}/{ud['tmp']['group']}={p}")
        reset_state(context)
        await show_work_menu(update, context, f"✅ Записано {fmt_percent(p)}% для {len(new)} працівників.")
        return

    if ud["mode"] == "work_sort_month":
        if text == "-":
            month = datetime.now().strftime("%m.%Y")
        else:
            dt = parse_mmyyyy(text)
            if not dt:
                await update.message.reply_text("Формат MM.YYYY або '-'.")
                return
            month = dt.strftime("%m.%Y")
        reset_state(context)
        await update.message.reply_text(format_sorted_workers(read_perf(True), month), reply_markup=WORK_KB)
        return

    if ud["mode"] == "work_export_date":
        date = extract_date_from_btn(text)
        if not parse_ddmmyyyy(date):
            await update.message.reply_text("Дата має бути DD.MM.YYYY.", reply_markup=date_kb())
            return
        ud["tmp"]["date"] = date
        ud["mode"] = "work_export_type"
        await update.message.reply_text("Тип зміни:", reply_markup=shift_type_kb())
        return

    if ud["mode"] == "work_export_type":
        typ = normalize_shift_type(text)
        if not typ:
            await update.message.reply_text("Обери day або night.")
            return
        date = ud["tmp"]["date"]
        content = format_shift(date, typ, read_shifts(True), read_perf(True), read_summary(True))
        filename = f"shift_{date.replace('.','-')}_{typ}.txt"
        path = os.path.join(BACKUP_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        reset_state(context)
        await context.bot.send_document(update.effective_chat.id, document=InputFile(path, filename=filename), caption="📝 Експорт зміни")
        await show_work_menu(update, context, "Готово ✅")
        return

    if ud["mode"] == "summary_date":
        date = extract_date_from_btn(text)
        if not parse_ddmmyyyy(date):
            await update.message.reply_text("Дата має бути DD.MM.YYYY.", reply_markup=date_kb())
            return
        ud["tmp"]["date"] = date
        ud["mode"] = "summary_type"
        await update.message.reply_text("Тип зміни:", reply_markup=shift_type_kb())
        return

    if ud["mode"] == "summary_type":
        typ = normalize_shift_type(text)
        if not typ:
            await update.message.reply_text("Обери day або night.")
            return
        ud["tmp"]["shift_type"] = typ
        ud["mode"] = "summary_total"
        await update.message.reply_text("Введи загальний %:")
        return

    if ud["mode"] == "summary_total":
        p = safe_float(text)
        if p is None:
            await update.message.reply_text("Не схоже на число.")
            return
        ud["tmp"]["total_percent"] = str(p)
        ud["mode"] = "summary_agency"
        await update.message.reply_text("Введи агенційний %:")
        return

    if ud["mode"] == "summary_agency":
        p = safe_float(text)
        if p is None:
            await update.message.reply_text("Не схоже на число.")
            return
        rows = read_summary(True)
        date, typ = ud["tmp"]["date"], ud["tmp"]["shift_type"]
        rows = [r for r in rows if not (r["date"] == date and r["shift_type"] == typ)]
        rows.append(ensure_summary_columns({"date": date, "shift_type": typ, "total_percent": ud["tmp"]["total_percent"], "agency_percent": str(p)}))
        write_summary(rows)
        await backup_everywhere(context, update.effective_chat.id, "summary", f"{date} {typ}")
        reset_state(context)
        await show_work_menu(update, context, "✅ % по зміні збережено.")
        return

# ==============================
# TEXT HANDLER
# ==============================

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = normalize_text(update.message.text)
    ud = st(context)

    if ud["mode"] and is_cancel(text):
        reset_state(context)
        if ud["menu"] == "employee":
            await show_employee_menu(update, context, "Скасовано ✅")
        elif ud["menu"] == "work":
            await show_work_menu(update, context, "Скасовано ✅")
        else:
            await show_main_menu(update, context, "Скасовано ✅")
        return

    if ud["mode"] == "restore_wait_file":
        await update.message.reply_text("Надішли CSV або ZIP файлом-документом.")
        return

    if ud["mode"]:
        if ud["menu"] == "employee":
            await employee_flow(update, context, text)
            return
        if ud["menu"] == "work":
            await work_flow(update, context, text)
            return

    # main
    if is_btn(text, BTN_EMPLOYEE_MENU):
        set_menu(context, "employee")
        reset_state(context)
        await show_employee_menu(update, context, "Меню: Працівник ✅")
        return

    if is_btn(text, BTN_WORK_MENU):
        set_menu(context, "work")
        reset_state(context)
        await show_work_menu(update, context, "Меню: Організація роботи ✅")
        return

    if is_btn(text, "Backup"):
        paths = await backup_everywhere(context, update.effective_chat.id, "manual")
        await update.message.reply_text("💾 Backup зроблено:\n" + "\n".join(os.path.basename(p) for p in paths), reply_markup=MAIN_KB)
        return

    if is_btn(text, "Seed SAP"):
        await backup_everywhere(context, update.effective_chat.id, "pre_seed_sap")
        count = merge_seed_sap()
        await backup_everywhere(context, update.effective_chat.id, "after_seed_sap")
        await show_main_menu(update, context, f"🧬 Seed SAP завершено ✅\nЗаписів у базі: {count}")
        return

    if is_btn(text, "Відновити"):
        ud["mode"] = "restore_wait_file"
        ud["tmp"] = {}
        set_menu(context, "main")
        await update.message.reply_text("Надішли ZIP backup або employees.csv файлом.")
        return

    # employee menu
    if ud["menu"] == "employee":
        rows = read_employees()
        if is_btn(text, "Статистика"):
            await update.message.reply_text(format_stats(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Всі"):
            await update.message.reply_text(format_all(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Картка"):
            ud["mode"] = "card_wait_query"; ud["tmp"] = {}
            await update.message.reply_text("Введи SAP або частину прізвища:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)); return
        if is_btn(text, "З шафкою"):
            await update.message.reply_text(format_with_locker(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Без шафки"):
            await update.message.reply_text(format_no_locker(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "З ножем"):
            await update.message.reply_text(format_with_knife(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Без ножа"):
            await update.message.reply_text(format_no_knife(rows), reply_markup=EMPLOYEE_KB); return
        if is_btn(text, "Додати працівника"):
            ud["mode"] = "add_wait_sap"; ud["tmp"] = {}
            await update.message.reply_text("Введи SAP:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)); return
        if is_btn(text, "Редагувати працівника"):
            ud["mode"] = "edit_wait_query"; ud["tmp"] = {}
            await update.message.reply_text("Введи SAP або частину прізвища:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)); return
        if is_btn(text, "Видалити працівника"):
            ud["mode"] = "delete_wait_query"; ud["tmp"] = {}
            await update.message.reply_text("Введи SAP або частину прізвища:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)); return
        if is_btn(text, BTN_BACK):
            set_menu(context, "main"); reset_state(context)
            await show_main_menu(update, context, "Назад ✅"); return
        await show_employee_menu(update, context); return

    # work menu
    if ud["menu"] == "work":
        if is_btn(text, "Створити зміну"):
            ud["mode"] = "work_create_date"; ud["tmp"] = {}
            await update.message.reply_text("Обери дату:", reply_markup=date_kb()); return
        if is_btn(text, "Показати зміну"):
            ud["mode"] = "work_show_date"; ud["tmp"] = {}
            await update.message.reply_text("Обери дату:", reply_markup=date_kb()); return
        if is_btn(text, "Додати працівників"):
            if not ud.get("active_shift"):
                await show_work_menu(update, context, "Спочатку створи/обери зміну."); return
            ud["mode"] = "work_add_hala"; ud["tmp"] = {}
            await update.message.reply_text("Обери зал:", reply_markup=hala_kb()); return
        if is_btn(text, "Імпорт %"):
            if not ud.get("active_shift"):
                await show_work_menu(update, context, "Спочатку створи/обери зміну."); return
            ud["mode"] = "import_percent_wait_text"; ud["tmp"] = {}
            await update.message.reply_text("Встав список:\n51009998 - 156,44\n51010002 - 156,44", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)); return
        if is_btn(text, "Внести %"):
            if not ud.get("active_shift"):
                await show_work_menu(update, context, "Спочатку створи/обери зміну."); return
            ud["mode"] = "work_set_group_hala"; ud["tmp"] = {}
            await update.message.reply_text("Обери зал:", reply_markup=hala_kb()); return
        if is_btn(text, "% по зміні"):
            ud["mode"] = "summary_date"; ud["tmp"] = {}
            await update.message.reply_text("Обери дату:", reply_markup=date_kb()); return
        if is_btn(text, "Сортування"):
            ud["mode"] = "work_sort_month"; ud["tmp"] = {}
            await update.message.reply_text("Введи місяць MM.YYYY або '-' для поточного:", reply_markup=ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)); return
        if is_btn(text, "Експорт"):
            ud["mode"] = "work_export_date"; ud["tmp"] = {}
            await update.message.reply_text("Обери дату:", reply_markup=date_kb()); return
        if is_btn(text, "Backup зміни"):
            paths = await backup_everywhere(context, update.effective_chat.id, "manual_shift")
            await update.message.reply_text("💾 Backup зроблено:\n" + "\n".join(os.path.basename(p) for p in paths), reply_markup=WORK_KB); return
        if is_btn(text, BTN_BACK):
            set_menu(context, "main"); reset_state(context)
            await show_main_menu(update, context, "Назад ✅"); return
        await show_work_menu(update, context); return

    await show_main_menu(update, context)

# ==============================
# DOCUMENT RESTORE
# ==============================

async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = st(context)
    if ud["mode"] != "restore_wait_file":
        await update.message.reply_text("Файл отримав, але зараз не режим відновлення. Натисни ♻️ Відновити з файлу.")
        return

    doc: Document = update.message.document
    fname = doc.file_name or ""
    low = fname.lower()
    if not (low.endswith(".csv") or low.endswith(".zip")):
        await update.message.reply_text("Потрібен CSV або ZIP.")
        return

    await backup_everywhere(context, update.effective_chat.id, "pre_restore")
    file = await doc.get_file()
    content = await file.download_as_bytearray()

    if low.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(bytes(content))) as z:
                restored = []
                for target in [os.path.basename(EMPLOYEES_DB_PATH), os.path.basename(SHIFTS_DB_PATH), os.path.basename(PERF_DB_PATH), os.path.basename(SHIFT_SUMMARY_DB_PATH)]:
                    if target in set(z.namelist()):
                        z.extract(target, path=".")
                        restored.append(target)
                _employee_cache["mtime"] = _shift_cache["mtime"] = _perf_cache["mtime"] = _summary_cache["mtime"] = None
            reset_state(context); set_menu(context, "main")
            await show_main_menu(update, context, "♻️ Відновлено з ZIP ✅\n" + ", ".join(restored))
        except Exception as e:
            await update.message.reply_text(f"❌ Помилка ZIP: {e}")
        return

    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(StringIO(text))
    rows = [ensure_employee_columns(r) for r in reader]
    rows = [r for r in rows if r["surname"] or r["sap"]]
    write_employees(rows)
    await backup_everywhere(context, update.effective_chat.id, "after_restore", f"Працівників: {len(rows)}")
    reset_state(context); set_menu(context, "main")
    await show_main_menu(update, context, f"♻️ employees.csv відновлено ✅\nЗаписів: {len(rows)}")

# ==============================
# PHOTO PLACEHOLDER
# ==============================

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Фото отримав.\n\nУ цій версії OCR ще не підключений. "
        "Поки використовуй 📥 Імпорт % SAP текстом:\n51009998 - 156,44"
    )

# ==============================
# MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    migrate_old_local_if_needed()
    ensure_all_files()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("chatid", cmd_chatid))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
