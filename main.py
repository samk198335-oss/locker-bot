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
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")

DB_PATH = "data.db"

# ======================
# DATABASE
# ======================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surname TEXT UNIQUE,
            knife INTEGER,
            locker TEXT
        )
        """)

# ======================
# RENDER KEEP ALIVE
# ======================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_healthcheck():
    HTTPServer(("0.0.0.0", 10000), HealthHandler).serve_forever()

# ======================
# HELPERS
# ======================
def keyboard():
    return ReplyKeyboardMarkup(
        [
            ["🗡 З ножем", "🚫 Без ножа"],
            ["🗄 З шафкою", "❌ Без шафки"],
            ["👥 Всі", "📊 Статистика"],
        ],
        resize_keyboard=True,
    )

def format_workers(rows, show_locker=False):
    if not rows:
        return "❌ Немає даних"
    text = ""
    for r in rows:
        if show_locker:
            text += f"• {r['surname']} — {r['locker']}\n"
        else:
            text += f"• {r['surname']}\n"
    return text

# ======================
# COMMANDS
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Обери фільтр або команду 👇",
        reply_markup=keyboard(),
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
        knife = db.execute("SELECT COUNT(*) FROM workers WHERE knife=1").fetchone()[0]
        no_knife = db.execute("SELECT COUNT(*) FROM workers WHERE knife=0").fetchone()[0]
        locker = db.execute("SELECT COUNT(*) FROM workers WHERE locker!='-'").fetchone()[0]
        no_locker = db.execute("SELECT COUNT(*) FROM workers WHERE locker='-'").fetchone()[0]

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n"
        f"🗡 З ножем: {knife}\n"
        f"🚫 Без ножа: {no_knife}\n"
        f"🗄 З шафкою: {locker}\n"
        f"❌ Без шафки: {no_locker}"
    )

async def add_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        surname, knife, locker = context.args
        knife = int(knife)
        with get_db() as db:
            db.execute(
                "INSERT INTO workers (surname, knife, locker) VALUES (?, ?, ?)",
                (surname, knife, locker),
            )
        await update.message.reply_text("✅ Працівника додано")
    except Exception as e:
        await update.message.reply_text("❌ Помилка додавання")

async def rename_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        old, new = context.args
        with get_db() as db:
            db.execute(
                "UPDATE workers SET surname=? WHERE surname=?",
                (new, old),
            )
        await update.message.reply_text("✅ Прізвище змінено")
    except:
        await update.message.reply_text("❌ Помилка")

async def delete_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        surname = context.args[0]
        with get_db() as db:
            db.execute("DELETE FROM workers WHERE surname=?", (surname,))
        await update.message.reply_text("🗑 Видалено")
    except:
        await update.message.reply_text("❌ Помилка")

async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_db() as db:
        rows = db.execute("SELECT * FROM workers").fetchall()
    await update.message.reply_text(format_workers(rows))

# ======================
# BUTTON HANDLER
# ======================
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    with get_db() as db:
        if "З ножем" in text:
            rows = db.execute("SELECT * FROM workers WHERE knife=1").fetchall()
            await update.message.reply_text(format_workers(rows))
        elif "Без ножа" in text:
            rows = db.execute("SELECT * FROM workers WHERE knife=0").fetchall()
            await update.message.reply_text(format_workers(rows))
        elif "З шафкою" in text:
            rows = db.execute("SELECT * FROM workers WHERE locker!='-'").fetchall()
            await update.message.reply_text(format_workers(rows, True))
        elif "Без шафки" in text:
            rows = db.execute("SELECT * FROM workers WHERE locker='-'").fetchall()
            await update.message.reply_text(format_workers(rows))
        elif "Всі" in text:
            rows = db.execute("SELECT * FROM workers").fetchall()
            await update.message.reply_text(format_workers(rows))
        elif "Статистика" in text:
            await stats(update, context)

# ======================
# MAIN
# ======================
if __name__ == "__main__":
    init_db()

    threading.Thread(target=run_healthcheck, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("add", add_worker))
    app.add_handler(CommandHandler("rename", rename_worker))
    app.add_handler(CommandHandler("delete", delete_worker))
    app.add_handler(CommandHandler("list", list_all))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))

    app.run_polling()
