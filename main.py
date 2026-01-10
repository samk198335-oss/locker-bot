import os
import csv
import re
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

# ТЕСТОВИЙ донор (тільки для імпорту)
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ОСНОВНА база (локальна, з нею працюємо завжди)
DB_PATH = "base_data.csv"

# Адміни (username без @). Якщо пусто — адмін-перевірка вимкнена.
ADMIN_USERNAMES = set(filter(None, [
    # "admin1",
    # "admin2",
]))

# ==============================
# 🧱 UI
# ==============================

BTN_STATS = "📊 Статистика"
BTN_ALL = "👥 Всі"
BTN_LOCKER = "🗄️ З шафкою"
BTN_NO_LOCKER = "🚫 Без шафки"
BTN_KNIFE = "🔪 З ножем"
BTN_NO_KNIFE = "❌ Без ножа"

BTN_ADD = "➕ Додати працівника"
BTN_EDIT = "✏️ Редагувати працівника"
BTN_DELETE = "🗑 Видалити працівника"
BTN_IMPORT = "🔄 Імпорт з Google"

BTN_CANCEL = "⛔ Скасувати"

KNIFE_YES = "🔪 Є ніж"
KNIFE_NO = "❌ Нема ножа"
KNIFE_UNKNOWN = "❓ Невідомо"
KNIFE_KEEP = "↩️ Залишити як є"

MAIN_KB = ReplyKeyboardMarkup(
    [
        [BTN_STATS, BTN_ALL],
        [BTN_LOCKER, BTN_NO_LOCKER],
        [BTN_KNIFE, BTN_NO_KNIFE],
        [BTN_ADD, BTN_EDIT, BTN_DELETE],
        [BTN_IMPORT],
    ],
    resize_keyboard=True
)

CANCEL_KB = ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)

KNIFE_KB = ReplyKeyboardMarkup(
    [[KNIFE_YES, KNIFE_NO], [KNIFE_UNKNOWN, KNIFE_KEEP], [BTN_CANCEL]],
    resize_keyboard=True
)

# ==============================
# 🧰 HELPERS
# ==============================

def _safe_strip(v) -> str:
    return (v or "").strip()

def canon_key(name: str) -> str:
    """Ключ для порівняння записів: uppercase + стиск пробілів."""
    if not name:
        return ""
    name = re.sub(r"\s+", " ", name.strip())
    return name.upper()

def looks_like_canonical_upper_latin(name: str) -> bool:
    """
    Канонічний формат, який ти хочеш надалі:
    SURNAME NAME, LATIN, UPPERCASE
    """
    s = _safe_strip(name)
    return bool(re.fullmatch(r"[A-Z][A-Z\s'\-]+", s)) and len(s.split()) >= 2

def parse_knife(value: str):
    """
    1 -> є ніж
    0 -> нема
    None -> невідомо
    """
    v = _safe_strip(value).lower()
    if v in ("1", "yes", "+", "true", "так", "є", "имеется", "имеется всё", "имеется все"):
        return 1
    if v in ("0", "no", "-", "false", "ні", "нет", "немає", "нема"):
        return 0
    if v in ("2", "unknown", "невідомо", "неизвестно"):
        return None
    if v == "":
        return None
    return None

def normalize_locker(value: str):
    """None якщо шафки нема/порожньо/явно 'нет'."""
    v = _safe_strip(value)
    if not v:
        return None
    low = v.lower()
    if low in ("-", "нет", "no", "нема", "немає", "відсутня", "отсутствует"):
        return None
    return v

# ==============================
# ✅ CANON DISPLAY (підміна тільки для тих, хто вже канонічний у "Всі")
# ==============================

def build_canonical_map(all_rows: list[dict]) -> dict:
    """
    Беремо канонічні ПІБ з "Всі" (LATIN UPPERCASE 2+ слова) і робимо key->display.
    """
    canon = {}
    for r in all_rows:
        s = _safe_strip(r.get("surname"))
        if not s:
            continue
        if looks_like_canonical_upper_latin(s):
            canon[canon_key(s)] = s
    return canon

def display_name(raw_surname: str, canon_map: dict) -> str:
    """
    Якщо є канонічний відповідник у "Всі" -> показуємо канонічний.
    Інакше залишаємо як є (інших не чіпаємо).
    """
    raw = _safe_strip(raw_surname)
    if not raw:
        return ""
    return canon_map.get(canon_key(raw), raw)

