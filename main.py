import os
import threading
import requests
import csv
from io import StringIO
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"

COL_NAME = "Назва"
COL_KNIFE = "Ніж"
COL_LOCKER = "Шафка"

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================= CSV =================
def load_data():
    r = requests.get(CSV_URL, timeout=15)
    r.raise_for_status()
    return list(csv.DictReader(StringIO(r.text)))

def norm(v):
    return str(v).strip().lower()

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю!\n\n"
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
    await update.message.reply_text("\n".join(f"• {r[COL_NAME]}" for r in rows))

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [r for r in load_data() if norm(r.get(COL_KNIFE)) in ("так", "yes", "1")]
    await update.message.reply_text("\n".join(f"• {r[COL_NAME]}" for r in rows) or "❌ Нічого не знайдено")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [r for r in load_data() if norm(r.get(COL_LOCKER)) in ("так", "yes", "1")]
    await update.message.reply_text("\n".join(f"• {r[COL_NAME]}" for r in rows) or "❌ Нічого не знайдено")

# ================= MAIN =================
def main():
    print("Starting Flask...")
    threading.Thread(target=run_flask, daemon=True).start()

    print("Starting Telegram bot polling...")
    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()

    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("find", find_all))
    tg_app.add_handler(CommandHandler("knife", knife))
    tg_app.add_handler(CommandHandler("with_locker", with_locker))

    tg_app.run_polling()

if __name__ == "__main__":
    main()
