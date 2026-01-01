import os
import csv
import requests
from io import StringIO
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# =========================
# НАЛАШТУВАННЯ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"

# Колонки в таблиці:
# 0 - Date
# 1 - Address
# 2 - Surname
# 3 - Knife
# 4 - Locker

# =========================
# ДОПОМІЖНІ ФУНКЦІЇ
# =========================

def load_rows():
    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()
    csv_data = response.text
    reader = csv.reader(StringIO(csv_data))
    rows = list(reader)
    return rows[1:]  # без заголовка


def format_rows(rows):
    if not rows:
        return "❌ Нічого не знайдено"

    text = ""
    for r in rows:
        date = r[0]
        address = r[1]
        surname = r[2]
        knife = r[3]
        locker = r[4]

        text += (
            f"📅 {date}\n"
            f"📍 {address}\n"
            f"👤 {surname}\n"
            f"🔪 Ніж: {knife}\n"
            f"🗄 Шафка: {locker}\n"
            f"------------------\n"
        )
    return text


# =========================
# КОМАНДИ
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\n"
        "Available commands:\n"
        "/find\n"
        "/knife\n"
        "/no_knife\n"
        "/with_locker\n"
        "/no_locker\n"
        "/myid"
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Your ID: {update.effective_user.id}")


async def find_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    await update.message.reply_text(format_rows(rows))


async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    filtered = [r for r in rows if r[3].strip() not in ("", "0", "-")]
    await update.message.reply_text(format_rows(filtered))


async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    filtered = [r for r in rows if r[3].strip() in ("", "0", "-")]
    await update.message.reply_text(format_rows(filtered))


async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    filtered = [r for r in rows if r[4].strip() not in ("", "-", "0")]
    await update.message.reply_text(format_rows(filtered))


async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    filtered = [r for r in rows if r[4].strip() in ("", "-", "0")]
    await update.message.reply_text(format_rows(filtered))


# =========================
# ЗАПУСК
# =========================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_all))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))
    app.add_handler(CommandHandler("myid", myid))

    app.run_polling()


if __name__ == "__main__":
    main()