# ==============================
# 🗃 LOCAL DB (base_data.csv)
# ==============================

DB_FIELDS = ["Address", "surname", "knife", "locker", "deleted"]

def ensure_db_exists():
    if os.path.exists(DB_PATH):
        return
    with open(DB_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DB_FIELDS)
        w.writeheader()

def read_db_rows() -> list[dict]:
    ensure_db_exists()
    rows = []
    with open(DB_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "Address": row.get("Address", ""),
                "surname": row.get("surname", ""),
                "knife": row.get("knife", ""),
                "locker": row.get("locker", ""),
                "deleted": row.get("deleted", "0") or "0",
            })
    return rows

def write_db_rows(rows: list[dict]):
    ensure_db_exists()
    with open(DB_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DB_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({
                "Address": r.get("Address", ""),
                "surname": r.get("surname", ""),
                "knife": r.get("knife", ""),
                "locker": r.get("locker", ""),
                "deleted": r.get("deleted", "0") or "0",
            })

def active_rows_unique() -> list[dict]:
    """
    Повертає активні (deleted!=1) рядки без дублікатів по canon_key(surname).
    """
    rows = read_db_rows()
    out = []
    seen = set()
    for r in rows:
        if _safe_strip(r.get("deleted")) == "1":
            continue
        s = _safe_strip(r.get("surname"))
        if not s:
            continue
        k = canon_key(s)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out

def find_active_by_name(input_name: str) -> dict | None:
    """
    Шукаємо працівника у базі по canon_key.
    """
    key = canon_key(input_name)
    for r in active_rows_unique():
        if canon_key(r.get("surname", "")) == key:
            return r
    return None

def upsert_employee(surname: str, locker: str, knife: str, address: str = ""):
    """
    Додає або оновлює працівника у base_data.csv (по canon_key).
    """
    rows = read_db_rows()
    key = canon_key(surname)

    updated = False
    for r in rows:
        if canon_key(r.get("surname", "")) == key:
            r["surname"] = surname
            r["locker"] = locker
            r["knife"] = knife
            r["Address"] = address or r.get("Address", "")
            r["deleted"] = "0"
            updated = True
            break

    if not updated:
        rows.append({
            "Address": address,
            "surname": surname,
            "knife": knife,
            "locker": locker,
            "deleted": "0",
        })

    write_db_rows(rows)

def soft_delete_employee(name: str) -> bool:
    rows = read_db_rows()
    key = canon_key(name)
    changed = False
    for r in rows:
        if canon_key(r.get("surname","")) == key and _safe_strip(r.get("deleted")) != "1":
            r["deleted"] = "1"
            changed = True
    if changed:
        write_db_rows(rows)
    return changed

# ==============================
# 🔐 ADMIN
# ==============================

def is_admin(update: Update) -> bool:
    if not ADMIN_USERNAMES:
        return True
    u = update.effective_user
    if not u or not u.username:
        return False
    return u.username in ADMIN_USERNAMES

def admin_only_text() -> str:
    return "⛔ Доступ тільки для адмінів."

def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update):
            await update.message.reply_text(admin_only_text(), reply_markup=MAIN_KB)
            return
        return await func(update, context)
    return wrapper

# ==============================
# 🔄 IMPORT FROM GOOGLE (donor)
# ==============================

def _norm_header(h: str) -> str:
    return (h or "").replace("\ufeff", "").strip().lower()

