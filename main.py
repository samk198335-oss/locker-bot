import os
import csv
import time
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Tuple, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ==================================================
# ✅ CONFIG
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CSV_URL = os.getenv(
    "CSV_URL",
    "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv",
)

# Local file for added employees (because Google CSV export is read-only)
LOCAL_DATA_FILE = os.getenv("LOCAL_DATA_FILE", "local_data.csv")

# Cache (seconds)
CACHE_TTL = int(os.getenv("CACHE_TTL", "60"))

# Required column names in CSV
COL_ADDRESS = "Adress"   # <- IMPORTANT: In your sheet header it's "Adress" (not "Address")
COL_SURNAME = "surname"
COL_KNIFE = "knife"
COL_LOCKER = "locker"

# ==================================================
# 🔧 RENDER FREE STABILIZATION (health endpoint)
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ==================================================
# 🧠 CACHE
# ==================================================

_cache_data: Optional[List[Dict[str, str]]] = None
_cache_time: float = 0.0

def _now() -> float:
    return time.time()

# ==================================================
# ✅ NORMALIZERS (THE MOST IMPORTANT PART)
# ==================================================

def norm_str(v: object) -> str:
    return str(v).strip() if v is not None else ""

def knife_value(v: object) -> str:
    """
    STRICT knife logic:
      "1" => has knife
      "0" => no knife
      everything else => unknown (ignored)
    """
    s = norm_str(v)
    if s == "1":
        return "1"
    if s == "0":
        return "0"
    return ""

def locker_value(v: object) -> str:
    """
    Locker:
      empty / "-" / "—" => no locker (empty)
      anything else => has locker
    """
    s = norm_str(v)
    if s in ("", "-", "—"):
        return ""
    return s

def display_person(row: Dict[str, str]) -> str:
    name = norm_str(row.get(COL_SURNAME, ""))
    locker = locker_value(row.get(COL_LOCKER, ""))
    if locker:
        return f"{name} — {locker}"
    return name

# ==================================================
# 📥 DATA LOADING
# ==================================================

def read_remote_csv() -> List[Dict[str, str]]:
    r = requests.get(CSV_URL, timeout=20)
    r.raise_for_status()
    content = r.content.decode("utf-8", errors="replace")
    reader = csv.DictReader(StringIO(content))
    rows = []
    for row in reader:
        # Keep only expected keys, but preserve if present
        rows.append({k: (v if v is not None else "") for k, v in row.items()})
    return rows

def ensure_local_file():
    if os.path.exists(LOCAL_DATA_FILE):
        return
    # Create with headers
    with open(LOCAL_DATA_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[COL_ADDRESS, COL_SURNAME, COL_KNIFE, COL_LOCKER],
        )
        w.writeheader()

