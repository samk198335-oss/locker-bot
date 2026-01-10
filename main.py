import os
import csv
import re
import shutil
import threading
from io import BytesIO, StringIO
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests

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

DB_PATH = "base_data.csv"
BACKUP_DIR = "backups"
BACKUP_KEEP_LAST = int(os.getenv("BACKUP_KEEP_LAST", "200"))

# Донор для аварійного /seed (тільки коли база порожня!)
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ✅ БЕЗ АДМІНІВ (всі можуть користуватись)
ADMIN_USERNAMES = set()  # залишаємо пустим

# ==============================
# 🧱 UI
# ==============================

BTN_STATS = "📊 Статистика"
BTN_ALL = "👥 Всі"
BTN_LOCKER = "🗄️ З шафкою"
BTN_NO_LOCKER = "🚫 Без шафки"
BTN_KNIFE = "🔪 З ножем"
BTN_NO_KNIFE = "❌ Без ножа"

BTN_SEARCH = "🔎 Пошук"

BTN_ADD = "➕ Додати працівника"
BTN_EDIT = "✏️ Редагувати працівника"
BTN_DELETE = "🗑 Видалити працівника"

BTN_BACKUP = "💾 Backup бази"
BTN_RESTORE = "♻️ Відновити з файлу"

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
        [BTN_SEARCH],
        [BTN_ADD, BTN_EDIT, BTN_DELETE],
        [BTN_BACKUP, BTN_RESTORE],
    ],
    resize_keyboard=True
)

CANCEL_KB = ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)

KNIFE_KB = ReplyKeyboardMarkup(
    [[KNIFE_YES, KNIFE_NO], [KNIFE_UNKNOWN, KNIFE_KEEP], [BTN_CANCEL]],
    resize_keyboard=True
)

# ==============================
# 🔐 ACCESS (no admins for now)
# ==============================

def is_admin(update: Update) -> bool:
    if not ADMIN_USERNAMES:
        return True
    u = update.effective_user
    return bool(u and u.username and u.username in ADMIN_USERNAMES)

def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # адмін-перевірка вимкнена, але лишаємо як каркас на майбутнє
        if not is_admin(update):
            await update.message.reply_text("⛔ Доступ тільки для адмінів.", reply_markup=MAIN_KB)
            return
        return await func(update, context)
    return wrapper

# ==============================
# 🧠 CHATS REGISTRY (для авто-backup на 3 телефони)
# ==============================

MAX_BACKUP_CHATS = 10  # можна не чіпати

def register_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None:
        return
    s = context.bot_data.get("backup_chat_ids")
    if not isinstance(s, set):
        s = set()
    s.add(chat_id)

    # легка "ротація" щоб не розростався
    if len(s) > MAX_BACKUP_CHATS:
        # залишаємо будь-які MAX_BACKUP_CHATS
        s = set(list(s)[:MAX_BACKUP_CHATS])

    context.bot_data["backup_chat_ids"] = s

