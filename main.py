import os
import csv
import re
import time
import shutil
import threading
from datetime import datetime
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, Document
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==============================
# RENDER KEEP-ALIVE
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_http():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

threading.Thread(target=run_http, daemon=True).start()

# ==============================
# CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = os.getenv(
    "CSV_URL",
    "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
)

LOCAL_DB = "local_data.csv"
BACKUP_DIR = "backups"
BACKUP_CHAT_ID = int(os.getenv("BACKUP_CHAT_ID", "0") or 0)

os.makedirs(BACKUP_DIR, exist_ok=True)

# ==============================
# HELPERS
# ==============================

def now():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def norm(v):
    return re.sub(r"\s+", " ", (v or "").strip())

def low(v):
    return norm(v).lower()

def locker_has_value(v: str) -> bool:
    v = norm(v)
    if not v:
        return False
    if low(v) in {"-", "—", "–", "нема", "ні", "нет", "no", "none"}:
        return False
    return True

def knife_has(v: str) -> bool:
    v = norm(v)
    return v in {"1", "2"}

def read_db():
    if not os.path.exists(LOCAL_DB):
        return []
    with open(LOCAL_DB, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_db(rows):
    with open(LOCAL_DB, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Address", "surname", "knife", "locker"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

# ==============================
# BACKUP
# ==============================

async def make_backup(context, reason):
    name = f"backup_{now()}_{reason}.csv"
    path = os.path.join(BACKUP_DIR, name)
    shutil.copyfile(LOCAL_DB, path)

    if BACKUP_CHAT_ID:
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=BACKUP_CHAT_ID,
                document=f,
                caption=f"💾 Backup ({reason})"
            )

# ==============================
# MENU
# ==============================

KB = ReplyKeyboardMarkup(
    [
        ["📊 Статистика", "👥 Всі"],
        ["🗄️ З шафкою", "⛔ Без шафки"],
        ["🔪 З ножем", "🚫 Без ножа"],
        ["➕ Додати працівника", "✏️ Редагувати працівника"],
        ["🗑️ Видалити працівника"],
        ["💾 Backup бази", "🧬 Seed з Google"],
        ["♻️ Відновити з файлу"],
    ],
    resize_keyboard=True
)

STATE = {"mode": None, "tmp": {}}

def reset():
    STATE["mode"] = None
    STATE["tmp"] = {}

# ==============================
# COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset()
    await update.message.reply_text("Готово 👇", reply_markup=KB)

async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"chat_id = {update.effective_chat.id}")

# ==============================
# TEXT HANDLER
# ==============================

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = norm(update.message.text)
    rows = read_db()

    if t == "📊 Статистика":
        total = len(rows)
        with_locker = sum(1 for r in rows if locker_has_value(r.get("locker")))
        no_locker = total - with_locker
        with_knife = sum(1 for r in rows if knife_has(r.get("knife")))
        no_knife = total - with_knife
        await update.message.reply_text(
            f"Всього: {total}\n"
            f"🗄️ З шафкою: {with_locker}\n"
            f"⛔ Без шафки: {no_locker}\n"
            f"🔪 З ножем: {with_knife}\n"
            f"🚫 Без ножа: {no_knife}",
            reply_markup=KB
        )
        return

    if t == "🗄️ З шафкою":
        out = [
            f"{r['surname']} — {r['locker']}"
            for r in rows if locker_has_value(r.get("locker"))
        ]
        await update.message.reply_text("\n".join(out) or "Немає", reply_markup=KB)
        return

    if t == "⛔ Без шафки":
        out = [r["surname"] for r in rows if not locker_has_value(r.get("locker"))]
        await update.message.reply_text("\n".join(out) or "Немає", reply_markup=KB)
        return

    if t == "🔪 З ножем":
        out = [r["surname"] for r in rows if knife_has(r.get("knife"))]
        await update.message.reply_text("\n".join(out) or "Немає", reply_markup=KB)
        return

    if t == "🚫 Без ножа":
        out = [r["surname"] for r in rows if not knife_has(r.get("knife"))]
        await update.message.reply_text("\n".join(out) or "Немає", reply_markup=KB)
        return

    if t == "💾 Backup бази":
        await make_backup(context, "manual")
        await update.message.reply_text("💾 Backup зроблено", reply_markup=KB)
        return

    await update.message.reply_text("Обери дію 👇", reply_markup=KB)

# ==============================
# MAIN
# ==============================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chatid", chatid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling()

if __name__ == "__main__":
    main()
