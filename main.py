import os
import csv
import re
import time
import threading
import requests
from io import StringIO
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import (
    Update,
    ReplyKeyboardMarkup,
)
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# 🔧 RENDER FREE STABILIZATION: simple HTTP server (for uptime checks)
# =========================================================

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


# =========================================================
# 🔑 CONFIG
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CSV_URL = os.environ.get(
    "CSV_URL",
    "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
).strip()

# Backup group chat id (Telegram supergroup id like -100...)
BACKUP_CHAT_ID = os.environ.get("BACKUP_CHAT_ID", "").strip()

# Optional self ping URL (you had it earlier)
SELF_PING_URL = os.environ.get("SELF_PING_URL", "").strip()

DATA_FILE = "base_data.csv"

REQUIRED_COLUMNS = ["Address", "surname", "knife", "locker"]

# =========================================================
# 🧩 UI
# =========================================================

BTN_STATS = "📊 Статистика"
BTN_ALL = "👥 Всі"
BTN_LOCKER_YES = "🗄️ З шафкою"
BTN_LOCKER_NO = "⛔️ Без шафки"
BTN_KNIFE_YES = "🔪 З ножем"
BTN_KNIFE_NO = "⛔️ Без ножа"
BTN_BACKUP = "💾 Backup бази"
BTN_SEED = "🧬 Seed з Google"
BTN_RESTORE = "♻️ Відновити з файлу"
BTN_CANCEL = "⛔️ Скасувати"

MAIN_KB = ReplyKeyboardMarkup(
    [
        [BTN_STATS, BTN_ALL],
        [BTN_LOCKER_YES, BTN_LOCKER_NO],
        [BTN_KNIFE_YES, BTN_KNIFE_NO],
        [BTN_BACKUP, BTN_SEED],
        [BTN_RESTORE],
    ],
    resize_keyboard=True
)

CANCEL_KB = ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)


# =========================================================
# ✅ HELPERS: normalize / parsing
# =========================================================

def _norm(s: str) -> str:
    return (s or "").strip()

def _norm_low(s: str) -> str:
    return _norm(s).lower()

YES_SET = {"1", "yes", "y", "true", "так", "+", "є", "есть", "имеется", "наявний"}
NO_SET = {"0", "no", "n", "false", "ні", "нет", "-"}

def parse_knife(v: str) -> str:
    """
    returns: "yes" | "no" | "unknown"
    """
    t = _norm_low(v)
    if t in YES_SET:
        return "yes"
    if t in NO_SET:
        return "no"
    if t == "":
        return "unknown"
    # sometimes they use "2" for unknown
    if t == "2":
        return "unknown"
    return "unknown"

def has_locker(v: str) -> bool:
    """
    True if locker field contains something meaningful.
    Accepts numbers and phrases, rejects empty / '-' / 'ні' etc.
    """
    t = _norm_low(v)
    if t == "":
        return False
    if t in {"-", "—", "ні", "нет", "no", "0"}:
        return False
    return True

def safe_row_value(row: dict, key: str) -> str:
    return _norm(row.get(key, ""))

def ensure_headers(rows: list[dict]) -> list[dict]:
    """
    Keep only REQUIRED_COLUMNS, fill missing with "".
    """
    cleaned = []
    for r in rows:
        nr = {k: safe_row_value(r, k) for k in REQUIRED_COLUMNS}
        cleaned.append(nr)
    return cleaned


# =========================================================
# 📦 DB: read/write
# =========================================================

def db_exists_and_has_data() -> bool:
    if not os.path.exists(DATA_FILE):
        return False
    try:
        with open(DATA_FILE, "r", encoding="utf-8", newline="") as f:
            content = f.read().strip()
        if not content:
            return False
        # must have at least header + 1 row
        lines = [ln for ln in content.splitlines() if ln.strip()]
        return len(lines) >= 2
    except Exception:
        return False

def read_db() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return []
            rows = []
            for row in reader:
                rows.append(row)
        # normalize column names by mapping if needed
        # if someone saved with different case, try to map
        fieldnames = [fn.strip() for fn in (rows[0].keys() if rows else [])]

        # If exact required headers exist – just clean and return
        if rows and all(k in rows[0] for k in REQUIRED_COLUMNS):
            return ensure_headers(rows)

        # Otherwise try to map by lowercase keys
        mapped = []
        for r in rows:
            low = {str(k).strip().lower(): (v if v is not None else "") for k, v in r.items()}
            mapped.append({
                "Address": _norm(low.get("address", "")),
                "surname": _norm(low.get("surname", "")),
                "knife": _norm(low.get("knife", "")),
                "locker": _norm(low.get("locker", "")),
            })
        return ensure_headers(mapped)
    except Exception:
        return []

