import os
import csv
import threading
import requests
from io import StringIO

from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

PORT = int(os.environ.get("PORT", 10000))
# ==========================================

# ---------- FLASK (Render Free needs open port) ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive 🚀"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ---------- HELPERS ----------
def normalize(v: str) -> str:
    return v.strip().lower()

def is_yes(v: str) -> bool:
    return normalize(v) in ["yes", "true", "1", "так", "+"]

def is_no(v: str) -> bool:
    return normalize(v) in ["no", "false", "0", "ні", "-"]

# ---------- DATA ----------
def load_data():
    try:
        r = requests.get(CSV_URL, timeout=10)
        r.raise_for_status()
        csv_file = StringIO(r.text)
        reader = csv.DictReader(csv_file)
        return list(reader)
    except Exception as e:
        print("❌ CSV load error:", e)
        return []

def filter_data(data, knife=None, locker=None):
    results = []

    for row in data:
        if knife is not None:
            if knife == "yes" and not is_yes(row.get("knife", "")):
                continue
            if knife == "no" and not is_no(row.get("knife", "")):
                continue

        if locker is not None:
            if locker == "yes" and not is_yes(row.get("locker", "")):
                continue
            if locker == "no" and not is_no(row.get("locker", "")):
                continue

        results.append(row)

    return results

def format_results(rows):
    if not rows:
        return "❌ Нічого не знайдено"

    messages = []
    for r in rows:
        messages.append(
            f"📍 {r.get('name','')}\n"
            f"ℹ️ {r.get('info','')}"
        )

    return "\n\n".join(messages[:20])  # Telegram limit safe

# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю!\n\n"
        "Доступні команди:\n"
        "/find <текст> — пошук\n"
        "/knife — з ножем\n"
        "/no_knife — без ножа\n"
        "/with_locker — з шафкою\n"
        "/no_locker — без шафки"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Вкажи текст для пошуку")
        return

    query = normalize(" ".join(context.args))
    data = load_data()

    results = [
        r for r in data
        if query in normalize(r.get("name", "")) or
           query in normalize(r.get("info", ""))
    ]

    await update.message.reply_text(format_results(results))

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, knife="yes"))
    )

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, knife="no"))
    )

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, locker="yes"))
    )

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(
        format_results(filter_data(data, locker="no"))
    )

# ---------- MAIN ----------
def main():
    threading.Thread(target=run_flask).start()

    app_tg = ApplicationBuilder().token(BOT_TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("find", find))
    app_tg.add_handler(CommandHandler("knife", knife))
    app_tg.add_handler(CommandHandler("no_knife", no_knife))
    app_tg.add_handler(CommandHandler("with_locker", with_locker))
    app_tg.add_handler(CommandHandler("no_locker", no_locker))

    app_tg.run_polling()

if __name__ == "__main__":
    main()
