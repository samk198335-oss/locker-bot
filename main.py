import os
import csv
import time
import asyncio
import logging
import threading
from io import StringIO
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Tuple, Optional

import requests

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
# LOGGING
# ==================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("locker-bot")

# ==================================================
# RENDER FREE: SIMPLE HTTP SERVER (keeps service "healthy")
# ==================================================
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

# ==================================================
# CONFIG
# ==================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

CSV_URL = os.environ.get("CSV_URL", "").strip()  # optional seed source
BACKUP_CHAT_ID_RAW = os.environ.get("BACKUP_CHAT_ID", "").strip()  # required for auto-restore via pinned backup
SELF_PING_URL = os.environ.get("SELF_PING_URL", "").strip()  # optional (for uptime robot)

BASE_FILE = "local_data.csv"

CACHE_TTL = 300  # seconds for Google CSV cache
_google_cache = {"time": 0.0, "rows": []}  # type: ignore

# CSV columns (fixed)
COL_ADDRESS = "Address"
COL_SURNAME = "surname"
COL_KNIFE = "knife"
COL_LOCKER = "locker"

# ==================================================
# UI
# ==================================================
MAIN_KB = ReplyKeyboardMarkup(
    [
        ["📊 Статистика", "👥 Всі"],
        ["🗄️ З шафкою", "🚫 Без шафки"],
        ["🔪 З ножем", "🚫 Без ножа"],
        ["💾 Backup бази", "♻️ Seed з Google"],
    ],
    resize_keyboard=True,
)

# ==================================================
# HELPERS
# ==================================================
def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def normalize_str(s: str) -> str:
    return (s or "").strip()

def file_exists_and_not_empty(path: str) -> bool:
    try:
        return os.path.exists(path) and os.path.getsize(path) > 0
    except Exception:
        return False

def safe_int(s: str) -> Optional[int]:
    try:
        return int(str(s).strip())
    except Exception:
        return None

def parse_backup_chat_id() -> Optional[int]:
    if not BACKUP_CHAT_ID_RAW:
        return None
    try:
        return int(BACKUP_CHAT_ID_RAW)
    except Exception:
        return None

