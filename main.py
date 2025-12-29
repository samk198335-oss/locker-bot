import os
import csv
import requests
from io import StringIO
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =========================
# Налаштування
# =========================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# =========================
# Робота з таблицею
# =========================

def load_table():
    response = requests.get(CSV_URL)
    response.raise_for_status()

    csv_file = StringIO(response.text)
    reader = csv.DictReader(csv_file)
    return list(reader)

# =========================
# Команди бота
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт 👋\n"
        "Доступні команди:\n"
        "/знайти Прізвище\n"
        "/локер Номер\n"
    )

async def знайти(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Використання: /знайти Прізвище")
        return

    query = " ".join(context.args).lower()
    rows = load_table()

    results = [
        r for r in rows
        if query in r.get("surname", "").lower()
    ]

    if not results:
        await update.message.reply_text("Нічого не знайдено")
        return

    text = ""
    for r in results:
        text += (
            f"👤 {r.get('surname')}\n"
            f"📍 Адреса: {r.get('adress')}\n"
            f"🔐 Локер: {r.get('locker')}\n\n"
        )

    await update.message.reply_text(text)

async def локер(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Використання: /локер Номер")
        return

    locker_number = context.args[0]
    rows = load_table()

    results = [
        r for r in rows
        if r.get("locker") == locker_number
    ]

    if not results:
        await update.message.reply_text("Локер не знайдено")
        return

    text = ""
    for r in results:
        text += (
            f"👤 {r.get('surname')}\n"
            f"📍 Адреса: {r.get('adress')}\n"
            f"🔐 Локер: {r.get('locker')}\n\n"
        )

    await update.message.reply_text(text)

# =========================
# Запуск бота
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("знайти", знайти))
    app.add_handler(CommandHandler("локер", локер))

    print("🤖 Бот запущений")
    app.run_polling()

if __name__ == "__main__":
    main()

    
