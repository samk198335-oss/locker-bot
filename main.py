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
# Допоміжні функції
# =========================

def has_value(value):
    return value and value.strip() not in ["0", "ні", "no", ""]

# =========================
# Команди бота
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт 👋\n\n"
        "Доступні команди:\n"
        "/знайти Прізвище\n"
        "/локер Номер\n"
        "/ніж\n"
        "/безножа\n"
        "/зшафкою\n"
        "/безшафки"
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

    await send_results(update, results)

async def локер(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Використання: /локер Номер")
        return

    locker_number = context.args[0]
    rows = load_table()

    results = [
        r for r in rows
        if r.get("locker", "").strip() == locker_number
    ]

    if not results:
        await update.message.reply_text("Локер не знайдено")
        return

    await send_results(update, results)

async def ніж(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_table()
    results = [r for r in rows if has_value(r.get("knife"))]

    if not results:
        await update.message.reply_text("Немає працівників з ножем")
        return

    await send_results(update, results)

async def безножа(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_table()
    results = [r for r in rows if not has_value(r.get("knife"))]

    if not results:
        await update.message.reply_text("Усі мають ніж")
        return

    await send_results(update, results)

async def зшафкою(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_table()
    results = [r for r in rows if has_value(r.get("locker"))]

    if not results:
        await update.message.reply_text("Немає працівників з шафкою")
        return

    await send_results(update, results)

async def безшафки(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_table()
    results = [r for r in rows if not has_value(r.get("locker"))]

    if not results:
        await update.message.reply_text("Усі мають шафку")
        return

# =========================
# Формування відповіді
# =========================

async def send_results(update: Update, results):
    text = ""
    for r in results:
        text += (
            f"👤 {r.get('surname')}\n"
            f"📍 Адреса: {r.get('adress')}\n"
            f"🔪 Ніж: {r.get('knife') or '—'}\n"
            f"🔐 Шафка: {r.get('locker') or '—'}\n\n"
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
    app.add_handler(CommandHandler("ніж", ніж))
    app.add_handler(CommandHandler("безножа", безножа))
    app.add_handler(CommandHandler("зшафкою", зшафкою))
    app.add_handler(CommandHandler("безшафки", безшафки))

    print("🤖 Бот запущений")
    app.run_polling()

if __name__ == "__main__":
    main()
    
