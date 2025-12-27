import os
import csv
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
TOKEN = os.getenv("BOT_TOKEN")

def load_data():
    response = requests.get(CSV_URL)
    response.encoding = "utf-8"
    rows = list(csv.DictReader(response.text.splitlines()))
    return rows

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот-локер готовий!\n\n"
        "/find Прізвище — знайти працівника\n"
        "/stats — статистика ножів"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Вкажи прізвище після /find")
        return

    surname = context.args[0].lower()
    data = load_data()

    for row in data:
        if row["Прізвище"].lower() == surname:
            knife = "✅ Є" if row["Ніж"] == "1" else "❌ Немає"
            text = (
                f"👤 {row['Прізвище']} {row['Імʼя']}\n"
                f"🗄 Шафка: {row['Шафка']}\n"
                f"🔪 Ніж: {knife}"
            )
            await update.message.reply_text(text)
            return

    await update.message.reply_text("❌ Працівника не знайдено")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    with_knife = sum(1 for r in data if r["Ніж"] == "1")
    without_knife = len(data) - with_knife

    await update.message.reply_text(
        f"📊 Статистика:\n"
        f"🔪 З ножами: {with_knife}\n"
        f"❌ Без ножів: {without_knife}"
    )

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("find", find))
app.add_handler(CommandHandler("stats", stats))

app.run_polling()
