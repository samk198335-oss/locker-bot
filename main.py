import os
import sys
import csv
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"


def load_data():
    import requests
    response = requests.get(CSV_URL, timeout=30)
    response.raise_for_status()
    rows = []
    reader = csv.reader(response.text.splitlines())
    for row in reader:
        rows.append(row)
    return rows


DATA = load_data()


def filter_data(col_index: int, value: str):
    result = []
    for row in DATA[1:]:
        if len(row) > col_index and row[col_index].strip().lower() == value:
            result.append(" | ".join(row))
    return result


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\nAvailable commands:\n"
        "/find\n"
        "/knife\n"
        "/no_knife\n"
        "/with_locker\n"
        "/no_locker\n"
        "/myid"
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Your ID: {update.effective_user.id}")


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = filter_data(0, "yes")
    await reply_result(update, res)


async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = filter_data(1, "yes")
    await reply_result(update, res)


async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = filter_data(1, "no")
    await reply_result(update, res)


async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = filter_data(2, "yes")
    await reply_result(update, res)


async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = filter_data(2, "no")
    await reply_result(update, res)


async def reply_result(update: Update, result):
    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return
    text = "\n\n".join(result[:20])
    await update.message.reply_text(text)


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))
    app.add_handler(CommandHandler("myid", myid))

    await app.run_polling(close_loop=False)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        # Render already has a running loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
