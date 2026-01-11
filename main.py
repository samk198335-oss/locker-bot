import os
import csv
import re
import time
import shutil
import threading
import requests
from io import StringIO
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
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

DATA_FILE = "local_data.csv"
BACKUP_DIR = "backups"

CACHE_TTL = 120  # для seed з Google (щоб не дергати часто)
_google_cache = {"data": "", "time": 0}

# ==============================
# ✅ UI BUTTONS
# ==============================

BTN_STATS = "📊 Статистика"
BTN_ALL = "👥 Всі"
BTN_WITH_LOCKER = "🗄 З шафкою"
BTN_NO_LOCKER = "⛔️ Без шафки"
BTN_WITH_KNIFE = "🔪 З ножем"
BTN_NO_KNIFE = "🚫 Без ножа"

BTN_BACKUP = "💾 Backup бази"
BTN_SEED = "🧬 Seed з Google"
BTN_RESTORE = "♻️ Відновити з файлу"

BTN_ADD = "➕ Додати працівника"
BTN_EDIT = "✏️ Редагувати працівника"
BTN_DELETE = "🗑 Видалити працівника"

# add flow knife buttons
K_YES = "✅ Є ніж"
K_NO = "❌ Нема ножа"
K_UNK = "❓ Невідомо"
K_CANCEL = "↩️ Скасувати"

# edit menu
E_NAME = "✍️ Змінити прізвище"
E_LOCKER = "🗄 Змінити шафку"
E_KNIFE = "🔪 Змінити ніж"
E_DONE = "✅ Готово"
E_CANCEL = "↩️ Скасувати"

# delete confirm
D_CONFIRM = "✅ Так, видалити"
D_CANCEL = "↩️ Скасувати"

def main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [BTN_STATS, BTN_ALL],
        [BTN_WITH_LOCKER, BTN_NO_LOCKER],
        [BTN_WITH_KNIFE, BTN_NO_KNIFE],
        [BTN_ADD, BTN_EDIT],
        [BTN_DELETE],
        [BTN_BACKUP, BTN_SEED],
        [BTN_RESTORE],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def knife_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [K_YES, K_NO],
        [K_UNK],
        [K_CANCEL],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def edit_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [E_NAME, E_LOCKER],
        [E_KNIFE],
        [E_DONE],
        [E_CANCEL],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def delete_confirm_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [D_CONFIRM],
        [D_CANCEL],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==============================
# 🧠 NORMALIZERS / PARSERS
# ==============================

def norm_text(s: str) -> str:
    return (s or "").strip()

def norm_key(s: str) -> str:
    # for matching surnames: casefold + squeeze spaces
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.casefold()

def is_yes_token(v: str) -> bool:
    v = norm_key(v)
    return v in {"1", "yes", "y", "true", "так", "є", "имеется", "имеется все", "ключ є", "ключ", "да", "+"}

def is_no_token(v: str) -> bool:
    v = norm_key(v)
    return v in {"0", "no", "n", "false", "ні", "нет", "-", "—"}

def parse_knife(value: str) -> int:
    """
    returns:
      1 = has knife
      0 = no knife
      2 = unknown
    """
    v = norm_text(value)
    if v == "":
        return 2
    vk = norm_key(v)
    if vk in {"1", "2", "0"}:
        # legacy numeric
        n = int(vk)
        if n in (0, 1, 2):
            return n
    if is_yes_token(v):
        return 1
    if is_no_token(v):
        return 0
    return 2

def knife_to_str(n: int) -> str:
    return "1" if n == 1 else "0" if n == 0 else "2"

def has_locker(value: str) -> bool:
    v = norm_text(value)
    if v == "":
        return False
    vk = norm_key(v)
    # if user wrote obvious "no"
    if vk in {"0", "ні", "нет", "no", "false", "-", "—"}:
        return False
    return True

# ==============================
# 📦 LOCAL DATA (CSV)
# ==============================

