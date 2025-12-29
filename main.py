import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

SHEET_URL = "https://docs.google.com/spreadsheets/d/ID/export?format=csv"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот успішно запущений ✅")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Напиши прізвище після /find")
        return

    surname = " ".join(context.args).lower()
    data = requests.get(SHEET_URL).text.splitlines()

    for row in data[1:]:
        cols = row.split(",")
        if surname in cols[2].lower():
            await update.message.reply_text(
                f"📍 Адреса: {cols[1]}\n"
                f"👤 {cols[2]}\n"
                f"🔪 Ніж: {cols[3]}\n"
                f"🔐 Локер: {cols[4]}"
            )
            return

    await update.message.reply_text("Не знайдено")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.run_polling()

if __name__ == "__main__":
    main()
    
