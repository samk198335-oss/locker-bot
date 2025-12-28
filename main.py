import os
import csv
import requests
from io import StringIO
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/ID/export?format=csv"


def load_sheet():
    response = requests.get(CSV_URL, timeout=10)
    response.encoding = "utf-8"
    reader = csv.DictReader(StringIO(response.text))
    return list(reader)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот успішно запущений ✅\n\n"
        "Команди:\n"
        "/find <прізвище>\n"
        "/locker <номер>"
    )


async def find_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Використання: /find <прізвище>")
        return

    query = " ".join(context.args).lower()
    rows = load_sheet()

    results = []
    for row in rows:
        if query in row["surname"].lower():
            results.append(row)

    if not results:
        await update.message.reply_text("Нічого не знайдено ❌")
        return

    text = ""
    for r in results:
        text += (
            f"👤 {r['surname']}\n"
            f"📍 {r['Adress']}\n"
            f"🔪 Ножі: {r['knife']}\n"
            f"🔐 Локер: {r['locker']}\n"
            f"———————————\n"
        )

    await update.message.reply_text(text)


async def find_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Використання: /locker <номер>")
        return

    locker = " ".join(context.args).lower()
    rows = load_sheet()

    results = [r for r in rows if locker == r["locker"].lower()]

    if not results:
        await update.message.reply_text("Локер не знайдено ❌")
        return

    text = ""
    for r in results:
        text += (
            f"👤 {r['surname']}\n"
            f"📍 {r['Adress']}\n"
            f"🔪 Ножі: {r['knife']}\n"
            f"🔐 Локер: {r['locker']}\n"
            f"———————————\n"
        )

    await update.message.reply_text(text)


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_person))
    app.add_handler(CommandHandler("locker", find_locker))

    app.run_polling()


if __name__ == "__main__":
    main()
