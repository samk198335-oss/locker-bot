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
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "bot.db"

# ==============================
# 🗄️ DATABASE
# ==============================

def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                surname TEXT NOT NULL UNIQUE,
                knife INTEGER NOT NULL,
                locker TEXT
            )
        """)

def load_workers():
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM workers").fetchall()

# ==============================
# 🧠 HELPERS
# ==============================

def is_yes(value) -> bool:
    return str(value).strip() == "1"

def has_locker(value) -> bool:
    return value and str(value).strip() not in ("-", "0", "")

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
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Обери фільтр або команду 👇",
        reply_markup=KEYBOARD
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_workers()

    total = len(rows)
    knife_yes = knife_no = locker_yes = locker_no = 0

    for r in rows:
        if is_yes(r["knife"]):
            knife_yes += 1
        else:
            knife_no += 1

        if has_locker(r["locker"]):
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def all_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_workers()
    result = [r["surname"] for r in rows]
    await update.message.reply_text("👥 Всі:\n\n" + "\n".join(result) if result else "❌ Немає даних")

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_workers()
    result = [r["surname"] for r in rows if is_yes(r["knife"])]
    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(result) if result else "❌ Немає даних")

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_workers()
    result = [r["surname"] for r in rows if not is_yes(r["knife"])]
    await update.message.reply_text("🚫 Без ножа:\n\n" + "\n".join(result) if result else "❌ Немає даних")

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_workers()
    result = [f'{r["surname"]} — {r["locker"]}' for r in rows if has_locker(r["locker"])]
    await update.message.reply_text("🗄️ З шафкою:\n\n" + "\n".join(result) if result else "❌ Немає даних")

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_workers()
    result = [r["surname"] for r in rows if not has_locker(r["locker"])]
    await update.message.reply_text("❌ Без шафки:\n\n" + "\n".join(result) if result else "❌ Немає даних")

# ==============================
# ✏️ EDIT COMMANDS
# ==============================

async def add_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        surname, knife, locker = context.args
        with get_db() as conn:
            conn.execute(
                "INSERT INTO workers (surname, knife, locker) VALUES (?, ?, ?)",
                (surname, int(knife), None if locker == "-" else locker)
            )
        await update.message.reply_text("✅ Додано")
    except Exception as e:
        await update.message.reply_text("❌ Помилка додавання")

async def rename_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        old, new = context.args
        with get_db() as conn:
            conn.execute("UPDATE workers SET surname=? WHERE surname=?", (new, old))
        await update.message.reply_text("✅ Оновлено")
    except:
        await update.message.reply_text("❌ Помилка")

async def setknife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        surname, value = context.args
        with get_db() as conn:
            conn.execute("UPDATE workers SET knife=? WHERE surname=?", (int(value), surname))
        await update.message.reply_text("✅ Оновлено")
    except:
        await update.message.reply_text("❌ Помилка")

async def setlocker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        surname, value = context.args
        with get_db() as conn:
            conn.execute(
                "UPDATE workers SET locker=? WHERE surname=?",
                (None if value == "-" else value, surname)
            )
        await update.message.reply_text("✅ Оновлено")
    except:
        await update.message.reply_text("❌ Помилка")

# ==============================
# 🎛️ FILTER HANDLER
# ==============================

async def handle_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🔪 З ножем":
        await knife_list(update, context)
    elif text == "🚫 Без ножа":
        await no_knife_list(update, context)
    elif text == "🗄️ З шафкою":
        await locker_list(update, context)
    elif text == "❌ Без шафки":
        await no_locker_list(update, context)
    elif text == "👥 Всі":
        await all_list(update, context)
    elif text == "📊 Статистика":
        await stats(update, context)

# ==============================
# 🌐 RENDER KEEP ALIVE
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
    app.add_handler(CommandHandler("add", add_worker))
    app.add_handler(CommandHandler("rename", rename_worker))
    app.add_handler(CommandHandler("setknife", setknife))
    app.add_handler(CommandHandler("setlocker", setlocker))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filters))

    app.run_polling()

if __name__ == "__main__":
    main()