def get_backup_chat_ids(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    s = context.bot_data.get("backup_chat_ids")
    if isinstance(s, set):
        return list(s)
    return []

# ==============================
# 🧰 HELPERS
# ==============================

def _safe_strip(v) -> str:
    return (v or "").strip()

def canon_key(name: str) -> str:
    if not name:
        return ""
    name = re.sub(r"\s+", " ", name.strip())
    return name.upper()

def looks_like_canonical_upper_latin(name: str) -> bool:
    s = _safe_strip(name)
    return bool(re.fullmatch(r"[A-Z][A-Z\s'\-]+", s)) and len(s.split()) >= 2

def parse_knife(value: str):
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
    v = _safe_strip(value)
    if not v:
        return None
    low = v.lower()
    if low in ("-", "нет", "no", "нема", "немає", "відсутня", "отсутствует"):
        return None
    return v

def knife_label(v: str) -> str:
    k = parse_knife(v)
    if k == 1:
        return "🔪"
    if k == 0:
        return "❌"
    return "❓"

# ==============================
# ✅ CANON DISPLAY
# ==============================

def build_canonical_map(all_rows: list[dict]) -> dict:
    canon = {}
    for r in all_rows:
        s = _safe_strip(r.get("surname"))
        if not s:
            continue
        if looks_like_canonical_upper_latin(s):
            canon[canon_key(s)] = s
    return canon

def display_name(raw_surname: str, canon_map: dict) -> str:
    raw = _safe_strip(raw_surname)
    if not raw:
        return ""
    return canon_map.get(canon_key(raw), raw)

# ==============================
# 🗃 LOCAL DB + BACKUPS (FREE)
# ==============================

DB_FIELDS = ["Address", "surname", "knife", "locker", "deleted"]

def ensure_dirs():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def ensure_db_exists():
    ensure_dirs()
    if os.path.exists(DB_PATH):
        return
    with open(DB_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DB_FIELDS)
        w.writeheader()

def _timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")

def _rotate_backups_keep_last(n: int):
    try:
        files = []
        for fn in os.listdir(BACKUP_DIR):
            if fn.lower().endswith(".csv") and fn.startswith("base_data_"):
                files.append(os.path.join(BACKUP_DIR, fn))
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in files[n:]:
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass

def backup_db(reason: str = "auto") -> tuple[bool, str]:
    ensure_db_exists()
    if not os.path.exists(DB_PATH):
        return False, "DB file not found"

    ts = _timestamp()
    safe_reason = re.sub(r"[^a-zA-Z0-9_\-]+", "_", reason or "auto")[:30]
    dst = os.path.join(BACKUP_DIR, f"base_data_{ts}_{safe_reason}.csv")
    try:
        shutil.copy2(DB_PATH, dst)
        _rotate_backups_keep_last(BACKUP_KEEP_LAST)
        return True, dst
    except Exception as e:
        return False, str(e)

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

def write_db_rows_atomic(rows: list[dict]):
    ensure_db_exists()
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
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
    os.replace(tmp, DB_PATH)

def dedupe_keep_last(rows: list[dict]) -> list[dict]:
    best = {}
    order = []
    for r in rows:
        s = _safe_strip(r.get("surname"))
        if not s:
            continue
        k = canon_key(s)
        if k not in best:
            order.append(k)
        best[k] = r
    return [best[k] for k in order]

def active_rows_unique() -> list[dict]:
    rows = dedupe_keep_last(read_db_rows())
    out = []
    for r in rows:
        if _safe_strip(r.get("deleted")) == "1":
            continue
        if not _safe_strip(r.get("surname")):
            continue
        out.append(r)
    return out

def find_active_by_name(input_name: str) -> dict | None:
    key = canon_key(input_name)
    for r in active_rows_unique():
        if canon_key(r.get("surname", "")) == key:
            return r
    return None

def upsert_employee(surname: str, locker: str, knife: str, address: str = ""):
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

    rows = dedupe_keep_last(rows)
    write_db_rows_atomic(rows)

def soft_delete_employee(name: str) -> bool:
    rows = read_db_rows()
    key = canon_key(name)
    changed = False
    for r in rows:
        if canon_key(r.get("surname", "")) == key and _safe_strip(r.get("deleted")) != "1":
            r["deleted"] = "1"
            changed = True
    if changed:
        rows = dedupe_keep_last(rows)
        write_db_rows_atomic(rows)
    return changed

async def send_db_file(update: Update, context: ContextTypes.DEFAULT_TYPE, caption: str):
    ensure_db_exists()
    if not os.path.exists(DB_PATH):
        await update.message.reply_text("❌ DB файл не знайдено.", reply_markup=MAIN_KB)
        return

    with open(DB_PATH, "rb") as f:
        data = f.read()

    bio = BytesIO(data)
    bio.name = f"base_data_{_timestamp()}.csv"
    await update.message.reply_document(document=bio, caption=caption, reply_markup=MAIN_KB)

async def notify_chats_backup(context: ContextTypes.DEFAULT_TYPE, reason: str):
    ok, path_or_err = backup_db(reason)
    if not ok:
        return

    chat_ids = get_backup_chat_ids(context)
    if not chat_ids:
        return

    try:
        with open(path_or_err, "rb") as f:
            data = f.read()
        for chat_id in chat_ids:
            bio = BytesIO(data)
            bio.name = os.path.basename(path_or_err)
            await context.bot.send_document(
                chat_id=chat_id,
                document=bio,
                caption=f"💾 Auto-backup ({reason}). Збережи файл ✅"
            )
    except Exception:
        pass

# ==============================
# ℹ️ EMPTY DB HINT
# ==============================

def empty_db_hint_text() -> str:
    return (
        "⚠️ База порожня (після деплою на Render Free файли стираються).\n\n"
        "✅ Як відновити:\n"
        "1) Натисни ♻️ Відновити з файлу і надішли CSV backup\n"
        "або\n"
        "2) Напиши /seed (аварійно підтягне з Google, тільки якщо база пуста)\n\n"
        "Порада: перед кожним оновленням коду тисни 💾 Backup бази."
    )

async def hint_if_empty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if len(active_rows_unique()) == 0:
        await update.message.reply_text(empty_db_hint_text(), reply_markup=MAIN_KB)
        return True
    return False

# ==============================
# 🔄 SEED FROM GOOGLE (тільки якщо база порожня)
# ==============================

def fetch_google_rows() -> list[dict]:
    r = requests.get(CSV_URL, timeout=20)
    r.raise_for_status()
    r.encoding = "utf-8"
    f = StringIO(r.text)

    reader = csv.reader(f)
    try:
        headers = next(reader)
    except StopIteration:
        return []

    def norm(h: str) -> str:
        return (h or "").replace("\ufeff", "").strip().lower()

    idx = {norm(h): i for i, h in enumerate(headers)}

    def pick(*names):
        for n in names:
            if n in idx:
                return idx[n]
        return None

    i_address = pick("address", "адреса")
    i_surname = pick("surname", "прізвище", "прiзвище", "піб")
    i_knife = pick("knife", "ніж", "нiж")
    i_locker = pick("locker", "шафка", "номер шафки")

    rows = []
    for row in reader:
        def get(i):
            if i is None or i >= len(row):
                return ""
            return row[i]

        surname = _safe_strip(get(i_surname))
        if not surname:
            continue

        rows.append({
            "Address": get(i_address),
            "surname": surname,
            "knife": get(i_knife),
            "locker": get(i_locker),
            "deleted": "0",
        })

    return rows

@require_admin
async def seed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)

    if len(active_rows_unique()) > 0:
        await update.message.reply_text("❌ Seed заборонений. База вже не порожня.", reply_markup=MAIN_KB)
        return

    try:
        src = fetch_google_rows()
        if not src:
            raise RuntimeError("Google CSV порожній або немає потрібних колонок")

        src = dedupe_keep_last(src)
        write_db_rows_atomic(src)

        await update.message.reply_text(f"✅ Базу відновлено з Google.\nЗаписів: {len(src)}", reply_markup=MAIN_KB)
        await notify_chats_backup(context, "seed")

    except Exception as e:
        await update.message.reply_text(f"❌ Помилка seed: {e}", reply_markup=MAIN_KB)