def read_local_csv() -> List[Dict[str, str]]:
    ensure_local_file()
    out: List[Dict[str, str]] = []
    with open(LOCAL_DATA_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append({k: (v if v is not None else "") for k, v in row.items()})
    return out

def load_data(force: bool = False) -> List[Dict[str, str]]:
    global _cache_data, _cache_time

    if not force and _cache_data is not None and (_now() - _cache_time) < CACHE_TTL:
        return _cache_data

    remote = read_remote_csv()
    local = read_local_csv()

    # Merge = remote + local additions
    merged = remote + local

    _cache_data = merged
    _cache_time = _now()
    return merged

# ==================================================
# 🧾 STATS + LISTS
# ==================================================

def compute_stats(rows: List[Dict[str, str]]) -> Dict[str, int]:
    total = 0
    knife_yes = 0
    knife_no = 0
    locker_yes = 0
    locker_no = 0

    for r in rows:
        name = norm_str(r.get(COL_SURNAME, ""))
        if not name:
            continue
        total += 1

        kv = knife_value(r.get(COL_KNIFE, ""))
        if kv == "1":
            knife_yes += 1
        elif kv == "0":
            knife_no += 1
        # unknown ignored

        lv = locker_value(r.get(COL_LOCKER, ""))
        if lv:
            locker_yes += 1
        else:
            locker_no += 1

    return {
        "total": total,
        "knife_yes": knife_yes,
        "knife_no": knife_no,
        "locker_yes": locker_yes,
        "locker_no": locker_no,
    }

def list_people(rows: List[Dict[str, str]], mode: str) -> List[str]:
    """
    mode:
      all | knife_yes | knife_no | locker_yes | locker_no
    """
    out: List[str] = []
    for r in rows:
        name = norm_str(r.get(COL_SURNAME, ""))
        if not name:
            continue

        kv = knife_value(r.get(COL_KNIFE, ""))
        lv = locker_value(r.get(COL_LOCKER, ""))

        if mode == "all":
            out.append(display_person(r))
        elif mode == "knife_yes":
            if kv == "1":
                out.append(display_person(r))
        elif mode == "knife_no":
            if kv == "0":
                out.append(display_person(r))
        elif mode == "locker_yes":
            if lv:
                out.append(display_person(r))
        elif mode == "locker_no":
            if not lv:
                out.append(display_person(r))

    return out

def chunk_text(lines: List[str], header: str, limit: int = 3800) -> List[str]:
    """
    Telegram message limit ~4096. Keep safe margin.
    """
    if not lines:
        return [f"{header}\n\nНемає даних."]
    msgs: List[str] = []
    cur = header + "\n\n"
    for line in lines:
        add = line + "\n"
        if len(cur) + len(add) > limit:
            msgs.append(cur.rstrip())
            cur = header + "\n\n" + add
        else:
            cur += add
    if cur.strip():
        msgs.append(cur.rstrip())
    return msgs

# ==================================================
# 🧩 UI
# ==================================================

def main_menu_kb() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("📊 Статистика", callback_data="m_stats"),
            InlineKeyboardButton("👥 Всі", callback_data="m_all"),
        ],
        [
            InlineKeyboardButton("🔪 З ножем", callback_data="m_knife_yes"),
            InlineKeyboardButton("🚫 Без ножа", callback_data="m_knife_no"),
        ],
        [
            InlineKeyboardButton("🗄 З шафкою", callback_data="m_locker_yes"),
            InlineKeyboardButton("❌ Без шафки", callback_data="m_locker_no"),
        ],
        [
            InlineKeyboardButton("➕ Додати працівника", callback_data="m_add"),
        ],
    ]
    return InlineKeyboardMarkup(kb)

def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Скасувати", callback_data="add_cancel")]])

def knife_choice_kb() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton("🔪 Є ніж", callback_data="add_knife_1"),
            InlineKeyboardButton("🚫 Немає ножа", callback_data="add_knife_0"),
        ],
        [InlineKeyboardButton("❌ Скасувати", callback_data="add_cancel")],
    ]
    return InlineKeyboardMarkup(kb)

# ==================================================
# ➕ ADD EMPLOYEE (Conversation)
# ==================================================

ADD_SURNAME, ADD_LOCKER, ADD_KNIFE = range(3)

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()

    context.user_data["add"] = {}

    text = "➕ Додати працівника\n\nВведіть *прізвище та імʼя* (як у таблиці):"
    if update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=cancel_kb())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=cancel_kb())
    return ADD_SURNAME

async def add_surname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    surname = norm_str(update.message.text)
    if not surname:
        await update.message.reply_text("Будь ласка, введіть прізвище та імʼя.", reply_markup=cancel_kb())
        return ADD_SURNAME

    context.user_data["add"]["surname"] = surname

    await update.message.reply_text(
        "Введіть *номер шафки* або `-` якщо шафки немає:",
        parse_mode="Markdown",
        reply_markup=cancel_kb(),
    )
    return ADD_LOCKER

async def add_locker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    locker = norm_str(update.message.text)
    # store normalized (empty if -/—/empty)
    locker = locker_value(locker)

    context.user_data["add"]["locker"] = locker

    await update.message.reply_text(
        "Оберіть *ніж* кнопкою:",
        parse_mode="Markdown",
        reply_markup=knife_choice_kb(),
    )
    return ADD_KNIFE

def append_local_row(row: Dict[str, str]) -> None:
    ensure_local_file()
    with open(LOCAL_DATA_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[COL_ADDRESS, COL_SURNAME, COL_KNIFE, COL_LOCKER])
        writer.writerow(row)

async def add_knife_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()

    data = q.data  # add_knife_1 / add_knife_0
    knife = "1" if data.endswith("_1") else "0"

    payload = context.user_data.get("add", {})
    surname = norm_str(payload.get("surname", ""))
    locker = locker_value(payload.get("locker", ""))

    if not surname:
        await q.message.reply_text("Помилка: не знайдено прізвище. Спробуйте ще раз.", reply_markup=main_menu_kb())
        return ConversationHandler.END

    # Address is optional in your flow; set empty
    row = {
        COL_ADDRESS: "",
        COL_SURNAME: surname,
        COL_KNIFE: knife,
        COL_LOCKER: locker,
    }

    append_local_row(row)

    # invalidate cache
    global _cache_data, _cache_time
    _cache_data = None
    _cache_time = 0.0

    await q.message.reply_text(
        f"✅ Додано: {display_person(row)}\nНіж: {'Є' if knife == '1' else 'Немає'}",
        reply_markup=main_menu_kb(),
    )
    return ConversationHandler.END