def write_db(rows: list[dict]) -> None:
    rows = ensure_headers(rows)
    with open(DATA_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REQUIRED_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: safe_row_value(r, k) for k in REQUIRED_COLUMNS})

def count_records(rows: list[dict]) -> int:
    # count only rows with surname filled (avoid empty garbage lines)
    return sum(1 for r in rows if safe_row_value(r, "surname") != "")


# =========================================================
# 🌐 Seed from Google
# =========================================================

def seed_from_google_sync() -> int:
    resp = requests.get(CSV_URL, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    text = resp.text
    reader = csv.DictReader(StringIO(text))
    raw_rows = list(reader)

    # If sheet has different headers, try fallback mapping by known names
    rows = []
    for r in raw_rows:
        if all(k in r for k in REQUIRED_COLUMNS):
            rows.append({k: safe_row_value(r, k) for k in REQUIRED_COLUMNS})
        else:
            low = {str(k).strip().lower(): (v if v is not None else "") for k, v in r.items()}
            rows.append({
                "Address": _norm(low.get("address", "")),
                "surname": _norm(low.get("surname", "")),
                "knife": _norm(low.get("knife", "")),
                "locker": _norm(low.get("locker", "")),
            })

    write_db(rows)
    return count_records(rows)


# =========================================================
# 📤 Backup to Telegram (and pin)
# =========================================================

async def send_backup_to_group(bot, note: str = "") -> tuple[bool, str]:
    if not BACKUP_CHAT_ID:
        return False, "BACKUP_CHAT_ID не заданий в Render Environment."

    rows = read_db()
    n = count_records(rows)
    if n == 0:
        return False, "⚠️ Немає даних для backup (база порожня)."

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"base_data_{ts}.csv"

    # write temp backup file
    write_db(rows)
    # also copy to timestamped file
    with open(DATA_FILE, "r", encoding="utf-8") as src:
        data = src.read()
    with open(fname, "w", encoding="utf-8") as out:
        out.write(data)

    caption = f"💾 Backup бази ({n} записів) • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    if note:
        caption += f"\n{note}"

    try:
        with open(fname, "rb") as f:
            msg = await bot.send_document(
                chat_id=int(BACKUP_CHAT_ID),
                document=f,
                caption=caption
            )
        # try pin
        try:
            await bot.pin_chat_message(chat_id=int(BACKUP_CHAT_ID), message_id=msg.message_id, disable_notification=True)
        except TelegramError:
            # no rights to pin - ignore
            pass
        finally:
            try:
                os.remove(fname)
            except Exception:
                pass
        return True, "✅ Backup відправив у backup-групу (і спробував закріпити)."
    except TelegramError as e:
        try:
            os.remove(fname)
        except Exception:
            pass
        return False, f"❌ Не зміг відправити backup у групу: {e}"


# =========================================================
# ♻️ Restore from pinned backup in Telegram
# =========================================================

async def restore_from_pinned_backup(bot) -> tuple[bool, str]:
    if not BACKUP_CHAT_ID:
        return False, "BACKUP_CHAT_ID не заданий."

    try:
        chat = await bot.get_chat(int(BACKUP_CHAT_ID))
        pinned = getattr(chat, "pinned_message", None)
        if not pinned:
            return False, "У backup-групі немає закріпленого (pinned) повідомлення."
        doc = getattr(pinned, "document", None)
        if not doc:
            return False, "Pinned повідомлення є, але там немає CSV-документа."
        file = await bot.get_file(doc.file_id)
        b = await file.download_as_bytearray()
        content = b.decode("utf-8", errors="replace").strip()
        if not content:
            return False, "Pinned CSV порожній."

        # Validate CSV header
        reader = csv.DictReader(StringIO(content))
        if not reader.fieldnames:
            return False, "Pinned CSV має некоректний формат (немає заголовків)."

        # Write to DATA_FILE
        with open(DATA_FILE, "w", encoding="utf-8", newline="") as f:
            f.write(content + ("\n" if not content.endswith("\n") else ""))

        # normalize by rewriting with required headers if needed
        rows = read_db()
        write_db(rows)

        n = count_records(rows)
        if n == 0:
            return False, "Відновив файл, але в ньому 0 записів (перевір pinned backup)."
        return True, f"✅ Відновлено з pinned backup: {n} записів."
    except TelegramError as e:
        return False, f"❌ Restore з pinned backup не вдався: {e}"
    except Exception as e:
        return False, f"❌ Restore error: {e}"


# =========================================================
# 🧠 Auto ensure DB at startup
# =========================================================

async def ensure_db_on_start(bot) -> None:
    # If ok - do nothing
    if db_exists_and_has_data():
        return

    # 1) Try restore from pinned backup
    ok, _ = await restore_from_pinned_backup(bot)
    if ok and db_exists_and_has_data():
        return

    # 2) fallback to seed from google
    try:
        seed_from_google_sync()
    except Exception:
        # last resort: create empty db with header
        write_db([])


# =========================================================
# 📊 Stats & Lists
# =========================================================

def build_stats_text(rows: list[dict]) -> str:
    total = count_records(rows)

    knife_yes = 0
    knife_no = 0
    knife_unknown = 0

    locker_yes = 0
    locker_no = 0

    for r in rows:
        if safe_row_value(r, "surname") == "":
            continue

        k = parse_knife(safe_row_value(r, "knife"))
        if k == "yes":
            knife_yes += 1
        elif k == "no":
            knife_no += 1
        else:
            knife_unknown += 1

        if has_locker(safe_row_value(r, "locker")):
            locker_yes += 1
        else:
            locker_no += 1

    return (
        "📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        "🔪 Ніж:\n"
        f"✅ Є: {knife_yes}\n"
        f"⛔️ Нема: {knife_no}\n"
        f"❓ Невідомо: {knife_unknown}\n\n"
        "🗄️ Шафка:\n"
        f"✅ Є: {locker_yes}\n"
        f"⛔️ Нема: {locker_no}"
    )

def format_people_list(title: str, people: list[str]) -> str:
    if not people:
        return f"{title}\n\nНемає даних."
    return f"{title}\n\n" + "\n".join(people)

def list_all(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = safe_row_value(r, "surname")
        if not s:
            continue
        people.append(s)
    people.sort(key=lambda x: x.lower())
    return format_people_list("👥 Всі:", people)

def list_locker_yes(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = safe_row_value(r, "surname")
        if not s:
            continue
        locker = safe_row_value(r, "locker")
        if has_locker(locker):
            people.append(f"{s} — {locker}")
    people.sort(key=lambda x: x.lower())
    return format_people_list("🗄️ З шафкою:", people)

def list_locker_no(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = safe_row_value(r, "surname")
        if not s:
            continue
        locker = safe_row_value(r, "locker")
        if not has_locker(locker):
            people.append(s)
    people.sort(key=lambda x: x.lower())
    return format_people_list("⛔️ Без шафки:", people)

def list_knife_yes(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = safe_row_value(r, "surname")
        if not s:
            continue
        if parse_knife(safe_row_value(r, "knife")) == "yes":
            people.append(s)
    people.sort(key=lambda x: x.lower())
    return format_people_list("🔪 З ножем:", people)

def list_knife_no(rows: list[dict]) -> str:
    people = []
    for r in rows:
        s = safe_row_value(r, "surname")
        if not s:
            continue
        if parse_knife(safe_row_value(r, "knife")) == "no":
            people.append(s)
    people.sort(key=lambda x: x.lower())
    return format_people_list("⛔️ Без ножа:", people)


# =========================================================
# 🧾 Restore from file flow (user sends CSV document)
# =========================================================

async def start_restore_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["restore_waiting"] = True
    await update.message.reply_text(
        "♻️ Відновлення активне.\n"
        "Надішли CSV-файл бази (base_data_*.csv) як **ДОКУМЕНТ**.\n\n"
        "⛔️ Скасувати — кнопка нижче.",
        reply_markup=CANCEL_KB
    )

async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("restore_waiting", None)
    await update.message.reply_text("Скасовано ✅", reply_markup=MAIN_KB)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("restore_waiting"):
        await update.message.reply_text("Я отримав файл, але зараз не в режимі відновлення. Натисни ♻️ Відновити з файлу.", reply_markup=MAIN_KB)
        return

    doc = update.message.document
    if not doc:
        await update.message.reply_text("Не бачу документа. Надішли CSV як **Document**.", reply_markup=CANCEL_KB)
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        file = await context.bot.get_file(doc.file_id)
        b = await file.download_as_bytearray()
        content = b.decode("utf-8", errors="replace").strip()
        if not content:
            await update.message.reply_text("Файл порожній ❌", reply_markup=CANCEL_KB)
            return

        # write as is then normalize
        with open(DATA_FILE, "w", encoding="utf-8", newline="") as f:
            f.write(content + ("\n" if not content.endswith("\n") else ""))

        rows = read_db()
        write_db(rows)
        n = count_records(rows)

        context.user_data.pop("restore_waiting", None)

        await update.message.reply_text(f"✅ Відновлено. Записів: {n}", reply_markup=MAIN_KB)

        # autobackup after restore
        ok, msg = await send_backup_to_group(context.bot, note="♻️ Auto-backup після відновлення")
        if ok:
            await update.message.reply_text(msg, reply_markup=MAIN_KB)
        else:
            await update.message.reply_text(msg, reply_markup=MAIN_KB)

    except TelegramError as e:
        await update.message.reply_text(f"❌ Помилка Telegram при завантаженні: {e}", reply_markup=CANCEL_KB)
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка відновлення: {e}", reply_markup=CANCEL_KB)


# =========================================================
# 🤖 Commands / Buttons
# =========================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Обери дію кнопками 👇",
        reply_markup=MAIN_KB
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    await update.message.reply_text(build_stats_text(rows), reply_markup=MAIN_KB)

async def cmd_seed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        n = seed_from_google_sync()
        await update.message.reply_text(f"✅✅ Seed зроблено з Google: {n} записів", reply_markup=MAIN_KB)

        # autobackup after seed
        ok, msg = await send_backup_to_group(context.bot, note="🧬 Auto-backup після Seed")
        await update.message.reply_text(msg, reply_markup=MAIN_KB)

    except Exception as e:
        await update.message.reply_text(f"❌ Seed не вдався: {e}", reply_markup=MAIN_KB)

async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💾 Роблю backup...", reply_markup=MAIN_KB)
    ok, msg = await send_backup_to_group(context.bot)
    await update.message.reply_text(msg, reply_markup=MAIN_KB)

async def cmd_restore_pinned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    ok, msg = await restore_from_pinned_backup(context.bot)
    await update.message.reply_text(msg, reply_markup=MAIN_KB)
    if ok:
        # autobackup after restore
        ok2, msg2 = await send_backup_to_group(context.bot, note="♻️ Auto-backup після pinned restore")
        await update.message.reply_text(msg2, reply_markup=MAIN_KB)

async def cmd_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    await update.message.reply_text(list_all(rows), reply_markup=MAIN_KB)

async def cmd_locker_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    await update.message.reply_text(list_locker_yes(rows), reply_markup=MAIN_KB)

async def cmd_locker_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    await update.message.reply_text(list_locker_no(rows), reply_markup=MAIN_KB)

async def cmd_knife_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    await update.message.reply_text(list_knife_yes(rows), reply_markup=MAIN_KB)

async def cmd_knife_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = read_db()
    await update.message.reply_text(list_knife_no(rows), reply_markup=MAIN_KB)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # cancel
    if text == BTN_CANCEL:
        await cancel_flow(update, context)
        return

    # main buttons
    if text == BTN_STATS:
        await cmd_stats(update, context); return
    if text == BTN_ALL:
        await cmd_all(update, context); return
    if text == BTN_LOCKER_YES:
        await cmd_locker_yes(update, context); return
    if text == BTN_LOCKER_NO:
        await cmd_locker_no(update, context); return
    if text == BTN_KNIFE_YES:
        await cmd_knife_yes(update, context); return
    if text == BTN_KNIFE_NO:
        await cmd_knife_no(update, context); return
    if text == BTN_BACKUP:
        await cmd_backup(update, context); return
    if text == BTN_SEED:
        await cmd_seed(update, context); return
    if text == BTN_RESTORE:
        await start_restore_flow(update, context); return

    # if user writes /start or unknown
    await update.message.reply_text("Не зрозумів. Натисни кнопку або /start", reply_markup=MAIN_KB)


# =========================================================
# 🔁 Optional self ping (keep warm)
# =========================================================

def _self_ping_loop():
    if not SELF_PING_URL:
        return
    while True:
        try:
            requests.get(SELF_PING_URL, timeout=10)
        except Exception:
            pass
        time.sleep(240)  # every 4 min

threading.Thread(target=_self_ping_loop, daemon=True).start()


# =========================================================
# 🚀 App init
# =========================================================

async def post_init(app):
    # auto restore / seed on boot
    await ensure_db_on_start(app.bot)

    # if after ensuring DB we still have empty, keep file with header
    if not os.path.exists(DATA_FILE):
        write_db([])

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("seed", cmd_seed))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("restore", cmd_restore_pinned))

    # restore-from-file document handler
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # buttons / text
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # polling
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
