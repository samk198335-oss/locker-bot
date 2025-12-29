import os
import csv
import io
import logging
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"
)

# ================== LOGGING ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================== DATA ==================
def load_sheet():
    response = requests.get(SHEET_CSV_URL, timeout=20)
    response.raise_for_status()
    csv_file = io.StringIO(response.text)
    reader = csv.DictReader(csv_file)
    return list(reader)

def has_knife(value: str) -> bool:
    return str(value).strip() in ("1", "2")

def has_locker(value: str) -> bool:
    value = str(value).strip()
    return value.isdigit()

def filter_rows(rows, knife=None, locker=None):
    result = []

    for row in rows:
        knife_val = row.get("knife", "")
        locker_val = row.get("locker", "")

        if knife is not None and has_knife(knife_val) != knife:
            continue

        if locker is not None and has_locker(locker_val) != locker:
            continue

        result.append(row)

    return result

def format_rows(rows):
    if not rows:
        return "❌ Nothing found"

    lines = []
    for r in rows[:20]:
        lines.append(
            f"📍 {r.get('Adress', '—')}\n"
            f"👤 {r.get('surname', '—')}\n"
            f"🔪 Knife: {r.get('knife', '—')}\n"
            f"🔐 Locker: {r.get('locker', '—')}"
        )

    if len(rows) > 20:
        lines.append(f"\n…and {len(rows) - 20} more")

    return "\n\n".join(lines)

# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\n"
        "Available commands:\n"
        "/find\n"
        "/knife\n"
        "/no_knife\n"
        "/with_locker\n"
        "/no_locker\n"
        "/myid"
    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Your ID: {update.effective_user.id}"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    await update.message.reply_text(format_rows(rows))

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    await update.message.reply_text(
        format_rows(filter_rows(rows, knife=True))
    )

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    await update.message.reply_text(
        format_rows(filter_rows(rows, knife=False))
    )

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    await update.message.reply_text(
        format_rows(filter_rows(rows, locker=True))
    )

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    await update.message.reply_text(
        format_rows(filter_rows(rows, locker=False))
    )

# ================== MAIN ==================
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))
    app.add_handler(CommandHandler("myid", myid))

    logger.info("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