def read_csv_file(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for r in reader:
            # normalize required keys
            row = {
                COL_ADDRESS: normalize_str(r.get(COL_ADDRESS, "")),
                COL_SURNAME: normalize_str(r.get(COL_SURNAME, "")),
                COL_KNIFE: normalize_str(r.get(COL_KNIFE, "")),
                COL_LOCKER: normalize_str(r.get(COL_LOCKER, "")),
            }
            # skip completely empty lines
            if any(row.values()):
                rows.append(row)
        return rows

def write_csv_file(path: str, rows: List[Dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[COL_ADDRESS, COL_SURNAME, COL_KNIFE, COL_LOCKER])
        writer.writeheader()
        for r in rows:
            writer.writerow({
                COL_ADDRESS: normalize_str(r.get(COL_ADDRESS, "")),
                COL_SURNAME: normalize_str(r.get(COL_SURNAME, "")),
                COL_KNIFE: normalize_str(r.get(COL_KNIFE, "")),
                COL_LOCKER: normalize_str(r.get(COL_LOCKER, "")),
            })

def load_google_csv_cached() -> List[Dict[str, str]]:
    if not CSV_URL:
        return []
    now = time.time()
    if _google_cache["rows"] and now - _google_cache["time"] < CACHE_TTL:
        return _google_cache["rows"]

    resp = requests.get(CSV_URL, timeout=20)
    resp.raise_for_status()
    text = resp.text
    f = StringIO(text)
    reader = csv.DictReader(f)

    rows = []
    for r in reader:
        row = {
            COL_ADDRESS: normalize_str(r.get(COL_ADDRESS, "")),
            COL_SURNAME: normalize_str(r.get(COL_SURNAME, "")),
            COL_KNIFE: normalize_str(r.get(COL_KNIFE, "")),
            COL_LOCKER: normalize_str(r.get(COL_LOCKER, "")),
        }
        if any(row.values()):
            rows.append(row)

    _google_cache["rows"] = rows
    _google_cache["time"] = now
    return rows

def is_knife_yes(v: str) -> bool:
    # knife expected 1/0/2, but we are tolerant
    v = normalize_str(v).lower()
    return v in {"1", "yes", "y", "true", "так", "+", "є", "имеется", "наявний"}

def is_knife_no(v: str) -> bool:
    v = normalize_str(v).lower()
    return v in {"0", "no", "n", "false", "ні", "нет", "-"}

def is_locker_yes(v: str) -> bool:
    v0 = normalize_str(v)
    if not v0:
        return False
    low = v0.lower()
    if low in {"-", "0", "ні", "нет", "no", "нема", "немає"}:
        return False
    # any non-empty locker value counts as "has locker"
    return True

def is_locker_no(v: str) -> bool:
    return not is_locker_yes(v)

def format_people_list(rows: List[Dict[str, str]], with_locker_number: bool = False) -> str:
    lines = []
    for r in rows:
        name = normalize_str(r.get(COL_SURNAME, ""))
        if not name:
            continue
        if with_locker_number:
            locker = normalize_str(r.get(COL_LOCKER, ""))
            if locker:
                lines.append(f"{name} — {locker}")
            else:
                lines.append(name)
        else:
            lines.append(name)
    return "\n".join(lines) if lines else "Немає даних."

# ==================================================
# BACKUP/RESTORE CORE (Pinned message trick)
# ==================================================
async def restore_from_pinned_backup(app, backup_chat_id: int) -> Tuple[bool, str]:
    """
    Auto-restore by downloading DOCUMENT from pinned message in backup group.
    Works because getChat returns pinned_message even without history access.
    """
    try:
        chat = await app.bot.get_chat(backup_chat_id)
        pinned = getattr(chat, "pinned_message", None)
        if not pinned:
            return False, "У backup-групі немає закріпленого (pinned) повідомлення з CSV."

        doc = getattr(pinned, "document", None)
        if not doc:
            return False, "Pinned повідомлення є, але в ньому немає документа (CSV)."

        file = await app.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()

        # write raw bytes to file
        with open(BASE_FILE, "wb") as f:
            f.write(content)

        # quick validate: must have header with surname column
        rows = read_csv_file(BASE_FILE)
        if not rows:
            return False, "CSV з pinned відновився, але вийшов порожнім або з неправильними колонками."

        return True, f"✅ Відновив базу з pinned backup ({len(rows)} записів)."

    except Exception as e:
        logger.exception("restore_from_pinned_backup failed")
        return False, f"Помилка авто-відновлення з pinned backup: {e}"

async def ensure_local_db_ready(app) -> str:
    """
    On boot: if local DB missing/empty -> try pinned backup -> else try seed from Google.
    Returns human-readable status.
    """
    if file_exists_and_not_empty(BASE_FILE):
        rows = read_csv_file(BASE_FILE)
        return f"✅ Локальна база OK ({len(rows)} записів)."

    backup_chat_id = parse_backup_chat_id()
    if backup_chat_id:
        ok, msg = await restore_from_pinned_backup(app, backup_chat_id)
        if ok:
            return msg
        logger.warning(msg)

    # fallback seed from Google
    if CSV_URL:
        try:
            rows = load_google_csv_cached()
            if rows:
                write_csv_file(BASE_FILE, rows)
                return f"✅ База була пуста — зробив seed з Google ({len(rows)} записів)."
            return "⚠️ База пуста і Google seed повернув 0 записів."
        except Exception as e:
            logger.exception("seed from Google failed")
            return f"⚠️ База пуста, pinned backup недоступний, seed з Google не вдався: {e}"

    return "⚠️ База пуста. Додай BACKUP_CHAT_ID або CSV_URL, або зроби /restore (надішли CSV)."

async def send_backup_and_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    backup_chat_id = parse_backup_chat_id()
    if not backup_chat_id:
        await update.message.reply_text("❌ BACKUP_CHAT_ID не заданий у Render → Environment Variables.")
        return

    rows = read_csv_file(BASE_FILE)
    if not rows:
        await update.message.reply_text("⚠️ База пуста — нічого бекапити.")
        return

    await update.message.reply_text("💾 Роблю backup…")
    filename = f"base_data_{now_ts()}.csv"

    # create temp file
    write_csv_file(filename, rows)

    try:
        with open(filename, "rb") as f:
            msg = await context.bot.send_document(
                chat_id=backup_chat_id,
                document=f,
                filename=filename,
                caption=f"💾 Backup бази ({len(rows)} записів) • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            )

        # pin the backup message (this is the KEY for auto-restore)
        try:
            await context.bot.pin_chat_message(
                chat_id=backup_chat_id,
                message_id=msg.message_id,
                disable_notification=True,
            )
            await update.message.reply_text("✅ Backup відправив у backup-групу і закріпив (pinned).")
        except Exception as e:
            await update.message.reply_text(
                "⚠️ Backup відправив, але НЕ зміг закріпити (pinned).\n"
                "Дай боту право 'Pin messages' у backup-групі.\n"
                f"Помилка: {e}"
            )

    finally:
        try:
            os.remove(filename)
        except Exception:
            pass

async def manual_restore_from_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    User sends a CSV document => overwrite local DB.
    """
    msg = update.message
    if not msg or not msg.document:
        await msg.reply_text("Надішли CSV як документ.")
        return

    await msg.reply_chat_action(ChatAction.TYPING)
    file = await context.bot.get_file(msg.document.file_id)
    content = await file.download_as_bytearray()

    with open(BASE_FILE, "wb") as f:
        f.write(content)

    rows = read_csv_file(BASE_FILE)
    if not rows:
        await msg.reply_text("⚠️ Файл прийняв, але база вийшла порожня або не ті колонки.")
        return

    await msg.reply_text(f"✅ Відновлено базу з файлу ({len(rows)} записів).")

    # optionally also backup+pin immediately (so next deploy auto-restores)
    backup_chat_id = parse_backup_chat_id()
    if backup_chat_id:
        await msg.reply_text("📌 Зараз одразу зроблю backup у групу і закріплю (щоб після деплою відновлювалось автоматично)…")
        await send_backup_and_pin(update, context)

# ==================================================
# BOT COMMANDS
# ==================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = await ensure_local_db_ready(context.application)
    await update.message.reply_text(
        "Привіт! Я готовий.\n\n"
        f"{status}\n\n"
        "Команди:\n"
        "/stats\n"
        "/all_list\n"
        "/locker_list\n"
        "/no_locker_list\n"
        "/knife_list\n"
        "/no_knife_list\n"
        "/backup\n"
        "/seed\n"
        "/restore (надішли CSV документом)\n",
        reply_markup=MAIN_KB,
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_local_db_ready(context.application)

    rows = read_csv_file(BASE_FILE)
    total = len(rows)
    knife_yes = sum(1 for r in rows if is_knife_yes(r.get(COL_KNIFE, "")))
    knife_no = sum(1 for r in rows if is_knife_no(r.get(COL_KNIFE, "")))
    knife_unknown = total - knife_yes - knife_no

    locker_yes = sum(1 for r in rows if is_locker_yes(r.get(COL_LOCKER, "")))
    locker_no = total - locker_yes

    text = (
        f"📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 Ніж:\n"
        f"  ✅ Є: {knife_yes}\n"
        f"  🚫 Нема: {knife_no}\n"
        f"  ❓ Невідомо: {knife_unknown}\n\n"
        f"🗄️ Шафка:\n"
        f"  ✅ Є: {locker_yes}\n"
        f"  🚫 Нема: {locker_no}\n"
    )
    await update.message.reply_text(text)

async def cmd_all_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_local_db_ready(context.application)
    rows = read_csv_file(BASE_FILE)
    rows_sorted = sorted(rows, key=lambda r: normalize_str(r.get(COL_SURNAME, "")).lower())
    text = "👥 Всі:\n\n" + format_people_list(rows_sorted)
    await update.message.reply_text(text)

async def cmd_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_local_db_ready(context.application)
    rows = [r for r in read_csv_file(BASE_FILE) if is_locker_yes(r.get(COL_LOCKER, ""))]
    rows_sorted = sorted(rows, key=lambda r: normalize_str(r.get(COL_SURNAME, "")).lower())
    text = "🗄️ З шафкою:\n\n" + format_people_list(rows_sorted, with_locker_number=True)
    await update.message.reply_text(text)

async def cmd_no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_local_db_ready(context.application)
    rows = [r for r in read_csv_file(BASE_FILE) if is_locker_no(r.get(COL_LOCKER, ""))]
    rows_sorted = sorted(rows, key=lambda r: normalize_str(r.get(COL_SURNAME, "")).lower())
    text = "🚫 Без шафки:\n\n" + format_people_list(rows_sorted)
    await update.message.reply_text(text)

async def cmd_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_local_db_ready(context.application)
    rows = [r for r in read_csv_file(BASE_FILE) if is_knife_yes(r.get(COL_KNIFE, ""))]
    rows_sorted = sorted(rows, key=lambda r: normalize_str(r.get(COL_SURNAME, "")).lower())
    text = "🔪 З ножем:\n\n" + format_people_list(rows_sorted)
    await update.message.reply_text(text)

async def cmd_no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_local_db_ready(context.application)
    rows = [r for r in read_csv_file(BASE_FILE) if is_knife_no(r.get(COL_KNIFE, ""))]
    rows_sorted = sorted(rows, key=lambda r: normalize_str(r.get(COL_SURNAME, "")).lower())
    text = "🚫 Без ножа:\n\n" + format_people_list(rows_sorted)
    await update.message.reply_text(text)

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ensure_local_db_ready(context.application)
    await send_backup_and_pin(update, context)

async def cmd_seed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not CSV_URL:
        await update.message.reply_text("❌ CSV_URL не заданий у Render. Seed неможливий.")
        return
    try:
        rows = load_google_csv_cached()
        if not rows:
            await update.message.reply_text("⚠️ Seed: Google CSV повернув 0 записів.")
            return
        write_csv_file(BASE_FILE, rows)
        await update.message.reply_text(f"✅ Seed з Google виконано ({len(rows)} записів).")
    except Exception as e:
        await update.message.reply_text(f"❌ Seed помилка: {e}")

async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "♻️ Відновлення:\n"
        "Надішли мені CSV-файл бази як *ДОКУМЕНТ* (не фото).\n"
        "Я перезапишу local_data.csv.\n",
        parse_mode="Markdown",
    )

# ==================================================
# TEXT BUTTONS (keyboard)
# ==================================================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    t = (update.message.text or "").strip()

    if t == "📊 Статистика":
        await cmd_stats(update, context)
    elif t == "👥 Всі":
        await cmd_all_list(update, context)
    elif t == "🗄️ З шафкою":
        await cmd_locker_list(update, context)
    elif t == "🚫 Без шафки":
        await cmd_no_locker_list(update, context)
    elif t == "🔪 З ножем":
        await cmd_knife_list(update, context)
    elif t == "🚫 Без ножа":
        await cmd_no_knife_list(update, context)
    elif t == "💾 Backup бази":
        await cmd_backup(update, context)
    elif t == "♻️ Seed з Google":
        await cmd_seed(update, context)
    else:
        await update.message.reply_text("Не зрозумів. Натисни кнопку або /start", reply_markup=MAIN_KB)

# ==================================================
# OPTIONAL SELF-PING (to keep Render from sleeping; used with UptimeRobot anyway)
# ==================================================
async def self_ping_loop(app):
    if not SELF_PING_URL:
        return
    while True:
        try:
            requests.get(SELF_PING_URL, timeout=10)
        except Exception:
            pass
        await asyncio.sleep(240)  # every 4 minutes

# ==================================================
# APP STARTUP
# ==================================================
async def post_init(app):
    # Ensure DB is ready as soon as bot boots
    status = await ensure_local_db_ready(app)
    logger.info(status)

    # Optionally start self-ping loop
    if SELF_PING_URL:
        app.create_task(self_ping_loop(app))

def main():
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # commands
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("all_list", cmd_all_list))
    application.add_handler(CommandHandler("locker_list", cmd_locker_list))
    application.add_handler(CommandHandler("no_locker_list", cmd_no_locker_list))
    application.add_handler(CommandHandler("knife_list", cmd_knife_list))
    application.add_handler(CommandHandler("no_knife_list", cmd_no_knife_list))
    application.add_handler(CommandHandler("backup", cmd_backup))
    application.add_handler(CommandHandler("seed", cmd_seed))
    application.add_handler(CommandHandler("restore", cmd_restore))

    # restore by sending a document
    application.add_handler(MessageHandler(filters.Document.ALL, manual_restore_from_document))

    # text buttons
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    logger.info("Bot starting polling…")
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