def ensure_storage():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        # create empty with headers
        with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Address", "surname", "knife", "locker"])
            w.writeheader()

def read_local() -> list[dict]:
    ensure_storage()
    rows = []
    with open(DATA_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # keep only expected cols
            rows.append({
                "Address": r.get("Address", ""),
                "surname": r.get("surname", ""),
                "knife": r.get("knife", ""),
                "locker": r.get("locker", ""),
            })
    return rows

def write_local(rows: list[dict]):
    ensure_storage()
    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Address", "surname", "knife", "locker"])
        w.writeheader()
        for r in rows:
            w.writerow({
                "Address": r.get("Address", ""),
                "surname": r.get("surname", ""),
                "knife": r.get("knife", ""),
                "locker": r.get("locker", ""),
            })

def make_backup(reason: str = "auto") -> str:
    ensure_storage()
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "_", reason)[:30]
    dst = os.path.join(BACKUP_DIR, f"backup_{ts}_{safe_reason}.csv")
    shutil.copy2(DATA_FILE, dst)
    return dst

# ==============================
# 🌐 GOOGLE SEED
# ==============================

def fetch_google_csv() -> str:
    now = time.time()
    if _google_cache["data"] and now - _google_cache["time"] < CACHE_TTL:
        return _google_cache["data"]
    r = requests.get(CSV_URL, timeout=15)
    r.encoding = "utf-8"
    _google_cache["data"] = r.text
    _google_cache["time"] = now
    return r.text

def seed_from_google() -> tuple[bool, str]:
    try:
        txt = fetch_google_csv()
        # validate headers
        reader = csv.DictReader(StringIO(txt))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        required = {"Address", "surname", "knife", "locker"}
        if not required.issubset(set(headers)):
            return False, f"❌ У Google CSV нема потрібних колонок: {sorted(required)}\nЗнайдено: {headers}"
        # backup before overwrite
        make_backup("before_seed")
        rows = []
        for r in reader:
            rows.append({
                "Address": r.get("Address", "") or "",
                "surname": r.get("surname", "") or "",
                "knife": r.get("knife", "") or "",
                "locker": r.get("locker", "") or "",
            })
        write_local(rows)
        make_backup("after_seed")
        return True, f"✅ Seed успішний. Записів: {len(rows)}"
    except Exception as e:
        return False, f"❌ Seed помилка: {e}"

# ==============================
# 📊 STATS & LISTS
# ==============================

def build_stats(rows: list[dict]) -> str:
    total = 0
    knife_yes = knife_no = knife_unk = 0
    locker_yes = locker_no = 0

    for r in rows:
        sname = norm_text(r.get("surname", ""))
        if not sname:
            continue
        total += 1

        k = parse_knife(r.get("knife", ""))
        if k == 1:
            knife_yes += 1
        elif k == 0:
            knife_no += 1
        else:
            knife_unk += 1

        if has_locker(r.get("locker", "")):
            locker_yes += 1
        else:
            locker_no += 1

    return (
        "📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        "🔪 Ніж:\n"
        f"✅ Є: {knife_yes}\n"
        f"🚫 Нема: {knife_no}\n"
        f"❓ Невідомо: {knife_unk}\n\n"
        "🗄 Шафка:\n"
        f"✅ Є: {locker_yes}\n"
        f"⛔️ Нема: {locker_no}"
    )

