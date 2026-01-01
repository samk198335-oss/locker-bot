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

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive 🚀"

# ---------- CSV LOAD ----------

def load_csv():
    response = requests.get(CSV_URL, timeout=15)
    response.raise_for_status()
    f = StringIO(response.text)
    return list(csv.DictReader(f))

def has_locker(value: str) -> bool:
    if not value:
        return False
    value = value.strip().lower()
    return value not in ["-", "0", "ні", "нет"]

# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт 👋\n\n"
        "Команди:\n"
        "/знайти Прізвище\n"
        "/ніж\n"
        "/безножа\n"
        "/зшафкою\n"
        "/безшафки"
    )

async def find_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажи прізвище після команди.")
        return

    query = " ".join(context.args).lower()
    rows = load_csv()

    results = [r for r in rows if query in r["surname"].lower()]

    if not results:
        await update.message.reply_text("Нічого не знайдено.")
        return

    text = ""
    for r in results:
        text += (
            f"📍 {r['Adress']}\n"
            f"👤 {r['surname']}\n"
            f"🔪 Ніж: {'є' if r['knife'] != '0' else 'немає'}\n"
            f"🧥 Шафка: {'є' if has_locker(r['locker']) else 'немає'}\n\n"
        )

    await update.message.reply_text(text)

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    await update.message.reply_text(f"🔪 З ножем: {len([r for r in rows if r['knife'] != '0'])}")

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    await update.message.reply_text(f"🚫 Без ножа: {len([r for r in rows if r['knife'] == '0'])}")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    await update.message.reply_text(f"🧥 З шафкою: {len([r for r in rows if has_locker(r['locker'])])}")

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    await update.message.reply_text(f"🚫 Без шафки: {len([r for r in rows if not has_locker(r['locker'])])}")

# ---------- TELEGRAM THREAD ----------

def run_bot():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("знайти", find_person))
    application.add_handler(CommandHandler("ніж", knife))
    application.add_handler(CommandHandler("безножа", no_knife))
    application.add_handler(CommandHandler("зшафкою", with_locker))
    application.add_handler(CommandHandler("безшафки", no_locker))

    application.run_polling()

# ---------- MAIN ----------

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
