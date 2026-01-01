import os
import threading
import requests
import csv
from io import StringIO

from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== CONFIG ==================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

PORT = int(os.environ.get("PORT", 10000))

# ============================================

# ---------- FLASK (Render Free needs open port) ----------

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive 🚀"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ---------- CSV ----------

def load_csv():
    r = requests.get(CSV_URL, timeout=15)
    r.raise_for_status()
    f = StringIO(r.text)
    return list(csv.DictReader(f))

# ---------- HELPERS ----------

def has_knife(v: str) -> bool:
    return v.strip() != "0"

def has_locker(v: str) -> bool:
    return v.strip() != "0"

# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вітаю 👋\n\n"
        "Доступні команди:\n"
        "/find <прізвище>\n"
        "/knife — з ножем\n"
        "/no_knife — без ножа\n"
        "/with_locker — з шафкою\n"
        "/no_locker — без шафки"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажи прізвище після /find")
        return

    query = " ".join(context.args).lower()
    rows = load_csv()

    results = []
    for r in rows:
        if query in r["surname"].lower():
            results.append(r)

    if not results:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = ""
    for r in results:
        text += (
            f"📍 {r['Adress']}\n"
            f"👤 {r['surname']}\n"
            f"🔪 Ніж: {'є' if has_knife(r['knife']) else 'немає'}\n"
            f"🧥 Шафка: {'є' if has_locker(r['locker']) else 'немає'}\n\n"
        )

    await update.message.reply_text(text)

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    res = [r for r in rows if has_knife(r["knife"])]
    await update.message.reply_text(f"🔪 З ножем: {len(res)}")

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    res = [r for r in rows if not has_knife(r["knife"])]
    await update.message.reply_text(f"🚫 Без ножа: {len(res)}")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    res = [r for r in rows if has_locker(r["locker"])]
    await update.message.reply_text(f"🧥 З шафкою: {len(res)}")

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    res = [r for r in rows if not has_locker(r["locker"])]
    await update.message.reply_text(f"🚫 Без шафки: {len(res)}")

# ---------- MAIN ----------

def main():
    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("find", find))
    app_tg.add_handler(CommandHandler("knife", knife))
    app_tg.add_handler(CommandHandler("no_knife", no_knife))
    app_tg.add_handler(CommandHandler("with_locker", with_locker))
    app_tg.add_handler(CommandHandler("no_locker", no_locker))

    app_tg.run_polling()

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    main()
