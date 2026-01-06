import os
import csv
import time
import sqlite3
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==============================
# 🔧 CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

DB_PATH = "data.db"

ADMINS = {"admin_username_1", "admin_username_2"}

# ==============================
# 🗄️ DATABASE
# ==============================

def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    db = get_db()
    cur = db.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            surname TEXT UNIQUE,
            knife TEXT,
            locker TEXT
        )
    """)

    db.commit()
    db.close()


def db_is_empty():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM workers")
    count = cur.fetchone()[0]
    db.close()
    return count == 0


# ==============================
# 🔁 CSV → SQLITE (ONE TIME)
# ==============================

def import_csv_once():
    if not db_is_empty():
        return

    response = requests.get(CSV_URL, timeout=10)
    response.encoding = "utf-8"

    reader = csv.DictReader(StringIO(response.text))
    rows = list(reader)

    db = get_db()
    cur = db.cursor()

    for r in rows:
        cur.execute("""
            INSERT OR IGNORE INTO workers (address, surname, knife, locker)
            VALUES (?, ?, ?, ?)
        """, (
            r.get("Address", "").strip(),
            r.get("surname", "").strip(),
            r.get("knife", "").strip(),
            r.get("locker", "").strip()
        ))

    db.commit()
    db.close()


# ==============================
# 🧠 HELPERS
# ==============================

def is_yes(value: str) -> bool:
    return value.strip().lower() in ("1", "yes", "y", "так", "є", "true", "+")


def has_locker(value: str) -> bool:
    return value.strip().lower() not in ("", "-", "ні", "no", "0")


def is_admin(update: Update) -> bool:
    return update.effective_user.username in ADMINS


def fetch_all():
    db = get_db()
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT * FROM workers").fetchall()
    db.close()
    return rows


# ==============================
# 🤖 COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Доступні команди:\n"
        "/stats\n"
        "/locker_list\n"
        "/no_locker_list\n"
        "/knife_list\n"
        "/no_knife_list"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = fetch_all()

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


async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = fetch_all()
    result = [
        f"{r['surname']} — {r['locker']}"
        for r in rows
        if r["surname"] and has_locker(r["locker"])
    ]

    await update.message.reply_text(
        "🗄️ З шафкою:\n\n" + "\n".join(result) if result else "❌ Немає даних"
    )


async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = fetch_all()
    result = [
        r["surname"]
        for r in rows
        if r["surname"] and not has_locker(r["locker"])
    ]

    await update.message.reply_text(
        "❌ Без шафки:\n\n" + "\n".join(result) if result else "❌ Немає даних"
    )


async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = fetch_all()
    result = [r["surname"] for r in rows if is_yes(r["knife"])]

    await update.message.reply_text(
        "🔪 З ножем:\n\n" + "\n".join(result) if result else "❌ Немає даних"
    )


async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = fetch_all()
    result = [r["surname"] for r in rows if not is_yes(r["knife"])]

    await update.message.reply_text(
        "🚫 Без ножа:\n\n" + "\n".join(result) if result else "❌ Немає даних"
    )


# ==============================
# 🔐 ADMIN COMMANDS
# ==============================

async def replace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await update.message.reply_text("⛔ Немає доступу")

    if len(context.args) != 2:
        return await update.message.reply_text("Формат:\n/replace СтареПрізвище НовеПрізвище")

    old, new = context.args

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE workers SET surname=? WHERE surname=?", (new, old))
    db.commit()
    db.close()

    await update.message.reply_text("✅ Прізвище оновлено")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await update.message.reply_text("⛔ Немає доступу")

    if not context.args:
        return await update.message.reply_text(
            "Формат:\n/add Прізвище knife=1 locker=25"
        )

    surname = context.args[0]
    knife = ""
    locker = ""

    for arg in context.args[1:]:
        if arg.startswith("knife="):
            knife = arg.split("=")[1]
        if arg.startswith("locker="):
            locker = arg.split("=")[1]

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO workers (surname, knife, locker)
        VALUES (?, ?, ?)
    """, (surname, knife, locker))
    db.commit()
    db.close()

    await update.message.reply_text("✅ Працівника додано")


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
    import_csv_once()

    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))

    app.add_handler(CommandHandler("replace", replace))
    app.add_handler(CommandHandler("add", add))

    app.run_polling()


if __name__ == "__main__":
    main()
