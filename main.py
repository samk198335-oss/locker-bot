import os
import requests
import csv
import io
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"


def load_data():
    response = requests.get(CSV_URL, timeout=15)
    response.raise_for_status()

    reader = csv.DictReader(io.StringIO(response.text))
    return list(reader)


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
    data = load_data()
    await update.message.reply_text(
        f"📊 Rows in table: {len(data)}"
    )


async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [r for r in data if r.get("knife") in ("1", "2")]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text(f"🔪 З ножем: {len(result)}")


async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [r for r in data if r.get("knife") == "0"]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text(f"🚫🔪 Без ножа: {len(result)}")


async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [r for r in data if r.get("locker") not in ("", "-", "0")]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text(f"🔐 З шафкою: {len(result)}")


async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [r for r in data if r.get("locker") in ("", "-", "0")]

    if not result:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text(f"🚫🔐 Без шафки: {len(result)}")


async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))
    app.add_handler(CommandHandler("myid", myid))

    # 🔥 КЛЮЧОВИЙ ФІКС ДЛЯ RENDER
    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
