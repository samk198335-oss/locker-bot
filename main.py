import os
import csv
import logging
import requests

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# той самий Google Sheets CSV
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"

# ================== LOGGING ==================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================== DATA ==================

def load_data():
    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()

    decoded = response.content.decode("utf-8")
    reader = csv.DictReader(decoded.splitlines())
    return list(reader)

# ================== COMMANDS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello 👋\n\n"
        "Available commands:\n"
        "/find\n"
        "/knife\n"
        "/no_knife\n"
        "/with_locker\n"
        "/no_locker"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(f"Rows in table: {len(data)}")

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [row for row in data if row.get("knife", "").lower() == "yes"]
    await update.message.reply_text(f"With knife: {len(result)}")

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [row for row in data if row.get("knife", "").lower() == "no"]
    await update.message.reply_text(f"No knife: {len(result)}")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [row for row in data if row.get("locker", "").lower() == "yes"]
    await update.message.reply_text(f"With locker: {len(result)}")

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    result = [row for row in data if row.get("locker", "").lower() == "no"]
    await update.message.reply_text(f"No locker: {len(result)}")

# ================== MAIN ==================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
