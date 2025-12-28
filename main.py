import os
import threading
from flask import Flask
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update

BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Telegram bot ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот працює ✅")

def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

# --- Flask app (для Render Free) ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# --- Start both ---
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    run_flask()
