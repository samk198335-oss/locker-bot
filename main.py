import os
import threading
from flask import Flask
import requests

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"

# ---------- Flask (тільки щоб Render не вбив сервіс) ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ---------- Helpers ----------
def load_data():
    response = requests.get(SHEET_CSV_URL, timeout=10)
    response.raise_for_status()
    rows = response.text.splitlines()
    return rows[1:]  # skip header


def filter_rows(keyword):
    rows = load_data()
    return [r for r in rows if keyword.lower() in r.lower()]


# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю!\n\n"
        "/find – знайти всі\n"
        "/knife – з ножем\n"
        "/no_knife – без ножа\n"
        "/with_locker – з шафкою\n"
        "/no_locker – без шафки"
    )


async def send_results(update: Update, rows):
    if not rows:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = "\n".join(rows[:20])
    await update.message.reply_text(text)


async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_results(update, load_data())


async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_results(update, filter_rows("ніж"))


async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_results(update, filter_rows("без ножа"))


async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_results(update, filter_rows("шаф"))


async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_results(update, filter_rows("без шаф"))


# ---------- Main ----------
def main():
    print("Starting Telegram bot polling...")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("find", find))
    application.add_handler(CommandHandler("knife", knife))
    application.add_handler(CommandHandler("no_knife", no_knife))
    application.add_handler(CommandHandler("with_locker", with_locker))
    application.add_handler(CommandHandler("no_locker", no_locker))

    application.run_polling()


if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    main()