# ==============================
# 📨 LISTS / STATS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)

    # ✅ (1) /start не збиває restore-режим
    if context.user_data.get("mode") == "restore_wait_file":
        await update.message.reply_text(
            "♻️ Відновлення активне.\nНадішли CSV-файл бази (document) або натисни ⛔ Скасувати.",
            reply_markup=CANCEL_KB
        )
        return

    await update.message.reply_text("Привіт! Обери дію кнопками нижче 👇", reply_markup=MAIN_KB)
    await hint_if_empty(update, context)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    if await hint_if_empty(update, context):
        return

    rows = active_rows_unique()

    total = len(rows)
    with_knife = no_knife = unknown_knife = 0
    with_locker = no_locker = 0

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
    register_chat(update, context)
    if await hint_if_empty(update, context):
        return

    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    names = [display_name(r.get("surname", ""), canon_map) for r in rows]
    names = [n for n in names if n]
    names.sort()

    await update.message.reply_text(("👥 Всі:\n\n" + "\n".join(names)) if names else "Немає даних.", reply_markup=MAIN_KB)

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    if await hint_if_empty(update, context):
        return

    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        locker = normalize_locker(r.get("locker", ""))
        if locker is None:
            continue
        name = display_name(r.get("surname", ""), canon_map)
        items.append(f"{name} — {locker}")

    items.sort()
    await update.message.reply_text(("🗄️ З шафкою:\n\n" + "\n".join(items)) if items else "Немає даних.", reply_markup=MAIN_KB)

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    if await hint_if_empty(update, context):
        return

    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        if normalize_locker(r.get("locker", "")) is not None:
            continue
        items.append(display_name(r.get("surname", ""), canon_map))

    items = [x for x in items if x]
    items.sort()
    await update.message.reply_text(("🚫 Без шафки:\n\n" + "\n".join(items)) if items else "Немає даних.", reply_markup=MAIN_KB)

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    if await hint_if_empty(update, context):
        return

    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        if parse_knife(r.get("knife", "")) != 1:
            continue
        items.append(display_name(r.get("surname", ""), canon_map))

    items = [x for x in items if x]
    items.sort()
    await update.message.reply_text(("🔪 З ножем:\n\n" + "\n".join(items)) if items else "Немає даних.", reply_markup=MAIN_KB)

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    if await hint_if_empty(update, context):
        return

    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    items = []
    for r in rows:
        if parse_knife(r.get("knife", "")) != 0:
            continue
        items.append(display_name(r.get("surname", ""), canon_map))

    items = [x for x in items if x]
    items.sort()
    await update.message.reply_text(("❌ Без ножа:\n\n" + "\n".join(items)) if items else "Немає даних.", reply_markup=MAIN_KB)

