import os
import csv
import requests
from io import StringIO
from collections import defaultdict

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ==============================
# CONFIG
# ==============================
BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# можливі "ТАК"
YES_VALUES = {"так", "yes", "+", "1", "true", "y"}

# ==============================
# CSV LOAD
# ==============================
def load_csv():
    resp = requests.get(CSV_URL, timeout=15)
    resp.raise_for_status()

    data = []
    reader = csv.DictReader(StringIO(resp.text))

    for row in reader:
        clean = {k.strip().lower(): (v or "").strip().lower() for k, v in row.items()}
        data.append(clean)

    return data

# ==============================
# HELPERS
# ==============================
def is_yes(value: str) -> bool:
    return value in YES_VALUES

def count_by_field(data, field):
    yes = []
    no = []

    for row in data:
        name = row.get("прізвище", "").title()
        value = row.get(field, "")

        if is_yes(value):
            yes.append(name)
        else:
            no.append(name)

    return yes, no

# ==============================
# COMMANDS
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/find\n"
        "/knife\n"
        "/no_knife\n"
        "/with_locker\n"
        "/no_locker"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    await update.message.reply_text(f"📋 Всього записів: {len(data)}")

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    yes, _ = count_by_field(data, "ніж")

    text = "🔪 НІЖ\n"
    text += f"Так: {len(yes)}"
    if yes:
        text += "\n" + ", ".join(yes)

    await update.message.reply_text(text)

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    _, no = count_by_field(data, "ніж")
    await update.message.reply_text(f"🚫 Без ножа: {len(no)}")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    yes, _ = count_by_field(data, "шафка")

    text = "🗄 ШАФКА\n"
    text += f"Так: {len(yes)}"
    if yes:
        text += "\n" + ", ".join(yes)

    await update.message.reply_text(text)

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    _, no = count_by_field(data, "шафка")
    await update.message.reply_text(f"🚫 Без шафки: {len(no)}")

# ==============================
# MAIN
# ==============================
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

if __name__ == "__main__":
    main()
