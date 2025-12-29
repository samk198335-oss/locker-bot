import os
import csv
import requests
from io import StringIO
from flask import Flask
from threading import Thread

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ================== CONFIG ==================

BOT_TOKEN = "PASTE_YOUR_BOT_TOKEN"
CSV_URL = "PASTE_YOUR_CSV_LINK"
ADMIN_ID = 123456789  # <-- вставиш свій ID після /myid

PORT = int(os.environ.get("PORT", 10000))

# ================== FLASK (Render needs open port) ==================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ================== HELPERS ==================

def load_data():
    response = requests.get(CSV_URL)
    response.encoding = "utf-8"
    csv_data = StringIO(response.text)
    reader = csv.DictReader(csv_data)
    return list(reader)

def format_rows(rows):
    if not rows:
        return "❌ Нічого не знайдено"
    text = ""
    for r in rows:
        text += (
            f"👤 {r['Прізвище']}\n"
            f"🔪 Ніж: {r['Ніж']}\n"
            f"🗄 Шафка: {r['Шафка'] or '—'}\n"
            f"📍 Адреса: {r['Адреса']}\n\n"
        )
    return text

# ================== COMMANDS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю!\n\n"
        "/find – знайти всіх\n"
        "/knife – з ножем\n"
        "/no_knife – без ножа\n"
        "/with_locker – з шафкою\n"
        "/no_locker – без шафки\n\n"
        "/myid – показати мій Telegram ID"
    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Твій Telegram ID: {update.effective_user.id}")

async def find_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    await update.message.reply_text(format_rows(rows))

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [r for r in load_data() if r["Ніж"].lower() == "так"]
    await update.message.reply_text(format_rows(rows))

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [r for r in load_data() if r["Ніж"].lower() != "так"]
    await update.message.reply_text(format_rows(rows))

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [r for r in load_data() if r["Шафка"].strip()]
    await update.message.reply_text(format_rows(rows))

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [r for r in load_data() if not r["Шафка"].strip()]
    await update.message.reply_text(format_rows(rows))

# ================== ADMIN ==================

async def add_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Немає доступу")
        return

    try:
        data = " ".join(context.args)
        surname, knife, locker, address = [x.strip() for x in data.split(",")]
    except:
        await update.message.reply_text(
            "❌ Формат:\n/add Прізвище,ніж,шафка,адреса"
        )
        return

    # Google Sheet append через Google Form / Apps Script (наступний крок)
    await update.message.reply_text(
        "✅ Дані прийняті.\n(Додавання в таблицю — наступний крок)"
    )

# ================== MAIN ==================

def main():
    Thread(target=run_flask).start()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", myid))
    application.add_handler(CommandHandler("find", find_all))
    application.add_handler(CommandHandler("knife", knife))
    application.add_handler(CommandHandler("no_knife", no_knife))
    application.add_handler(CommandHandler("with_locker", with_locker))
    application.add_handler(CommandHandler("no_locker", no_locker))
    application.add_handler(CommandHandler("add", add_employee))

    application.run_polling()

if __name__ == "__main__":
    main()