# ==============================
# 🔎 SEARCH
# ==============================

def _match_query(hay: str, q: str) -> bool:
    return q.lower() in (hay or "").lower()

async def search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    q = _safe_strip(query)
    if not q or len(q) < 2:
        await update.message.reply_text("Введи мінімум 2 символи для пошуку.", reply_markup=CANCEL_KB)
        return

    rows = active_rows_unique()
    canon_map = build_canonical_map(rows)

    found = []
    for r in rows:
        name_raw = _safe_strip(r.get("surname", ""))
        if not name_raw:
            continue
        if _match_query(name_raw, q):
            name = display_name(name_raw, canon_map)
            locker = normalize_locker(r.get("locker", "")) or "—"
            k = knife_label(r.get("knife", ""))
            found.append(f"{name} — {locker} — {k}")

    found.sort()
    if not found:
        await update.message.reply_text("Нічого не знайдено 🤷", reply_markup=MAIN_KB)
        return

    found = found[:30]
    await update.message.reply_text("🔎 Результати:\n\n" + "\n".join(found), reply_markup=MAIN_KB)

@require_admin
async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    context.user_data["mode"] = "search_query"
    await update.message.reply_text("🔎 Введи частину ПІБ для пошуку (мін. 2 символи):", reply_markup=CANCEL_KB)

async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    q = " ".join(context.args) if context.args else ""
    await search_results(update, context, q)

# ==============================
# 💾 BACKUP / RESTORE
# ==============================

@require_admin
async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    ok, info = backup_db("manual")
    if not ok:
        await update.message.reply_text(f"❌ Backup не створено:\n{info}", reply_markup=MAIN_KB)
        return
    await send_db_file(update, context, caption="💾 Поточна база (CSV). Збережи файл ✅")

@require_admin
async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    context.user_data["mode"] = "restore_wait_file"
    await update.message.reply_text(
        "♻️ Відновлення:\nНадішли мені CSV-файл бази (base_data_*.csv) як ДОКУМЕНТ.\n"
        "Я перезапишу базу.\n\n⛔ Скасувати — кнопка нижче.",
        reply_markup=CANCEL_KB
    )

