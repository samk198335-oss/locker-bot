import os
import csv
import requests
from io import StringIO

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"


def load_data():
    response = requests.get(CSV_URL)
    response.encoding = "utf-8"
    reader = csv.DictReader(StringIO(response.text))
    return list(reader)


# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Команди:\n"
        "/find Прізвище\n"
        "/knife\n"
        "/no_knife\n"
        "/with_locker\n"
        "/no_locker"
    )


async def find_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Вкажи прізвище після /find")
        return

    query = " ".join(context.args).lower()
    data = load_data()

    results = [
        row for row in data
        if query in row.get("surname", "").lower()
    ]

    if not results:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = ""
    for r in results:
        text += (
            f"📍 {r.get('Adress','')}\n"
            f"👤 {r.get('surname','')}\n"
            f"🔪 knife: {r.get('knife','')}\n"
            f"🗄 locker: {r.get('locker','')}\n\n"
        )

    await update.message.reply_text(text)


async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    count = sum(
        1 for r in data
        if r.get("knife", "").isdigit() and int(r["knife"]) > 0
    )
    await update.message.reply_text(f"🔪 З ножем: {count}")


async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    count = sum(
        1 for r in data
        if r.get("knife", "").isdigit() and int(r["knife"]) == 0
    )
    await update.message.reply_text(f"🚫 Без ножа: {count}")


async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    count = sum(
        1 for r in data
        if r.get("locker")
        and r.get("locker").strip() != "-"
    )
    await update.message.reply_text(f"🗄 З шафкою: {count}")


async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    count = sum(
        1 for r in data
        if not r.get("locker") or r.get("locker").strip() == "-"
    )
    await update.message.reply_text(f"🚫 Без шафки: {count}")


# ---------- MAIN ----------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find_person))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    app.run_polling()


if __name__ == "__main__":
    main()