def list_all(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = norm_text(r.get("surname", ""))
        if s:
            people.append(s)
    people = sorted(people, key=lambda x: x.casefold())
    if not people:
        return "Немає даних."
    return "👥 Всі:\n\n" + "\n".join(people)

def list_with_locker(rows: list[dict]) -> str:
    items = []
    for r in rows:
        s = norm_text(r.get("surname", ""))
        l = norm_text(r.get("locker", ""))
        if s and has_locker(l):
            items.append((s, l))
    items.sort(key=lambda x: x[0].casefold())
    if not items:
        return "Немає даних."
    return "🗄 З шафкою:\n\n" + "\n".join([f"{s} — {l}" for s, l in items])

def list_no_locker(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = norm_text(r.get("surname", ""))
        l = norm_text(r.get("locker", ""))
        if s and not has_locker(l):
            people.append(s)
    people.sort(key=lambda x: x.casefold())
    if not people:
        return "Немає даних."
    return "⛔️ Без шафки:\n\n" + "\n".join(people)

def list_with_knife(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = norm_text(r.get("surname", ""))
        if s and parse_knife(r.get("knife", "")) == 1:
            people.append(s)
    people.sort(key=lambda x: x.casefold())
    if not people:
        return "Немає даних."
    return "🔪 З ножем:\n\n" + "\n".join(people)

def list_no_knife(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = norm_text(r.get("surname", ""))
        if s and parse_knife(r.get("knife", "")) == 0:
            people.append(s)
    people.sort(key=lambda x: x.casefold())
    if not people:
        return "Немає даних."
    return "🚫 Без ножа:\n\n" + "\n".join(people)

# ==============================
# 🔎 FIND PERSON
# ==============================

def find_person_index(rows: list[dict], surname_query: str) -> int:
    q = norm_key(surname_query)
    if not q:
        return -1
    for i, r in enumerate(rows):
        if norm_key(r.get("surname", "")) == q:
            return i
    return -1

def suggest_similar(rows: list[dict], surname_query: str, limit: int = 8) -> list[str]:
    q = norm_key(surname_query)
    if not q:
        return []
    hits = []
    for r in rows:
        s = norm_text(r.get("surname", ""))
        if s and q in norm_key(s):
            hits.append(s)
    hits = sorted(set(hits), key=lambda x: x.casefold())
    return hits[:limit]

# ==============================
# 🤖 HANDLERS
# ==============================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_storage()
    await update.message.reply_text(
        "Привіт! Обери дію кнопками 👇",
        reply_markup=main_keyboard()
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_local()
    await update.message.reply_text(build_stats(rows), reply_markup=main_keyboard())

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # If user is in some flow, handle it elsewhere
    state = context.user_data.get("state")
    if state:
        await handle_flow(update, context)
        return

    rows = read_local()

    if text == BTN_STATS:
        await update.message.reply_text(build_stats(rows), reply_markup=main_keyboard())
        return

    if text == BTN_ALL:
        await update.message.reply_text(list_all(rows), reply_markup=main_keyboard())
        return

    if text == BTN_WITH_LOCKER:
        await update.message.reply_text(list_with_locker(rows), reply_markup=main_keyboard())
        return

    if text == BTN_NO_LOCKER:
        await update.message.reply_text(list_no_locker(rows), reply_markup=main_keyboard())
        return

    if text == BTN_WITH_KNIFE:
        await update.message.reply_text(list_with_knife(rows), reply_markup=main_keyboard())
        return

    if text == BTN_NO_KNIFE:
        await update.message.reply_text(list_no_knife(rows), reply_markup=main_keyboard())
        return

    if text == BTN_BACKUP:
        ensure_storage()
        path = make_backup("manual")
        await update.message.reply_text(f"💾 Backup зроблено: {path}", reply_markup=main_keyboard())
        return

    if text == BTN_SEED:
        ok, msg = seed_from_google()
        await update.message.reply_text(msg, reply_markup=main_keyboard())
        return

    if text == BTN_RESTORE:
        context.user_data["state"] = "restore_wait_file"
        await update.message.reply_text(
            "♻️ Надішли сюди CSV файлом (Document). Я відновлю базу з нього.\n\n"
            "⚠️ Потрібні колонки: Address, surname, knife, locker",
            reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True)
        )
        return

    # NEW: add/edit/delete
    if text == BTN_ADD:
        context.user_data["state"] = "add_wait_surname"
        context.user_data["tmp"] = {}
        await update.message.reply_text("➕ Введи прізвище та ім’я працівника:", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
        return

    if text == BTN_EDIT:
        context.user_data["state"] = "edit_wait_target"
        context.user_data["tmp"] = {}
        await update.message.reply_text("✏️ Введи прізвище та ім’я працівника, як в базі:", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
        return

    if text == BTN_DELETE:
        context.user_data["state"] = "delete_wait_target"
        context.user_data["tmp"] = {}
        await update.message.reply_text("🗑 Введи прізвище та ім’я працівника, як в базі:", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
        return

    # fallback
    await update.message.reply_text("Обери дію кнопками 👇", reply_markup=main_keyboard())

async def handle_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")
    tmp = context.user_data.get("tmp", {})

    # global cancel
    if text == K_CANCEL or text == E_CANCEL or text == D_CANCEL:
        context.user_data.clear()
        await update.message.reply_text("Скасовано ✅", reply_markup=main_keyboard())
        return

    # ------------- RESTORE -------------
    if state == "restore_wait_file":
        await update.message.reply_text("Надішли CSV саме файлом (Document), не текстом.", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
        return

    # ------------- ADD FLOW -------------
    if state == "add_wait_surname":
        sname = norm_text(text)
        if len(sname) < 2:
            await update.message.reply_text("Введи нормальне прізвище/ім’я (мінімум 2 символи).", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
            return
        rows = read_local()
        if find_person_index(rows, sname) != -1:
            await update.message.reply_text(
                "❌ Такий працівник вже є в базі.\n"
                "Введи інше ім’я або натисни «Скасувати».",
                reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True)
            )
            return
        tmp["surname"] = sname
        context.user_data["tmp"] = tmp
        context.user_data["state"] = "add_wait_locker"
        await update.message.reply_text(
            "🗄 Введи номер/текст шафки (або напиши «-» якщо шафки нема):",
            reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True)
        )
        return

    if state == "add_wait_locker":
        locker = norm_text(text)
        if locker == "":
            locker = "-"
        tmp["locker"] = locker
        context.user_data["tmp"] = tmp
        context.user_data["state"] = "add_wait_knife"
        await update.message.reply_text("🔪 Вкажи ніж:", reply_markup=knife_keyboard())
        return

    if state == "add_wait_knife":
        if text not in {K_YES, K_NO, K_UNK}:
            await update.message.reply_text("Натисни кнопку для ножа 👇", reply_markup=knife_keyboard())
            return
        knife = 1 if text == K_YES else 0 if text == K_NO else 2
        rows = read_local()
        # autobackup before
        make_backup("before_add")
        rows.append({
            "Address": "",
            "surname": tmp.get("surname", ""),
            "knife": knife_to_str(knife),
            "locker": tmp.get("locker", "-"),
        })
        write_local(rows)
        make_backup("after_add")

        context.user_data.clear()
        await update.message.reply_text(
            f"✅ Додано: {rows[-1]['surname']}\n"
            f"🗄 Шафка: {rows[-1]['locker']}\n"
            f"🔪 Ніж: {'Є' if knife==1 else 'Нема' if knife==0 else 'Невідомо'}",
            reply_markup=main_keyboard()
        )
        return

    # ------------- EDIT FLOW -------------
    if state == "edit_wait_target":
        target = norm_text(text)
        rows = read_local()
        idx = find_person_index(rows, target)
        if idx == -1:
            sim = suggest_similar(rows, target)
            if sim:
                await update.message.reply_text(
                    "❌ Не знайшов точного співпадіння.\nСхожі варіанти:\n- " + "\n- ".join(sim) +
                    "\n\nСкопіюй точне ім’я і надішли ще раз або «Скасувати».",
                    reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True)
                )
            else:
                await update.message.reply_text(
                    "❌ Не знайшов такого працівника. Перевір написання або «Скасувати».",
                    reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True)
                )
            return

        tmp["edit_idx"] = idx
        tmp["old_surname"] = rows[idx].get("surname", "")
        context.user_data["tmp"] = tmp
        context.user_data["state"] = "edit_choose_field"

        current = rows[idx]
        k = parse_knife(current.get("knife", ""))
        await update.message.reply_text(
            "✏️ Що змінюємо?\n\n"
            f"Поточні дані:\n"
            f"👤 {current.get('surname','')}\n"
            f"🗄 {current.get('locker','')}\n"
            f"🔪 {'Є' if k==1 else 'Нема' if k==0 else 'Невідомо'}",
            reply_markup=edit_keyboard()
        )
        return

    if state == "edit_choose_field":
        if text == E_DONE:
            context.user_data.clear()
            await update.message.reply_text("✅ Редагування завершено.", reply_markup=main_keyboard())
            return

        if text not in {E_NAME, E_LOCKER, E_KNIFE}:
            await update.message.reply_text("Обери, що змінюємо 👇", reply_markup=edit_keyboard())
            return

        tmp["field"] = text
        context.user_data["tmp"] = tmp

        if text == E_KNIFE:
            context.user_data["state"] = "edit_wait_knife"
            await update.message.reply_text("🔪 Вкажи новий стан ножа:", reply_markup=knife_keyboard())
            return

        if text == E_NAME:
            context.user_data["state"] = "edit_wait_new_name"
            await update.message.reply_text("✍️ Введи нове прізвище та ім’я:", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
            return

        if text == E_LOCKER:
            context.user_data["state"] = "edit_wait_new_locker"
            await update.message.reply_text("🗄 Введи нову шафку (або «-» щоб прибрати):", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
            return

    if state == "edit_wait_new_name":
        new_name = norm_text(text)
        if len(new_name) < 2:
            await update.message.reply_text("Мало символів. Введи нормальне ім’я.", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
            return

        rows = read_local()
        idx = tmp.get("edit_idx")
        if idx is None or idx < 0 or idx >= len(rows):
            context.user_data.clear()
            await update.message.reply_text("❌ Помилка стану. Почни знову.", reply_markup=main_keyboard())
            return

        # prevent duplicates (except itself)
        existing = find_person_index(rows, new_name)
        if existing != -1 and existing != idx:
            await update.message.reply_text("❌ Таке ім’я вже є в базі. Введи інше або «Скасувати».", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
            return

        make_backup("before_edit")
        rows[idx]["surname"] = new_name
        write_local(rows)
        make_backup("after_edit")

        await update.message.reply_text("✅ Прізвище змінено.", reply_markup=edit_keyboard())
        context.user_data["state"] = "edit_choose_field"
        return

    if state == "edit_wait_new_locker":
        new_locker = norm_text(text)
        if new_locker == "":
            new_locker = "-"
        rows = read_local()
        idx = tmp.get("edit_idx")
        if idx is None or idx < 0 or idx >= len(rows):
            context.user_data.clear()
            await update.message.reply_text("❌ Помилка стану. Почни знову.", reply_markup=main_keyboard())
            return

        make_backup("before_edit")
        rows[idx]["locker"] = new_locker
        write_local(rows)
        make_backup("after_edit")

        await update.message.reply_text("✅ Шафку змінено.", reply_markup=edit_keyboard())
        context.user_data["state"] = "edit_choose_field"
        return

    if state == "edit_wait_knife":
        if text not in {K_YES, K_NO, K_UNK}:
            await update.message.reply_text("Натисни кнопку 👇", reply_markup=knife_keyboard())
            return
        knife = 1 if text == K_YES else 0 if text == K_NO else 2

        rows = read_local()
        idx = tmp.get("edit_idx")
        if idx is None or idx < 0 or idx >= len(rows):
            context.user_data.clear()
            await update.message.reply_text("❌ Помилка стану. Почни знову.", reply_markup=main_keyboard())
            return

        make_backup("before_edit")
        rows[idx]["knife"] = knife_to_str(knife)
        write_local(rows)
        make_backup("after_edit")

        await update.message.reply_text("✅ Ніж оновлено.", reply_markup=edit_keyboard())
        context.user_data["state"] = "edit_choose_field"
        return

    # ------------- DELETE FLOW -------------
    if state == "delete_wait_target":
        target = norm_text(text)
        rows = read_local()
        idx = find_person_index(rows, target)
        if idx == -1:
            sim = suggest_similar(rows, target)
            if sim:
                await update.message.reply_text(
                    "❌ Не знайшов точного співпадіння.\nСхожі варіанти:\n- " + "\n- ".join(sim) +
                    "\n\nСкопіюй точне ім’я і надішли ще раз або «Скасувати».",
                    reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True)
                )
            else:
                await update.message.reply_text("❌ Не знайшов такого працівника. Перевір написання або «Скасувати».", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
            return

        tmp["delete_idx"] = idx
        tmp["delete_name"] = rows[idx].get("surname", "")
        context.user_data["tmp"] = tmp
        context.user_data["state"] = "delete_confirm"

        await update.message.reply_text(
            f"🗑 Точно видалити?\n\n👤 {tmp['delete_name']}",
            reply_markup=delete_confirm_keyboard()
        )
        return

    if state == "delete_confirm":
        if text != D_CONFIRM:
            await update.message.reply_text("Натисни підтвердження або «Скасувати».", reply_markup=delete_confirm_keyboard())
            return

        rows = read_local()
        idx = tmp.get("delete_idx")
        if idx is None or idx < 0 or idx >= len(rows):
            context.user_data.clear()
            await update.message.reply_text("❌ Помилка стану. Почни знову.", reply_markup=main_keyboard())
            return

        make_backup("before_delete")
        removed = rows.pop(idx)
        write_local(rows)
        make_backup("after_delete")

        context.user_data.clear()
        await update.message.reply_text(f"✅ Видалено: {removed.get('surname','')}", reply_markup=main_keyboard())
        return

    # unknown state fallback
    context.user_data.clear()
    await update.message.reply_text("❌ Щось пішло не так. Повернув у меню.", reply_markup=main_keyboard())

# ==============================
# ♻️ RESTORE FROM FILE (Document handler)
# ==============================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state")
    if state != "restore_wait_file":
        return

    doc = update.message.document
    if not doc:
        return

    if not (doc.file_name or "").lower().endswith(".csv"):
        await update.message.reply_text("❌ Потрібен саме .csv файл.", reply_markup=ReplyKeyboardMarkup([[K_CANCEL]], resize_keyboard=True))
        return

    try:
        tg_file = await doc.get_file()
        content = await tg_file.download_as_bytearray()
        text = content.decode("utf-8", errors="replace")

        reader = csv.DictReader(StringIO(text))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        required = {"Address", "surname", "knife", "locker"}
        if not required.issubset(set(headers)):
            await update.message.reply_text(
                f"❌ У файлі нема потрібних колонок: {sorted(required)}\nЗнайдено: {headers}",
                reply_markup=main_keyboard()
            )
            context.user_data.clear()
            return

        make_backup("before_restore")
        rows = []
        for r in reader:
            rows.append({
                "Address": r.get("Address", "") or "",
                "surname": r.get("surname", "") or "",
                "knife": r.get("knife", "") or "",
                "locker": r.get("locker", "") or "",
            })
        write_local(rows)
        make_backup("after_restore")

        context.user_data.clear()
        await update.message.reply_text(f"✅ Відновлено з файлу. Записів: {len(rows)}", reply_markup=main_keyboard())
    except Exception as e:
        context.user_data.clear()
        await update.message.reply_text(f"❌ Помилка відновлення: {e}", reply_markup=main_keyboard())

# ==============================
# 🚀 RUN
# ==============================

def build_app():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # restore file
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # main text handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    return app

if __name__ == "__main__":
    ensure_storage()
    app = build_app()
    app.run_polling(close_loop=False)
