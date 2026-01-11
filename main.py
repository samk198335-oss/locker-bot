import os
import csv
import time
import re
import threading
import requests
from io import StringIO
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==================================================
# 🔧 RENDER FREE STABILIZATION (HTTP PORT)
# ==================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

def run_http_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ==================================================
# 🔑 CONFIG
# ==================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

CSV_URL = os.environ.get(
    "CSV_URL",
    "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
).strip()

BACKUP_CHAT_ID = os.environ.get("BACKUP_CHAT_ID", "").strip()  # e.g. -1003573002174
SELF_PING_URL = os.environ.get("SELF_PING_URL", "").strip()

CACHE_TTL = int(os.environ.get("CACHE_TTL", "300"))

DATA_FILE = "base_data.csv"

# ==================================================
# 🧠 STATE (simple)
# ==================================================
# Якщо ти вже маєш інші “режими” додавання/редагування — їх можна інтегрувати пізніше.
_user_state = {}  # user_id -> dict

# ==================================================
# 🔁 CSV CACHE (для Google seed)
# ==================================================
_csv_cache = {"data": None, "ts": 0.0}

# ==================================================
# 🧩 Helpers
# ==================================================
def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def normalize_text(v: str) -> str:
    return (v or "").strip()

def normalize_key(v: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(v)).lower()

def parse_knife(v: str):
    """
    knife column: 1 / 0 / 2 or text variants.
    returns: 1 (yes), 0 (no), 2 (unknown/empty)
    """
    s = normalize_key(v)
    if s in ("1", "yes", "y", "так", "є", "+", "true", "on"):
        return 1
    if s in ("0", "no", "n", "ні", "нема", "-", "false", "off"):
        return 0
    if s in ("2", "unknown", "невідомо", "?", ""):
        return 2
    # якщо вписали щось дивне — вважаємо unknown, щоб не ламати списки
    return 2

def has_locker(v: str) -> bool:
    s = normalize_text(v)
    if not s:
        return False
    if normalize_key(s) in ("-", "нема", "ні", "no", "0"):
        return False
    return True

def ensure_columns(row: dict) -> dict:
    # жорстко по назвах колонок, як зафіксовано
    return {
        "Address": row.get("Address", ""),
        "surname": row.get("surname", ""),
        "knife": row.get("knife", ""),
        "locker": row.get("locker", ""),
    }

def read_local_db() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = []
            for r in reader:
                r = ensure_columns(r)
                # пропускаємо повністю пусті записи
                if not normalize_text(r["surname"]) and not normalize_text(r["Address"]):
                    continue
                rows.append(r)
            return rows
    except Exception:
        return []