def _fetch_google_rows() -> list[dict]:
    r = requests.get(CSV_URL, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    f = StringIO(r.text)

    reader = csv.reader(f)
    try:
        headers = next(reader)
    except StopIteration:
        return []

    idx = {_norm_header(h): i for i, h in enumerate(headers)}

    def pick_index(*candidates):
        for c in candidates:
            if c in idx:
                return idx[c]
        return None

    i_address = pick_index("address", "адреса")
    i_surname = pick_index("surname", "прізвище", "прiзвище")
    i_knife = pick_index("knife", "ніж", "нiж")
    i_locker = pick_index("locker", "шафка", "номер шафки")

    rows = []
    for row in reader:
        def get(i):
            if i is None:
                return ""
            return row[i] if i < len(row) else ""

        rows.append({
            "Address": get(i_address),
            "surname": get(i_surname),
            "knife": get(i_knife),
            "locker": get(i_locker),
            "deleted": "0",
        })
    return rows

def import_from_google_overwrite_db() -> tuple[bool, str]:
    """
    Перезаписує base_data.csv даними з Google (донор).
    """
    try:
        src = _fetch_google_rows()
    except Exception as e:
        return False, f"❌ Помилка імпорту: {e}"

    # фільтруємо порожні surname
    clean = []
    for r in src:
        if _safe_strip(r.get("surname")):
            clean.append(r)

    ensure_db_exists()
    write_db_rows(clean)
    return True, f"✅ Імпорт завершено. Записів: {len(clean)}"

def ensure_db_initialized_once():
    """
    Якщо база порожня (тільки заголовок або файл відсутній) — зробимо стартовий імпорт 1 раз.
    """
    if not os.path.exists(DB_PATH):
        ensure_db_exists()
        ok, _ = import_from_google_overwrite_db()
        return

    # якщо файл існує, але практично порожній
    rows = read_db_rows()
    active = [r for r in rows if _safe_strip(r.get("surname")) and _safe_strip(r.get("deleted")) != "1"]
    if len(active) == 0:
        import_from_google_overwrite_db()

# ==============================
# 📨 HANDLERS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Обери дію кнопками нижче 👇",
        reply_markup=MAIN_KB
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = active_rows_unique()

    total = len(rows)
    with_knife = 0
    no_knife = 0
    unknown_knife = 0
    with_locker = 0
    no_locker = 0

    for r in rows:
        knife = parse_knife(r.get("knife", ""))
        locker = normalize_locker(r.get("locker", ""))

        if knife == 1:
            with_knife += 1
        elif knife == 0:
            no_knife += 1
        else:
            unknown_knife += 1

        if locker is None:
            no_locker += 1
        else:
            with_locker += 1

    text = (
        f"📊 Статистика:\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {with_knife}\n"
        f"❌ Без ножа: {no_knife}\n"
        f"❓ Невідомо: {unknown_knife}\n\n"
        f"🗄️ З шафкою: {with_locker}\n"
        f"🚫 Без шафки: {no_locker}"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    names = [display_name(r.get("surname",""), canon_map) for r in rows]
    names = [n for n in names if n]
    names.sort()

    text = "👥 Всі:\n\n" + "\n".join(names) if names else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        locker = normalize_locker(r.get("locker",""))
        if locker is None:
            continue
        name = display_name(r.get("surname",""), canon_map)
        items.append(f"{name} — {locker}")

    items.sort()
    text = "🗄️ З шафкою:\n\n" + "\n".join(items) if items else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        locker = normalize_locker(r.get("locker",""))
        if locker is not None:
            continue
        name = display_name(r.get("surname",""), canon_map)
        items.append(name)

    items.sort()
    text = "🚫 Без шафки:\n\n" + "\n".join(items) if items else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        if parse_knife(r.get("knife","")) != 1:
            continue
        name = display_name(r.get("surname",""), canon_map)
        items.append(name)

    items.sort()
    text = "🔪 З ножем:\n\n" + "\n".join(items) if items else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        if parse_knife(r.get("knife","")) != 0:
            continue
        name = display_name(r.get("surname",""), canon_map)
        items.append(name)

    items.sort()
    text = "❌ Без ножа:\n\n" + "\n".join(items) if items else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

# ==============================
# ✍️ FLOWS: add/edit/delete (local DB)
# ==============================

MODE_NONE = None
MODE_ADD_NAME = "add_name"
MODE_ADD_LOCKER = "add_locker"
MODE_ADD_KNIFE = "add_knife"

MODE_EDIT_TARGET = "edit_target"
MODE_EDIT_NEW_NAME = "edit_new_name"
MODE_EDIT_LOCKER = "edit_locker"
MODE_EDIT_KNIFE = "edit_knife"

MODE_DELETE_NAME = "delete_name"
MODE_DELETE_CONFIRM = "delete_confirm"

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_NONE
    for k in ("tmp_add", "tmp_edit", "tmp_delete"):
        context.user_data.pop(k, None)
    await update.message.reply_text("Скасовано ✅", reply_markup=MAIN_KB)

@require_admin
async def import_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, msg = import_from_google_overwrite_db()
    await update.message.reply_text(msg, reply_markup=MAIN_KB)

@require_admin
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_ADD_NAME
    context.user_data.pop("tmp_add", None)
    await update.message.reply_text(
        "➕ Введи ПІБ у форматі LATIN UPPERCASE: SURNAME NAME\nНапр: TROKHYMETS DMYTRO",
        reply_markup=CANCEL_KB
    )

@require_admin
async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_EDIT_TARGET
    context.user_data.pop("tmp_edit", None)
    await update.message.reply_text(
        "✏️ Введи ПІБ працівника, якого редагуємо (як є в базі):",
        reply_markup=CANCEL_KB
    )

@require_admin
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_DELETE_NAME
    context.user_data.pop("tmp_delete", None)
    await update.message.reply_text(
        "🗑 Введи ПІБ працівника, якого треба видалити:",
        reply_markup=CANCEL_KB
    )

@require_admin
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = _safe_strip(update.message.text)
    mode = context.user_data.get("mode")

    if text == BTN_CANCEL:
        return await cancel(update, context)

    # ---------------- ADD ----------------
    if mode == MODE_ADD_NAME:
        if not looks_like_canonical_upper_latin(text):
            await update.message.reply_text(
                "❌ Формат невірний.\nПотрібно: LATIN UPPERCASE 'SURNAME NAME'\nНапр: VOVK ANNA",
                reply_markup=CANCEL_KB
            )
            return
        context.user_data["tmp_add"] = {"surname": text}
        context.user_data["mode"] = MODE_ADD_LOCKER
        await update.message.reply_text("Введи шафку (номер/текст) або '-' якщо без:", reply_markup=CANCEL_KB)
        return

    if mode == MODE_ADD_LOCKER:
        locker = normalize_locker(text) or ""
        context.user_data["tmp_add"]["locker"] = locker
        context.user_data["mode"] = MODE_ADD_KNIFE
        await update.message.reply_text("Обери ніж:", reply_markup=KNIFE_KB)
        return

    if mode == MODE_ADD_KNIFE:
        if text == KNIFE_YES:
            knife_val = "1"
        elif text == KNIFE_NO:
            knife_val = "0"
        elif text == KNIFE_UNKNOWN:
            knife_val = "2"
        else:
            await update.message.reply_text("Обери кнопку для ножа 👇", reply_markup=KNIFE_KB)
            return

        data = context.user_data.get("tmp_add") or {}
        surname = data.get("surname", "")
        locker = data.get("locker", "")
        upsert_employee(surname=surname, locker=locker, knife=knife_val)

        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_add", None)
        await update.message.reply_text(
            f"✅ Додано/оновлено:\n{surname}\nШафка: {locker or '—'}\nНіж: {knife_val}",
            reply_markup=MAIN_KB
        )
        return

    # ---------------- EDIT (name + locker + knife) ----------------
    if mode == MODE_EDIT_TARGET:
        emp = find_active_by_name(text)
        if not emp:
            await update.message.reply_text("❌ Не знайдено в базі. Спробуй ще раз або скасуй.", reply_markup=CANCEL_KB)
            return
        context.user_data["tmp_edit"] = {
            "old_key": canon_key(emp.get("surname","")),
            "current": emp,
        }
        context.user_data["mode"] = MODE_EDIT_NEW_NAME
        await update.message.reply_text(
            "Введи НОВИЙ ПІБ у форматі LATIN UPPERCASE (або '-' щоб залишити як є):",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_EDIT_NEW_NAME:
        tmp = context.user_data.get("tmp_edit") or {}
        current = tmp.get("current") or {}
        new_name = text

        if new_name == "-":
            new_name = _safe_strip(current.get("surname",""))
        else:
            if not looks_like_canonical_upper_latin(new_name):
                await update.message.reply_text(
                    "❌ Невірний формат.\nПотрібно: LATIN UPPERCASE 'SURNAME NAME'\nАбо '-' щоб залишити як є.",
                    reply_markup=CANCEL_KB
                )
                return

        tmp["new_surname"] = new_name
        context.user_data["tmp_edit"] = tmp
        context.user_data["mode"] = MODE_EDIT_LOCKER
        await update.message.reply_text(
            "Введи НОВУ шафку (або '-' щоб залишити як є, або пусто/ 'нет' щоб прибрати):",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_EDIT_LOCKER:
        tmp = context.user_data.get("tmp_edit") or {}
        current = tmp.get("current") or {}
        if text == "-":
            locker = _safe_strip(current.get("locker",""))
        else:
            locker = normalize_locker(text) or ""  # якщо ввів "нет" -> стане ""
        tmp["new_locker"] = locker
        context.user_data["tmp_edit"] = tmp
        context.user_data["mode"] = MODE_EDIT_KNIFE
        await update.message.reply_text("Обери ніж (або ↩️ Залишити як є):", reply_markup=KNIFE_KB)
        return

    if mode == MODE_EDIT_KNIFE:
        tmp = context.user_data.get("tmp_edit") or {}
        current = tmp.get("current") or {}
        if text == KNIFE_KEEP:
            knife_val = _safe_strip(current.get("knife",""))
        elif text == KNIFE_YES:
            knife_val = "1"
        elif text == KNIFE_NO:
            knife_val = "0"
        elif text == KNIFE_UNKNOWN:
            knife_val = "2"
        else:
            await update.message.reply_text("Обери кнопку 👇", reply_markup=KNIFE_KB)
            return

        old_key = tmp.get("old_key","")
        new_surname = tmp.get("new_surname", _safe_strip(current.get("surname","")))
        new_locker = tmp.get("new_locker", _safe_strip(current.get("locker","")))
        address = _safe_strip(current.get("Address",""))

        # якщо змінюємо ПІБ -> старий запис помічаємо deleted, новий upsert
        rows = read_db_rows()
        for r in rows:
            if canon_key(r.get("surname","")) == old_key and _safe_strip(r.get("deleted")) != "1":
                # якщо ім'я не змінилось (той самий key), то просто оновимо цей рядок
                if canon_key(new_surname) == old_key:
                    r["surname"] = new_surname
                    r["locker"] = new_locker
                    r["knife"] = knife_val
                    r["deleted"] = "0"
                else:
                    r["deleted"] = "1"
        write_db_rows(rows)

        upsert_employee(surname=new_surname, locker=new_locker, knife=knife_val, address=address)

        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_edit", None)

        await update.message.reply_text(
            f"✅ Оновлено:\n{new_surname}\nШафка: {new_locker or '—'}\nНіж: {knife_val}",
            reply_markup=MAIN_KB
        )
        return

    # ---------------- DELETE ----------------
    if mode == MODE_DELETE_NAME:
        context.user_data["tmp_delete"] = {"name": text}
        context.user_data["mode"] = MODE_DELETE_CONFIRM
        await update.message.reply_text(
            f"Підтверди видалення:\n{text}\n\nНапиши: YES щоб підтвердити, або ⛔ Скасувати",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_DELETE_CONFIRM:
        tmp = context.user_data.get("tmp_delete") or {}
        name = tmp.get("name","")
        if text.upper() != "YES":
            await update.message.reply_text("Не підтверджено. Напиши YES або скасуй.", reply_markup=CANCEL_KB)
            return
        ok = soft_delete_employee(name)
        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_delete", None)
        await update.message.reply_text(
            f"✅ Видалено: {name}" if ok else f"❌ Не знайдено: {name}",
            reply_markup=MAIN_KB
        )
        return

    # ---------------- BUTTON ROUTER ----------------
    if text == BTN_STATS:
        return await stats(update, context)
    if text == BTN_ALL:
        return await list_all(update, context)
    if text == BTN_LOCKER:
        return await locker_list(update, context)
    if text == BTN_NO_LOCKER:
        return await no_locker_list(update, context)
    if text == BTN_KNIFE:
        return await knife_list(update, context)
    if text == BTN_NO_KNIFE:
        return await no_knife_list(update, context)

    if text == BTN_ADD:
        return await add_start(update, context)
    if text == BTN_EDIT:
        return await edit_start(update, context)
    if text == BTN_DELETE:
        return await delete_start(update, context)
    if text == BTN_IMPORT:
        return await import_start(update, context)

    await update.message.reply_text("Обери дію кнопками 👇", reply_markup=MAIN_KB)

# ==============================
# 🚀 MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    # 1) стартова ініціалізація локальної бази (1 раз, якщо порожньо)
    ensure_db_initialized_once()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # команди
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("all", list_all))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("import", import_start))  # адмін

    # кнопки/текст
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
