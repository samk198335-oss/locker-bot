import os
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# ==============================
# 🔧 CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "data.db"

# ==============================
# 🗄️ DATABASE
# ==============================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surname TEXT NOT NULL,
            knife INTEGER NOT NULL,
            locker TEXT
        )
    """)
    conn.commit()
    conn.close()

# ==============================
# 🧠 HELPERS
# ==============================

def is_yes(value: str) -> bool:
    return value.strip().lower() in ("1", "yes", "y", "так", "є", "true", "+")

def has_locker(value: str) -> bool:
    return bool(value and value.strip() not in ("-", "0", "ні", "no"))

# ==============================
# 📋 KEYBOARD
# ==============================

KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄️ З шафкою", "❌ Без шафки"],
        ["👥 Всі", "📊 Статистика"]
    ],
    resize_keyboard=True
)

# ==============================
# 🤖 BASIC COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Обери фільтр або команду 👇",
        reply_markup=KEYBOARD
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT * FROM employees").fetchall()
    conn.close()

    total = len(rows)
    knife_yes = sum(1 for r in rows if r["knife"] == 1)
    knife_no = total - knife_yes
    locker_yes = sum(1 for r in rows if has_locker(r["locker"]))
    locker_no = total - locker_yes

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def all_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT surname FROM employees").fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text(
        "👥 Всі:\n\n" + "\n".join(r["surname"] for r in rows)
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT surname FROM employees WHERE knife = 1").fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text(
        "🔪 З ножем:\n\n" + "\n".join(r["surname"] for r in rows)
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT surname FROM employees WHERE knife = 0").fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text(
        "🚫 Без ножа:\n\n" + "\n".join(r["surname"] for r in rows)
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT surname, locker FROM employees WHERE locker IS NOT NULL AND locker != '-'").fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text(
        "🗄️ З шафкою:\n\n" +
        "\n".join(f"{r['surname']} — {r['locker']}" for r in rows)
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    rows = conn.execute("SELECT surname FROM employees WHERE locker IS NULL OR locker = '-'").fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text(
        "❌ Без шафки:\n\n" + "\n".join(r["surname"] for r in rows)
    )

# ==============================
# ➕ ADD EMPLOYEE
# ==============================

ADD_SURNAME, ADD_KNIFE, ADD_LOCKER = range(3)

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи прізвище:")
    return ADD_SURNAME

async def add_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["surname"] = update.message.text.strip()
    await update.message.reply_text("Ніж? (так / ні)")
    return ADD_KNIFE

async def add_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["knife"] = 1 if is_yes(update.message.text) else 0
    await update.message.reply_text("Шафка? (номер або -)")
    return ADD_LOCKER

async def add_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    locker = update.message.text.strip()
    conn = get_db()
    conn.execute(
        "INSERT INTO employees (surname, knife, locker) VALUES (?, ?, ?)",
        (context.user_data["surname"], context.user_data["knife"], locker)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Працівника додано")
    return ConversationHandler.END

# ==============================
# ✏️ RENAME
# ==============================

RENAME_OLD, RENAME_NEW = range(2)

async def rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Старе прізвище:")
    return RENAME_OLD

async def rename_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["old"] = update.message.text.strip()
    await update.message.reply_text("Нове прізвище:")
    return RENAME_NEW

async def rename_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    conn.execute(
        "UPDATE employees SET surname = ? WHERE surname = ?",
        (update.message.text.strip(), context.user_data["old"])
    )
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Прізвище оновлено")
    return ConversationHandler.END

# ==============================
# 🌐 KEEP ALIVE
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    HTTPServer(("0.0.0.0", 10000), HealthHandler).serve_forever()

# ==============================
# 🚀 MAIN
# ==============================

def main():
    init_db()
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(MessageHandler(filters.Regex("^🔪"), knife_list))
    app.add_handler(MessageHandler(filters.Regex("^🚫"), no_knife_list))
    app.add_handler(MessageHandler(filters.Regex("^🗄️"), locker_list))
    app.add_handler(MessageHandler(filters.Regex("^❌"), no_locker_list))
    app.add_handler(MessageHandler(filters.Regex("^👥"), all_list))
    app.add_handler(MessageHandler(filters.Regex("^📊"), stats))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            ADD_SURNAME: [MessageHandler(filters.TEXT, add_surname)],
            ADD_KNIFE: [MessageHandler(filters.TEXT, add_knife)],
            ADD_LOCKER: [MessageHandler(filters.TEXT, add_locker)],
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("rename", rename_start)],
        states={
            RENAME_OLD: [MessageHandler(filters.TEXT, rename_old)],
            RENAME_NEW: [MessageHandler(filters.TEXT, rename_new)],
        },
        fallbacks=[]
    ))

    app.run_polling()

if __name__ == "__main__":
    main()