@require_admin
async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    mode = context.user_data.get("mode")
    if mode != "restore_wait_file":
        return

    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ Немає файлу.", reply_markup=CANCEL_KB)
        return

    fn = (doc.file_name or "").lower()
    if not fn.endswith(".csv"):
        await update.message.reply_text("❌ Потрібен .csv файл.", reply_markup=CANCEL_KB)
        return

    try:
        tg_file = await doc.get_file()
        data = await tg_file.download_as_bytearray()

        if os.path.exists(DB_PATH):
            backup_db("before_restore")

        ensure_db_exists()
        tmp = DB_PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, DB_PATH)

        _ = read_db_rows()
        backup_db("after_restore")

        context.user_data["mode"] = None
        await update.message.reply_text(f"✅ Відновлено! Активних: {len(active_rows_unique())}", reply_markup=MAIN_KB)
        await notify_chats_backup(context, "restore")

    except Exception as e:
        context.user_data["mode"] = None
        await update.message.reply_text(f"❌ Помилка відновлення: {e}", reply_markup=MAIN_KB)

# ==============================
# ✍️ FLOWS: add/edit/delete + router
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
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    context.user_data["mode"] = MODE_ADD_NAME
    context.user_data.pop("tmp_add", None)
    await update.message.reply_text(
        "➕ Введи ПІБ у форматі LATIN UPPERCASE: SURNAME NAME\nНапр: BRAHA VIKTOR",
        reply_markup=CANCEL_KB
    )

@require_admin
async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    context.user_data["mode"] = MODE_EDIT_TARGET
    context.user_data.pop("tmp_edit", None)
    await update.message.reply_text(
        "✏️ Введи ПІБ працівника, якого редагуємо (як є в базі):",
        reply_markup=CANCEL_KB
    )

@require_admin
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    context.user_data["mode"] = MODE_DELETE_NAME
    context.user_data.pop("tmp_delete", None)
    await update.message.reply_text(
        "🗑 Введи ПІБ працівника, якого треба видалити:",
        reply_markup=CANCEL_KB
    )

