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

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"
)

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------- HELPERS ----------------
def load_sheet():
    response = requests.get(SHEET_CSV_URL, timeout=20)
    response.raise_for_status()
    csv_file = io.StringIO(response.text)
    reader = csv.DictReader(csv_file)
    return list(reader)

def filter_rows(rows, knife=None, locker=None):
    result = []
    for row in rows:
        if knife is not None and row.get("knife") != knife:
            continue
        if locker is not None and row.get("locker") != locker:
            continue
        result.append(row)
    return result

def format_rows(rows):
    if not rows:
        return "❌ Nothing found"

    lines = []
    for r in rows[:20]:
        line = (
            f"🔹 {r.get('name', '—')}\n"
            f"   Knife: {r.get('knife', '—')}\n"
            f"   Locker: {r.get('locker', '—')}"
        )
        lines.append(line)

    if len(rows) > 20:
        lines.append(f"\n…and {len(rows) - 20} more")

    return "\n\n".join(lines)

# ---------------- COMMANDS ----------------
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
    await update.message.reply_text(f"🆔 Your ID: {update.effective_user.id}")

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    await update.message.reply_text(format_rows(rows))

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    filtered = filter_rows(rows, knife="yes")
    await update.message.reply_text(format_rows(filtered))

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    filtered = filter_rows(rows, knife="no")
    await update.message.reply_text(format_rows(filtered))

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    filtered = filter_rows(rows, locker="yes")
    await update.message.reply_text(format_rows(filtered))

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_sheet()
    filtered = filter_rows(rows, locker="no")
    await update.message.reply_text(format_rows(filtered))

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("find", find))
    application.add_handler(CommandHandler("knife", knife))
    application.add_handler(CommandHandler("no_knife", no_knife))
    application.add_handler(CommandHandler("with_locker", with_locker))
    application.add_handler(CommandHandler("no_locker", no_locker))
    application.add_handler(CommandHandler("myid", myid))

    logger.info("Bot started")
    application.run_polling()

if __name__ == "__main__":
    main()
