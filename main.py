import os
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

DB_FILE = "data.db"

# =========================
# DATABASE
# =========================
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            surname TEXT NOT NULL,
            knife INTEGER NOT NULL,
            locker TEXT
        )
    """)
    conn.commit()
    conn.close()


# =========================
# HEALTHCHECK (RENDER)
# =========================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def run_health_server():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()


# =========================
# HELPERS
# =========================
def format_workers(rows):
    if not rows:
        return "❌ Немає даних"
    return "\n".join(
        f"• {r['surname']}"
        + (f" | 🗄 {r['locker']}" if r["locker"] else "")
        for r in rows
    )


# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄 З шафкою", "❌ Без шафки"],
        ["👥 Всі", "📊 Статистика"],
    ]
    await update.message.reply_text(
        "👋 Привіт! Обери фільтр або команду 👇",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
    knife = conn.execute("SELECT COUNT(*) FROM workers WHERE knife=1").fetchone()[0]
    no_knife = conn.execute("SELECT COUNT(*) FROM workers WHERE knife=0").fetchone()[0]
    locker = conn.execute("SELECT COUNT(*) FROM workers WHERE locker IS NOT NULL").fetchone()[0]
    no_locker = conn.execute("SELECT COUNT(*) FROM workers WHERE locker IS NULL").fetchone()[0]
    conn.close()

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"👥 Всього: {total}\n"
        f"🔪 З ножем: {knife}\n"
        f"🚫 Без ножа: {no_knife}\n"
        f"🗄 З шафкою: {locker}\n"
        f"❌ Без шафки: {no_locker}"
    )


async def list_all(update, context):
    conn = get_db()
    rows = conn.execute("SELECT * FROM workers").fetchall()
    conn.close()
    await update.message.reply_text(format_workers(rows))


async def list_knife(update, context):
    conn = get_db()
    rows = conn.execute("SELECT * FROM workers WHERE knife=1").fetchall()
    conn.close()
    await update.message.reply_text(format_workers(rows))


async def list_no_knife(update, context):
    conn = get_db()
    rows = conn.execute("SELECT * FROM workers WHERE knife=0").fetchall()
    conn.close()
    await update.message.reply_text(format_workers(rows))


async def list_locker(update, context):
    conn = get_db()
    rows = conn.execute("SELECT * FROM workers WHERE locker IS NOT NULL").fetchall()
    conn.close()
    await update.message.reply_text(format_workers(rows))


async def list_no_locker(update, context):
    conn = get_db()
    rows = conn.execute("SELECT * FROM workers WHERE locker IS NULL").fetchall()
    conn.close()
    await update.message.reply_text(format_workers(rows))


async def add_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.replace("/add", "").strip()
        surname, knife, locker = [x.strip() for x in text.split("|")]
        knife = int(knife)
        if locker == "-" or locker == "":
            locker = None

        conn = get_db()
        conn.execute(
            "INSERT INTO workers (surname, knife, locker) VALUES (?, ?, ?)",
            (surname, knife, locker),
        )
        conn.commit()
        conn.close()

        await update.message.reply_text("✅ Працівника додано")

    except Exception as e:
        await update.message.reply_text("❌ Формат:\n/add Прізвище Імʼя | 1/0 | номер/-")


async def rename_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.replace("/rename", "").strip()
        old, new = [x.strip() for x in text.split("|")]

        conn = get_db()
        cur = conn.execute(
            "UPDATE workers SET surname=? WHERE surname=?",
            (new, old),
        )
        conn.commit()
        conn.close()

        if cur.rowcount == 0:
            await update.message.reply_text("❌ Не знайдено")
        else:
            await update.message.reply_text("✅ Прізвище оновлено")

    except:
        await update.message.reply_text("❌ Формат:\n/rename Старе | Нове")


# =========================
# MAIN
# =========================
def main():
    init_db()

    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("all", list_all))
    app.add_handler(CommandHandler("knife", list_knife))
    app.add_handler(CommandHandler("no_knife", list_no_knife))
    app.add_handler(CommandHandler("locker", list_locker))
    app.add_handler(CommandHandler("no_locker", list_no_locker))
    app.add_handler(CommandHandler("add", add_worker))
    app.add_handler(CommandHandler("rename", rename_worker))

    app.run_polling()


if __name__ == "__main__":
    main()
