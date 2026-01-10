import os
import csv
import time
import re
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

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
CACHE_TTL = 300  # 5 хвилин

LOCAL_DB_PATH = "local_data.csv"  # локальна база для ручних правок/додавань/видалень

# Адміни (username без @). Якщо пусто — адмін-перевірка вимкнена.
ADMIN_USERNAMES = set(filter(None, [
    # "your_admin_username_1",
    # "your_admin_username_2",
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
BTN_EDIT = "✏️ Змінити прізвище"
BTN_DELETE = "🗑 Видалити працівника"
BTN_CANCEL = "⛔ Скасувати"

KNIFE_YES = "🔪 Є ніж"
KNIFE_NO = "❌ Нема ножа"
KNIFE_UNKNOWN = "❓ Невідомо"

MAIN_KB = ReplyKeyboardMarkup(
    [
        [BTN_STATS, BTN_ALL],
        [BTN_LOCKER, BTN_NO_LOCKER],
        [BTN_KNIFE, BTN_NO_KNIFE],
        [BTN_ADD, BTN_EDIT, BTN_DELETE],
    ],
    resize_keyboard=True
)

CANCEL_KB = ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)

KNIFE_KB = ReplyKeyboardMarkup(
    [[KNIFE_YES, KNIFE_NO], [KNIFE_UNKNOWN], [BTN_CANCEL]],
    resize_keyboard=True
)

# ==============================
# 🔁 CSV CACHE
# ==============================

_csv_cache = {"data": [], "time": 0}

def _safe_strip(v) -> str:
    return (v or "").strip()

def _fetch_remote_csv_rows() -> list[dict]:
    r = requests.get(CSV_URL, timeout=15)
    r.encoding = "utf-8"
    f = StringIO(r.text)
    reader = csv.DictReader(f)
    rows = []
    for row in reader:
        # очікувані колонки: Address, surname, knife, locker
        rows.append({
            "Address": row.get("Address", ""),
            "surname": row.get("surname", ""),
            "knife": row.get("knife", ""),
            "locker": row.get("locker", ""),
        })
    return rows

def load_remote_csv_cached() -> list[dict]:
    now = time.time()
    if _csv_cache["data"] and now - _csv_cache["time"] < CACHE_TTL:
        return _csv_cache["data"]
    data = _fetch_remote_csv_rows()
    _csv_cache["data"] = data
    _csv_cache["time"] = now
    return data

# ==============================
# 🗃 LOCAL DB (overlay)
# ==============================

def ensure_local_db():
    if os.path.exists(LOCAL_DB_PATH):
        return
    with open(LOCAL_DB_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["surname", "locker", "knife", "deleted"])
        w.writeheader()

def read_local_db() -> dict:
    """
    Повертає мапу за ключем canon_key(surname):
    {
      KEY: {"surname": "...", "locker": "...", "knife":"...", "deleted":"0/1"}
    }
    """
    ensure_local_db()
    out = {}
    with open(LOCAL_DB_PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            s = _safe_strip(row.get("surname"))
            if not s:
                continue
            key = canon_key(s)
            out[key] = {
                "surname": s,
                "locker": _safe_strip(row.get("locker")),
                "knife": _safe_strip(row.get("knife")),
                "deleted": _safe_strip(row.get("deleted")) or "0",
            }
    return out

def write_local_db(rows: list[dict]):
    ensure_local_db()
    with open(LOCAL_DB_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["surname", "locker", "knife", "deleted"])
        w.writeheader()
        for r in rows:
            w.writerow({
                "surname": r.get("surname", ""),
                "locker": r.get("locker", ""),
                "knife": r.get("knife", ""),
                "deleted": r.get("deleted", "0"),
            })

def upsert_local(surname: str, locker: str | None, knife: str | None, deleted: str = "0"):
    db = read_local_db()
    key = canon_key(surname)
    db[key] = {
        "surname": surname,
        "locker": locker or "",
        "knife": knife or "",
        "deleted": deleted,
    }
    write_local_db(list(db.values()))

def mark_deleted_local(surname: str):
    db = read_local_db()
    key = canon_key(surname)
    existing = db.get(key, {"surname": surname, "locker": "", "knife": "", "deleted": "0"})
    existing["deleted"] = "1"
    db[key] = existing
    write_local_db(list(db.values()))

# ==============================
# ✅ CANON DISPLAY (твоя вимога)
# ==============================

def canon_key(name: str) -> str:
    """Ключ порівняння: uppercase + стиск пробілів."""
    if not name:
        return ""
    name = re.sub(r"\s+", " ", name.strip())
    return name.upper()

def build_canonical_map(all_rows: list[dict]) -> dict:
    """
    Беремо канонічні ПІБ з "Всі":
    - LATIN
    - UPPERCASE
    - мінімум 2 слова
    і робимо мапу key -> canonical_display (сам текст ПІБ).
    """
    canon = {}
    for r in all_rows:
        s = _safe_strip(r.get("surname"))
        if not s:
            continue
        # Канонічний формат: тільки A-Z + пробіли + ' - (опційно), і 2+ слова
        if re.fullmatch(r"[A-Z][A-Z\s'\-]+", s) and len(s.split()) >= 2:
            canon[canon_key(s)] = s
    return canon

def display_name(raw_surname: str, canon_map: dict) -> str:
    """
    Якщо для цього запису існує канонічне ПІБ у "Всі" — показуємо канонічне.
    Інакше залишаємо як є (не чіпаємо).
    """
    raw = _safe_strip(raw_surname)
    if not raw:
        return ""
    return canon_map.get(canon_key(raw), raw)

# ==============================
# 🧮 PARSERS
# ==============================

def parse_knife(value: str):
    """
    Повертає:
    1 -> є ніж
    0 -> нема
    None -> невідомо/порожньо
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

    # якщо щось нестандартне — не ламаємось
    return None

def normalize_locker(value: str):
    """
    None якщо шафка не вказана або явно "немає".
    Інакше повертає текст як є (номер або "Так/Є/Ключ є/..." тощо).
    """
    v = _safe_strip(value)
    if not v:
        return None
    low = v.lower()
    if low in ("-", "нет", "no", "нема", "немає", "відсутня", "отсутствует"):
        return None
    return v

# ==============================
# 🧩 DATA MERGE (remote + local overlay)
# ==============================

def get_effective_rows() -> list[dict]:
    """
    Беремо remote Google CSV і накладаємо поверх local_data.csv:
    - якщо в local є запис для цього ПІБ (по canon_key) — він перезаписує knife/locker/surname
    - якщо deleted=1 — прибираємо з результату
    - якщо в local є новий ПІБ, якого немає в remote — додаємо
    """
    remote = load_remote_csv_cached()
    local = read_local_db()

    merged = []
    seen_keys = set()

    # 1) remote rows (overlaid)
    for r in remote:
        raw_s = _safe_strip(r.get("surname"))
        if not raw_s:
            continue
        key = canon_key(raw_s)
        seen_keys.add(key)

        loc = local.get(key)
        if loc and loc.get("deleted") == "1":
            continue

        if loc:
            merged.append({
                "Address": r.get("Address", ""),
                "surname": loc.get("surname", raw_s),
                "knife": loc.get("knife", r.get("knife", "")),
                "locker": loc.get("locker", r.get("locker", "")),
            })
        else:
            merged.append({
                "Address": r.get("Address", ""),
                "surname": raw_s,
                "knife": r.get("knife", ""),
                "locker": r.get("locker", ""),
            })

    # 2) local rows that are new (not in remote)
    for key, loc in local.items():
        if key in seen_keys:
            continue
        if loc.get("deleted") == "1":
            continue
        merged.append({
            "Address": "",
            "surname": loc.get("surname", ""),
            "knife": loc.get("knife", ""),
            "locker": loc.get("locker", ""),
        })

    return merged

def unique_by_key(rows: list[dict]) -> list[dict]:
    """
    Прибирає дублікати по canon_key(surname),
    залишає перший знайдений (плюс local overlay вже накладений).
    """
    out = []
    seen = set()
    for r in rows:
        s = _safe_strip(r.get("surname"))
        if not s:
            continue
        k = canon_key(s)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out

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

# ==============================
# 📨 HANDLERS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Обери дію кнопками нижче 👇",
        reply_markup=MAIN_KB
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = unique_by_key(get_effective_rows())
    canon_map = build_canonical_map(rows)  # не обов'язково для stats, але хай буде стабільно

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
    rows = unique_by_key(get_effective_rows())
    canon_map = build_canonical_map(rows)

    names = [display_name(r.get("surname",""), canon_map) for r in rows]
    names = [n for n in names if n]
    names.sort()

    text = "👥 Всі:\n\n" + "\n".join(names) if names else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = unique_by_key(get_effective_rows())
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
    rows = unique_by_key(get_effective_rows())
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
    rows = unique_by_key(get_effective_rows())
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        knife = parse_knife(r.get("knife",""))
        if knife != 1:
            continue
        name = display_name(r.get("surname",""), canon_map)
        items.append(name)

    items.sort()
    text = "🔪 З ножем:\n\n" + "\n".join(items) if items else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = unique_by_key(get_effective_rows())
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        knife = parse_knife(r.get("knife",""))
        if knife != 0:
            continue
        name = display_name(r.get("surname",""), canon_map)
        items.append(name)

    items.sort()
    text = "❌ Без ножа:\n\n" + "\n".join(items) if items else "Немає даних."
    await update.message.reply_text(text, reply_markup=MAIN_KB)

# ==============================
# ✍️ CRUD (local only)
# ==============================

MODE_NONE = None
MODE_ADD_NAME = "add_name"
MODE_ADD_LOCKER = "add_locker"
MODE_ADD_KNIFE = "add_knife"

MODE_EDIT_OLD = "edit_old"
MODE_EDIT_NEW = "edit_new"

MODE_DELETE_NAME = "delete_name"
MODE_DELETE_CONFIRM = "delete_confirm"

def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update):
            await update.message.reply_text(admin_only_text(), reply_markup=MAIN_KB)
            return
        return await func(update, context)
    return wrapper

@require_admin
async def add_employee_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_ADD_NAME
    context.user_data.pop("tmp_add", None)
    await update.message.reply_text(
        "➕ Введи ПІБ у форматі: SURNAME NAME (LATIN UPPERCASE)\nНапр: TROKHYMETS DMYTRO",
        reply_markup=CANCEL_KB
    )

@require_admin
async def edit_employee_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_EDIT_OLD
    context.user_data.pop("tmp_edit", None)
    await update.message.reply_text(
        "✏️ Введи ПІБ працівника, якого треба змінити (краще в форматі UPPERCASE):",
        reply_markup=CANCEL_KB
    )

@require_admin
async def delete_employee_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_DELETE_NAME
    context.user_data.pop("tmp_delete", None)
    await update.message.reply_text(
        "🗑 Введи ПІБ працівника, якого треба видалити (краще в UPPERCASE):",
        reply_markup=CANCEL_KB
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mode"] = MODE_NONE
    context.user_data.pop("tmp_add", None)
    context.user_data.pop("tmp_edit", None)
    context.user_data.pop("tmp_delete", None)
    await update.message.reply_text("Скасовано ✅", reply_markup=MAIN_KB)

def looks_like_canonical_upper_latin(name: str) -> bool:
    s = _safe_strip(name)
    return bool(re.fullmatch(r"[A-Z][A-Z\s'\-]+", s)) and len(s.split()) >= 2

@require_admin
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = _safe_strip(update.message.text)
    mode = context.user_data.get("mode")

    if text == BTN_CANCEL:
        return await cancel(update, context)

    # ---------------- ADD FLOW ----------------
    if mode == MODE_ADD_NAME:
        if not looks_like_canonical_upper_latin(text):
            await update.message.reply_text(
                "❌ Невірний формат.\nВведи так: SURNAME NAME (LATIN UPPERCASE)\nНапр: VOVK ANNA",
                reply_markup=CANCEL_KB
            )
            return
        context.user_data["tmp_add"] = {"surname": text}
        context.user_data["mode"] = MODE_ADD_LOCKER
        await update.message.reply_text(
            "Введи номер/значення шафки (або '-' якщо без шафки):",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_ADD_LOCKER:
        locker_in = text
        locker_norm = normalize_locker(locker_in)
        context.user_data["tmp_add"]["locker"] = locker_norm or ""
        context.user_data["mode"] = MODE_ADD_KNIFE
        await update.message.reply_text(
            "Обери ніж:",
            reply_markup=KNIFE_KB
        )
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
        upsert_local(surname=surname, locker=locker, knife=knife_val, deleted="0")

        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_add", None)

        await update.message.reply_text(
            f"✅ Додано/оновлено:\n{surname}\nШафка: {locker or '—'}\nНіж: {knife_val}",
            reply_markup=MAIN_KB
        )
        return

    # ---------------- EDIT FLOW ----------------
    if mode == MODE_EDIT_OLD:
        if not text:
            await update.message.reply_text("Введи ПІБ текстом.", reply_markup=CANCEL_KB)
            return
        context.user_data["tmp_edit"] = {"old": text}
        context.user_data["mode"] = MODE_EDIT_NEW
        await update.message.reply_text(
            "Введи новий ПІБ у форматі: SURNAME NAME (LATIN UPPERCASE)\nНапр: TROKHYMETS DMYTRO",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_EDIT_NEW:
        if not looks_like_canonical_upper_latin(text):
            await update.message.reply_text(
                "❌ Невірний формат нового ПІБ.\nВведи так: SURNAME NAME (LATIN UPPERCASE)\nНапр: VOVK ANNA",
                reply_markup=CANCEL_KB
            )
            return

        tmp = context.user_data.get("tmp_edit") or {}
        old_name = tmp.get("old", "")
        new_name = text

        # беремо поточні дані працівника (з merged), щоб НЕ втратити locker/knife
        rows = unique_by_key(get_effective_rows())
        old_key = canon_key(old_name)

        current = None
        for r in rows:
            if canon_key(r.get("surname","")) == old_key:
                current = r
                break

        if current is None:
            # якщо не знайшли — все одно дозволимо "перейменування" через local:
            # просто створимо новий запис, старий позначимо deleted
            mark_deleted_local(old_name)
            upsert_local(new_name, locker="", knife="2", deleted="0")
        else:
            locker = _safe_strip(current.get("locker",""))
            knife = _safe_strip(current.get("knife",""))
            mark_deleted_local(old_name)
            upsert_local(new_name, locker=locker, knife=knife, deleted="0")

        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_edit", None)

        await update.message.reply_text(
            f"✅ Змінено:\nБуло: {old_name}\nСтало: {new_name}",
            reply_markup=MAIN_KB
        )
        return

    # ---------------- DELETE FLOW ----------------
    if mode == MODE_DELETE_NAME:
        if not text:
            await update.message.reply_text("Введи ПІБ текстом.", reply_markup=CANCEL_KB)
            return
        context.user_data["tmp_delete"] = {"name": text}
        context.user_data["mode"] = MODE_DELETE_CONFIRM
        await update.message.reply_text(
            f"Підтверди видалення:\n{text}\n\nНапиши: YES щоб підтвердити, або натисни ⛔ Скасувати",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_DELETE_CONFIRM:
        tmp = context.user_data.get("tmp_delete") or {}
        name = tmp.get("name", "")
        if text.upper() != "YES":
            await update.message.reply_text("Не підтверджено. Напиши YES або скасуй.", reply_markup=CANCEL_KB)
            return
        mark_deleted_local(name)
        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_delete", None)
        await update.message.reply_text(f"✅ Видалено: {name}", reply_markup=MAIN_KB)
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
        return await add_employee_start(update, context)
    if text == BTN_EDIT:
        return await edit_employee_start(update, context)
    if text == BTN_DELETE:
        return await delete_employee_start(update, context)

    # якщо просто текст поза режимами
    await update.message.reply_text("Обери дію кнопками 👇", reply_markup=MAIN_KB)

# ==============================
# 🚀 MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("all", list_all))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
