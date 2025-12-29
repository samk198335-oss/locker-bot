import os
import csv
import requests
from io import StringIO

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =========================
# НАЛАШТУВАННЯ
# =========================

TOKEN = os.getenv("BOT_TOKEN")

# 🔗 ПРЯМЕ CSV-посилання на Google Sheets
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"

# =========================
# ДОПОМІЖНІ ФУНКЦІЇ
# =========================

def load_data():
    response = requests.get(GOOGLE_SHEET_CSV_URL)
    response.encoding = "utf-8"
    csv_data = csv.DictReader(StringIO(response.text))
    return list(csv_data)


def filter_data(**conditions):
    data = load_data()
    result = []

    for row in data:
        ok = True
        for key, value in conditions.items():
            if row.get(key, "").strip().lower() != value.lower():
                ok = False
                break
        if ok:
            result.append(row)

    return result


def format_result(rows):
    if not rows:
        return "❌ Нічого не знайдено"

    text = "✅ Знайдено локери:\n\n"
    for r in rows:
        text += (
            f"📦 Локер: {r.get('locker', '-')}\n"
            f"🔪 Ніж: {r.get('knife', '-')}\n"
            f"🗄️ Шафка: {r.get('locker_box', '-')}\n\n"
        )
    return text


# =========================
# КОМАНДИ БОТА
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю!\n\n"
        "Доступні команди:\n"
        "/find – знайти всі\n"
        "/knife – з ножем\n"
        "/no_knife – без ножа\n"
        "/with_locker – з шафкою\n"
        "/no_locker – без шафки"
    )


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    await update.message.reply_text(format_result(rows))


async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = filter_data(knife="так")
    await update.message.reply_text(format_result(rows))


async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = filter_data(knife="ні")
    await update.message.reply_text(format_result(rows))


async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = filter_data(locker_box="так")
    await update.message.reply_text(format_result(rows))


async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = filter_data(locker_box="ні")
    await update.message.reply_text(format_result(rows))


# =========================
# ЗАПУСК БОТА
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    print("🤖 Бот запущений")
    app.run_polling()


if __name__ == "__main__":
    main()
