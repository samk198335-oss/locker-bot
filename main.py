import os
import threading
import requests
import csv
from io import StringIO
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"

# Назви колонок (ТОЧНО як у таблиці)
COL_KNIFE = "Ніж"
COL_LOCKER = "Шафка"
COL_NAME = "Назва"

# ================== FLASK (для Render) ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================== CSV ==================
def load_data():
    response = requests.get(CSV_URL)
    response.raise_for_status()
    csv_file = StringIO(response.text)
    return list(csv.DictReader(csv_file))

def normalize(val):
    return str(val).strip().lower()

# ================== COMMANDS ==================
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

async def find_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_data()
    if not rows:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    text = "\n".join(f"• {r[COL_NAME]}" for r in rows)
    await update.message.reply_text(text)

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [
        r for r in load_data()
        if normalize(r.get(COL_KNIFE)) in ("так", "yes", "1")
    ]
    await update.message.reply_text(
        "\n".join(f"• {r[COL_NAME]}" for r in rows) or "❌ Нічого не знайдено"
    )

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [
        r for r in load_data()
        if normalize(r.get(COL_KNIFE)) in ("ні", "no", "0", "")
    ]
    await update.message.reply_text(
        "\n".join(f"• {r[COL_NAME]}" for r in rows) or "❌ Нічого не знайдено"
    )

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [
        r for r in load_data()
        if normalize(r.get(COL_LOCKER)) in ("так", "yes", "1")
    ]
    await update.message.reply_text(
        "\n".join(f"• {r[COL_NAME]}" for r in rows) or "❌ Нічого не знайдено"
    )

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [
        r for r in load_data()
        if normalize(r.get(COL_LOCKER)) in ("ні", "no", "0", "")
    ]
    await update.message.reply_text(
        "\n".join(f"• {r[COL_NAME]}" for r in rows) or "❌ Нічого не знайдено"
    )

# ================== MAIN ==================
def main():
    threading.Thread(target=run_flask).start()

    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("find", find_all))
    app_tg.add_handler(CommandHandler("knife", knife))
    app_tg.add_handler(CommandHandler("no_knife", no_knife))
    app_tg.add_handler(CommandHandler("with_locker", with_locker))
    app_tg.add_handler(CommandHandler("no_locker", no_locker))

    app_tg.run_polling()

if __name__ == "__main__":
    main()