def write_local_db(rows: list[dict]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["Address", "surname", "knife", "locker"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            r = ensure_columns(r)
            writer.writerow(r)

def local_db_is_empty() -> bool:
    rows = read_local_db()
    return len(rows) == 0

def load_google_csv_rows() -> list[dict]:
    now = time.time()
    if _csv_cache["data"] is not None and (now - _csv_cache["ts"] < CACHE_TTL):
        return _csv_cache["data"]

    resp = requests.get(CSV_URL, timeout=15)
    resp.encoding = "utf-8"
    text = resp.text
    reader = csv.DictReader(StringIO(text))
    rows = []
    for r in reader:
        rows.append(ensure_columns(r))
    _csv_cache["data"] = rows
    _csv_cache["ts"] = now
    return rows

# ==================================================
# 📌 Backup / Restore (Telegram pinned in group)
# ==================================================
async def backup_to_group(bot, reason: str = "manual") -> tuple[bool, str]:
    """
    Створює backup-файл і надсилає в BACKUP_CHAT_ID, потім pin.
    """
    if not BACKUP_CHAT_ID:
        return False, "BACKUP_CHAT_ID не заданий у Render Environment."

    rows = read_local_db()
    if not rows:
        return False, "Немає даних для backup (база порожня)."

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"base_data_{ts}.csv"

    # пишемо тимчасово
    with open(fname, "w", encoding="utf-8", newline="") as f:
        fieldnames = ["Address", "surname", "knife", "locker"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(ensure_columns(r))

    # пробуємо зняти попередній pin (якщо є)
    old_pin_id = None
    try:
        chat = await bot.get_chat(BACKUP_CHAT_ID)
        if getattr(chat, "pinned_message", None):
            old_pin_id = chat.pinned_message.message_id
    except Exception:
        old_pin_id = None

    caption = f"💾 Backup бази ({len(rows)} записів) • {now_ts()} • {reason}"
    try:
        msg = await bot.send_document(
            chat_id=BACKUP_CHAT_ID,
            document=open(fname, "rb"),
            caption=caption,
        )
        try:
            # pin new
            await bot.pin_chat_message(chat_id=BACKUP_CHAT_ID, message_id=msg.message_id, disable_notification=True)
            # unpin old (optional)
            if old_pin_id and old_pin_id != msg.message_id:
                try:
                    await bot.unpin_chat_message(chat_id=BACKUP_CHAT_ID, message_id=old_pin_id)
                except Exception:
                    pass
        except Exception:
            # якщо pin не вдався — не критично
            pass

        return True, f"Backup відправив у backup-групу і закріпив (pinned). Файл: {fname}"
    except Exception as e:
        return False, f"Не зміг надіслати backup у групу: {e}"
    finally:
        try:
            os.remove(fname)
        except Exception:
            pass

async def restore_from_group_pinned(bot) -> tuple[bool, str]:
    """
    Якщо в backup-групі є pinned message з CSV документом — завантажує і відновлює base_data.csv
    """
    if not BACKUP_CHAT_ID:
        return False, "BACKUP_CHAT_ID не заданий у Render Environment."

    try:
        chat = await bot.get_chat(BACKUP_CHAT_ID)
        pm = getattr(chat, "pinned_message", None)
        if not pm:
            return False, "У backup-групі немає pinned повідомлення."
        if not pm.document:
            return False, "Pinned повідомлення є, але там не файл-документ."
        if not (pm.document.file_name or "").lower().endswith(".csv"):
            # все одно дозволимо, але попередимо
            pass

        file = await bot.get_file(pm.document.file_id)
        await file.download_to_drive(custom_path=DATA_FILE)

        rows = read_local_db()
        if not rows:
            return False, "Файл завантажив, але база все одно порожня (перевір CSV)."

        return True, f"✅ Відновив базу з pinned backup: {pm.document.file_name} ({len(rows)} записів)"
    except Exception as e:
        return False, f"Не зміг відновити з backup-групи: {e}"

async def seed_from_google() -> tuple[bool, str]:
    try:
        rows = load_google_csv_rows()
        if not rows:
            return False, "Google CSV порожній."
        write_local_db(rows)
        return True, f"✅ Seed зроблено з Google: {len(rows)} записів"
    except Exception as e:
        return False, f"Seed з Google не вдався: {e}"

async def ensure_db_on_start(app) -> None:
    """
    Запускається один раз при старті: якщо база порожня після деплою —
    1) пробує відновити з pinned backup у Telegram,
    2) якщо не вийшло — пробує seed з Google.
    """
    bot = app.bot
    if not local_db_is_empty():
        return

    # 1) telegram pinned backup
    ok, msg = await restore_from_group_pinned(bot)
    if ok:
        return

    # 2) google seed
    ok2, _ = await seed_from_google()
    return

# ==================================================
# 📊 Stats & Lists (єдина логіка)
# ==================================================
def compute_stats(rows: list[dict]) -> dict:
    total = len(rows)
    knife_yes = 0
    knife_no = 0
    knife_unknown = 0
    locker_yes = 0
    locker_no = 0

    for r in rows:
        k = parse_knife(r.get("knife", ""))
        if k == 1:
            knife_yes += 1
        elif k == 0:
            knife_no += 1
        else:
            knife_unknown += 1

        if has_locker(r.get("locker", "")):
            locker_yes += 1
        else:
            locker_no += 1

    return {
        "total": total,
        "knife_yes": knife_yes,
        "knife_no": knife_no,
        "knife_unknown": knife_unknown,
        "locker_yes": locker_yes,
        "locker_no": locker_no,
    }

def format_person(r: dict, with_locker_number: bool = False) -> str:
    name = normalize_text(r.get("surname", ""))
    locker = normalize_text(r.get("locker", ""))
    if with_locker_number and has_locker(locker):
        return f"{name} — {locker}"
    return name

def list_all(rows: list[dict]) -> list[str]:
    out = [format_person(r) for r in rows if normalize_text(r.get("surname", ""))]
    return sorted(out, key=lambda x: x.lower())

def list_with_locker(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        if normalize_text(r.get("surname", "")) and has_locker(r.get("locker", "")):
            out.append(format_person(r, with_locker_number=True))
    return sorted(out, key=lambda x: x.lower())

def list_without_locker(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        if normalize_text(r.get("surname", "")) and not has_locker(r.get("locker", "")):
            out.append(format_person(r))
    return sorted(out, key=lambda x: x.lower())

def list_with_knife(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        if normalize_text(r.get("surname", "")) and parse_knife(r.get("knife", "")) == 1:
            out.append(format_person(r))
    return sorted(out, key=lambda x: x.lower())

def list_without_knife(rows: list[dict]) -> list[str]:
    out = []
    for r in rows:
        if normalize_text(r.get("surname", "")) and parse_knife(r.get("knife", "")) == 0:
            out.append(format_person(r))
    return sorted(out, key=lambda x: x.lower())

# ==================================================
# 🧷 UI
# ==================================================
MENU = ReplyKeyboardMarkup(
    [
        ["📊 Статистика", "👥 Всі"],
        ["🗄️ З шафкою", "⛔️ Без шафки"],
        ["🔪 З ножем", "⛔️ Без ножа"],
        ["💾 Backup бази", "🧬 Seed з Google"],
    ],
    resize_keyboard=True
)

# ==================================================
# 🤖 Handlers
# ==================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _user_state.pop(update.effective_user.id, None)  # скидаємо будь-які "режими", щоб не блокувало списки
    await update.message.reply_text(
        "Готово ✅\nОбери дію кнопками 👇",
        reply_markup=MENU
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_local_db()
    st = compute_stats(rows)
    txt = (
        f"📊 Статистика:\n\n"
        f"Всього: {st['total']}\n\n"
        f"🔪 Ніж:\n"
        f"✅ Є: {st['knife_yes']}\n"
        f"⛔️ Нема: {st['knife_no']}\n"
        f"❓ Невідомо: {st['knife_unknown']}\n\n"
        f"🗄️ Шафка:\n"
        f"✅ Є: {st['locker_yes']}\n"
        f"⛔️ Нема: {st['locker_no']}"
    )
    await update.message.reply_text(txt, reply_markup=MENU)

async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_local_db()
    items = list_all(rows)
    if not items:
        await update.message.reply_text("👥 Всі:\n\nНемає даних.", reply_markup=MENU)
        return
    await update.message.reply_text("👥 Всі:\n\n" + "\n".join(items), reply_markup=MENU)

async def cmd_with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_local_db()
    items = list_with_locker(rows)
    if not items:
        await update.message.reply_text("🗄️ З шафкою:\n\nНемає даних.", reply_markup=MENU)
        return
    await update.message.reply_text("🗄️ З шафкою:\n\n" + "\n".join(items), reply_markup=MENU)

async def cmd_without_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_local_db()
    items = list_without_locker(rows)
    if not items:
        await update.message.reply_text("⛔️ Без шафки:\n\nНемає даних.", reply_markup=MENU)
        return
    await update.message.reply_text("⛔️ Без шафки:\n\n" + "\n".join(items), reply_markup=MENU)

async def cmd_with_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_local_db()
    items = list_with_knife(rows)
    if not items:
        await update.message.reply_text("🔪 З ножем:\n\nНемає даних.", reply_markup=MENU)
        return
    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(items), reply_markup=MENU)

async def cmd_without_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_local_db()
    items = list_without_knife(rows)
    if not items:
        await update.message.reply_text("⛔️ Без ножа:\n\nНемає даних.", reply_markup=MENU)
        return
    await update.message.reply_text("⛔️ Без ножа:\n\n" + "\n".join(items), reply_markup=MENU)

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.UPLOAD_DOCUMENT)
    ok, msg = await backup_to_group(context.bot, reason="manual")
    await update.message.reply_text(("✅ " if ok else "⚠️ ") + msg, reply_markup=MENU)

async def cmd_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, msg = await seed_from_google()
    if ok:
        # після seed — одразу backup (щоб завжди був pinned)
        await backup_to_group(context.bot, reason="seed_from_google")
    await update.message.reply_text(("✅ " if ok else "⚠️ ") + msg, reply_markup=MENU)

async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ручне відновлення (на всяк випадок)
    await update.message.chat.send_action(ChatAction.DOWNLOAD_DOCUMENT)
    ok, msg = await restore_from_group_pinned(context.bot)
    await update.message.reply_text(("✅ " if ok else "⚠️ ") + msg, reply_markup=MENU)

async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id = {update.effective_chat.id}")

# ==================================================
# ✍️ Change operations (приклад) + AUTO BACKUP
# ==================================================
# Щоб “автобекап після кожної зміни” працював реально, нам треба викликати backup_to_group
# у місцях де ти міняєш базу (додати/видалити/редагувати).
#
# Нижче — дуже прості команди (за бажанням можемо інтегрувати у твої кнопки/кроки потім).

async def cmd_add_simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /add Прізвище Ім'я | locker=12 | knife=1 | Address=...
    мінімально: /add Прізвище Ім'я
    """
    text = update.message.text
    payload = text.replace("/add", "", 1).strip()
    if not payload:
        await update.message.reply_text(
            "Формат:\n/add Прізвище Ім'я | locker=12 | knife=1 | Address=...\n\n"
            "knife: 1/0/2",
            reply_markup=MENU
        )
        return

    parts = [p.strip() for p in payload.split("|")]
    name = parts[0].strip()
    locker = ""
    knife = ""
    addr = ""

    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            k = normalize_key(k)
            v = v.strip()
            if k == "locker":
                locker = v
            elif k == "knife":
                knife = v
            elif k == "address":
                addr = v

    rows = read_local_db()
    rows.append({"Address": addr, "surname": name, "knife": knife, "locker": locker})
    write_local_db(rows)

    # ✅ AUTO BACKUP після зміни
    await backup_to_group(context.bot, reason="add_or_change")

    await update.message.reply_text(f"✅ Додав: {name}", reply_markup=MENU)

# ==================================================
# 🌐 Self ping loop (optional)
# ==================================================
def keep_self_awake():
    if not SELF_PING_URL:
        return
    while True:
        try:
            requests.get(SELF_PING_URL, timeout=10)
        except Exception:
            pass
        time.sleep(600)  # 10 хв

if SELF_PING_URL:
    threading.Thread(target=keep_self_awake, daemon=True).start()

# ==================================================
# 🚀 MAIN
# ==================================================
async def post_init(app):
    # авто-відновлення/seed якщо база порожня після деплою
    await ensure_db_on_start(app)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("seed", cmd_seed))
    app.add_handler(CommandHandler("restore", cmd_restore))
    app.add_handler(CommandHandler("chatid", cmd_chatid))

    # simple add (example)
    app.add_handler(CommandHandler("add", cmd_add_simple))

    # buttons (text)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    app.run_polling(close_loop=False)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()

    # якщо десь залишився “режим” — не блокуємо кнопки
    _user_state.pop(update.effective_user.id, None)

    if txt == "📊 Статистика":
        return await cmd_stats(update, context)
    if txt == "👥 Всі":
        return await cmd_all(update, context)
    if txt == "🗄️ З шафкою":
        return await cmd_with_locker(update, context)
    if txt == "⛔️ Без шафки":
        return await cmd_without_locker(update, context)
    if txt == "🔪 З ножем":
        return await cmd_with_knife(update, context)
    if txt == "⛔️ Без ножа":
        return await cmd_without_knife(update, context)
    if txt == "💾 Backup бази":
        return await cmd_backup(update, context)
    if txt == "🧬 Seed з Google":
        return await cmd_seed(update, context)

    # fallback
    await update.message.reply_text("Не зрозумів. Натисни кнопку або /start", reply_markup=MENU)

if __name__ == "__main__":
    main()