async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Скасовано.", reply_markup=main_menu_kb())
    else:
        await update.message.reply_text("Скасовано.", reply_markup=main_menu_kb())
    return ConversationHandler.END

# ==================================================
# 📌 COMMANDS
# ==================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Обери дію 👇",
        reply_markup=main_menu_kb(),
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    s = compute_stats(rows)

    text = (
        "📊 *Статистика:*\n\n"
        f"👥 Всього: {s['total']}\n\n"
        f"🔪 З ножем: {s['knife_yes']}\n"
        f"🚫 Без ножа: {s['knife_no']}\n\n"
        f"🗄 З шафкою: {s['locker_yes']}\n"
        f"❌ Без шафки: {s['locker_no']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())

async def send_list(update: Update, title: str, mode: str):
    rows = load_data()
    lines = list_people(rows, mode)
    msgs = chunk_text(lines, title)

    # If callback, reply in chat; else reply to message
    if update.callback_query:
        for i, m in enumerate(msgs):
            await update.callback_query.message.reply_text(m, reply_markup=main_menu_kb() if i == len(msgs) - 1 else None)
    else:
        for i, m in enumerate(msgs):
            await update.message.reply_text(m, reply_markup=main_menu_kb() if i == len(msgs) - 1 else None)

async def cmd_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_list(update, "🔪 З ножем:", "knife_yes")

async def cmd_no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_list(update, "🚫 Без ножа:", "knife_no")

async def cmd_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_list(update, "🗄 З шафкою:", "locker_yes")

async def cmd_no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_list(update, "❌ Без шафки:", "locker_no")

async def cmd_all_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_list(update, "👥 Всі:", "all")

# ==================================================
# 🧷 MENU CALLBACKS
# ==================================================

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    data = q.data

    if data == "m_stats":
        rows = load_data()
        s = compute_stats(rows)
        text = (
            "📊 *Статистика:*\n\n"
            f"👥 Всього: {s['total']}\n\n"
            f"🔪 З ножем: {s['knife_yes']}\n"
            f"🚫 Без ножа: {s['knife_no']}\n\n"
            f"🗄 З шафкою: {s['locker_yes']}\n"
            f"❌ Без шафки: {s['locker_no']}"
        )
        await q.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_kb())
        return

    if data == "m_all":
        await send_list(update, "👥 Всі:", "all")
        return

    if data == "m_knife_yes":
        await send_list(update, "🔪 З ножем:", "knife_yes")
        return

    if data == "m_knife_no":
        await send_list(update, "🚫 Без ножа:", "knife_no")
        return

    if data == "m_locker_yes":
        await send_list(update, "🗄 З шафкою:", "locker_yes")
        return

    if data == "m_locker_no":
        await send_list(update, "❌ Без шафки:", "locker_no")
        return

    if data == "m_add":
        # start conversation
        await add_start(update, context)
        return

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    # health server for Render
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("knife_list", cmd_knife_list))
    app.add_handler(CommandHandler("no_knife_list", cmd_no_knife_list))
    app.add_handler(CommandHandler("locker_list", cmd_locker_list))
    app.add_handler(CommandHandler("no_locker_list", cmd_no_locker_list))
    app.add_handler(CommandHandler("all_list", cmd_all_list))

    # Add employee conversation
    add_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_start, pattern="^m_add$"),
            CommandHandler("add", add_start),
        ],
        states={
            ADD_SURNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_surname),
                CallbackQueryHandler(add_cancel, pattern="^add_cancel$"),
            ],
            ADD_LOCKER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_locker),
                CallbackQueryHandler(add_cancel, pattern="^add_cancel$"),
            ],
            ADD_KNIFE: [
                CallbackQueryHandler(add_knife_choice, pattern="^add_knife_(1|0)$"),
                CallbackQueryHandler(add_cancel, pattern="^add_cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(add_cancel, pattern="^add_cancel$"),
            CommandHandler("cancel", add_cancel),
        ],
        allow_reentry=True,
    )
    app.add_handler(add_conv)

    # Menu callbacks (must be after add_conv entrypoints are registered)
    app.add_handler(CallbackQueryHandler(on_menu, pattern="^m_"))

    # Run
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
