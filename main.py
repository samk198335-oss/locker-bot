import os
import asyncio
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔹 Google Sheets CSV
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================= HELPERS =================
def load_data():
    response = requests.get(CSV_URL)
    response.raise_for_status()
    lines = response.text.splitlines()
    headers = lines[0].split(",")
    data = [dict(zip(headers, line.split(","))) for line in lines[1:]]
    return data

def filter_data(data, **conditions):
    result = []
    for row in data:
        ok = True
        for key, value in conditions.items():
            if row.get(key, "").strip().lower() != value.lower():
                ok = False
                break
        if ok:
            result.append(row)
    return result

def format_result(rows):
    if not rows:
        return "❌ Нічого не знайдено"
    text = ""
    for r in rows:
        text += f"🔹 Локер: {r.get('locker','')}\n"
        text += f"🔹 Ніж: {r.get('knife','')}\n"
        text += f"🔹 Шафка: {r.get('cabinet','')}\n\n"
    return text

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Команди:\n"
        "/знайти\n"
        "/ніж\n"
        "/безножа\n"
        "/зшафкою\n"
        "/безшафки"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(format_result(data))

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = filter_data(load_data(), knife="yes")
    await update.message.reply_text(format_result(data))

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = filter_data(load_data(), knife="no")
    await update.message.reply_text(format_result(data))

async def cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = filter_data(load_data(), cabinet="yes")
    await update.message.reply_text(format_result(data))

async def no_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = filter_data(load_data(), cabinet="no")
    await update.message.reply_text(format_result(data))

# ================= MAIN =================
async def run_bot():
    app_tg = Application.builder().token(BOT_TOKEN).build()

    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CommandHandler("знайти", find))
    app_tg.add_handler(CommandHandler("ніж", knife))
    app_tg.add_handler(CommandHandler("безножа", no_knife))
    app_tg.add_handler(CommandHandler("зшафкою", cabinet))
    app_tg.add_handler(CommandHandler("безшафки", no_cabinet))

    await app_tg.run_polling()

def main():
    print("Starting Flask...")
    threading.Thread(target=run_flask).start()

    print("Starting Telegram bot polling...")
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