@require_admin
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update, context)
    text = _safe_strip(update.message.text)

    # глобальна відміна
    if text == BTN_CANCEL:
        return await cancel(update, context)

    mode = context.user_data.get("mode")

    # ✅ (1) поки restore активний — нічого не збиваємо
    if mode == "restore_wait_file":
        await update.message.reply_text(
            "♻️ Відновлення активне.\nНадішли CSV-файл бази як ДОКУМЕНТ або натисни ⛔ Скасувати.",
            reply_markup=CANCEL_KB
        )
        return

    # SEARCH flow
    if mode == "search_query":
        context.user_data["mode"] = MODE_NONE
        return await search_results(update, context, text)

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

        await notify_chats_backup(context, "add_or_upsert")

        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_add", None)

        await update.message.reply_text(
            f"✅ Додано/оновлено:\n{surname}\nШафка: {locker or '—'}\nНіж: {knife_val}",
            reply_markup=MAIN_KB
        )
        return

    # ---------------- EDIT ----------------
    if mode == MODE_EDIT_TARGET:
        emp = find_active_by_name(text)
        if not emp:
            await update.message.reply_text("❌ Не знайдено в базі. Введи ПІБ точно як у списку або скасуй.", reply_markup=CANCEL_KB)
            return
        context.user_data["tmp_edit"] = {"old_key": canon_key(emp.get("surname", "")), "current": emp}
        context.user_data["mode"] = MODE_EDIT_NEW_NAME
        await update.message.reply_text(
            "Введи НОВИЙ ПІБ у форматі LATIN UPPERCASE (або '-' щоб залишити як є):",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_EDIT_NEW_NAME:
        tmp = context.user_data.get("tmp_edit") or {}
        current = tmp.get("current") or {}
        if text == "-":
            new_name = _safe_strip(current.get("surname", ""))
        else:
            if not looks_like_canonical_upper_latin(text):
                await update.message.reply_text(
                    "❌ Невірний формат.\nПотрібно: LATIN UPPERCASE 'SURNAME NAME'\nАбо '-' щоб залишити як є.",
                    reply_markup=CANCEL_KB
                )
                return
            new_name = text

        tmp["new_surname"] = new_name
        context.user_data["tmp_edit"] = tmp
        context.user_data["mode"] = MODE_EDIT_LOCKER
        await update.message.reply_text(
            "Введи НОВУ шафку (або '-' щоб залишити як є, або 'нет' щоб прибрати):",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_EDIT_LOCKER:
        tmp = context.user_data.get("tmp_edit") or {}
        current = tmp.get("current") or {}
        if text == "-":
            new_locker = _safe_strip(current.get("locker", ""))
        else:
            new_locker = normalize_locker(text) or ""
        tmp["new_locker"] = new_locker
        context.user_data["tmp_edit"] = tmp
        context.user_data["mode"] = MODE_EDIT_KNIFE
        await update.message.reply_text("Обери ніж (або ↩️ Залишити як є):", reply_markup=KNIFE_KB)
        return

    if mode == MODE_EDIT_KNIFE:
        tmp = context.user_data.get("tmp_edit") or {}
        current = tmp.get("current") or {}

        if text == KNIFE_KEEP:
            knife_val = _safe_strip(current.get("knife", ""))
        elif text == KNIFE_YES:
            knife_val = "1"
        elif text == KNIFE_NO:
            knife_val = "0"
        elif text == KNIFE_UNKNOWN:
            knife_val = "2"
        else:
            await update.message.reply_text("Обери кнопку 👇", reply_markup=KNIFE_KB)
            return

        old_key = tmp.get("old_key", "")
        new_surname = tmp.get("new_surname", _safe_strip(current.get("surname", "")))
        new_locker = tmp.get("new_locker", _safe_strip(current.get("locker", "")))
        address = _safe_strip(current.get("Address", ""))

        if canon_key(new_surname) == old_key:
            upsert_employee(surname=new_surname, locker=new_locker, knife=knife_val, address=address)
        else:
            soft_delete_employee(_safe_strip(current.get("surname", "")))
            upsert_employee(surname=new_surname, locker=new_locker, knife=knife_val, address=address)

        await notify_chats_backup(context, "edit")

        context.user_data["mode"] = MODE_NONE
        context.user_data.pop("tmp_edit", None)

        await update.message.reply_text(
            f"✅ Оновлено:\n{new_surname}\nШафка: {new_locker or '—'}\nНіж: {knife_val}",
            reply_markup=MAIN_KB
        )
        return

    # ---------------- DELETE ----------------
    if mode == MODE_DELETE_NAME:
        if not text:
            await update.message.reply_text("Введи ПІБ текстом.", reply_markup=CANCEL_KB)
            return
        context.user_data["tmp_delete"] = {"name": text}
        context.user_data["mode"] = MODE_DELETE_CONFIRM
        await update.message.reply_text(
            f"Підтверди видалення:\n{text}\n\nНапиши: YES щоб підтвердити, або ⛔ Скасувати",
            reply_markup=CANCEL_KB
        )
        return

    if mode == MODE_DELETE_CONFIRM:
        tmp = context.user_data.get("tmp_delete") or {}
        name = tmp.get("name", "")
        if text.upper() != "YES":
            await update.message.reply_text("Не підтверджено. Напиши YES або скасуй.", reply_markup=CANCEL_KB)
            return
        ok = soft_delete_employee(name)

        await notify_chats_backup(context, "delete")

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

    if text == BTN_SEARCH:
        return await search_start(update, context)

    if text == BTN_ADD:
        return await add_start(update, context)
    if text == BTN_EDIT:
        return await edit_start(update, context)
    if text == BTN_DELETE:
        return await delete_start(update, context)

    if text == BTN_BACKUP:
        return await backup_command(update, context)
    if text == BTN_RESTORE:
        return await restore_command(update, context)

    await update.message.reply_text("Обери дію кнопками 👇", reply_markup=MAIN_KB)

# ==============================
# 🚀 MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    ensure_db_exists()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("all", list_all))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))

    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("restore", restore_command))
    app.add_handler(CommandHandler("find", find_command))

    # аварійне відновлення з Google (тільки коли база порожня)
    app.add_handler(CommandHandler("seed", seed_command))

    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
