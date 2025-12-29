import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ================== НАЛАШТУВАННЯ ==================

TOKEN = os.getenv("BOT_TOKEN")  # токен з Render Environment Variables

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# ================== HANDLERS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Вітаю!\n\n"
        "/find – знайти всі\n"
        "/knife – з ножем\n"
        "/no_knife – без ножа\n"
        "/with_locker – з шафкою\n"
        "/no_locker – без шафки\n\n"
        "/myid – показати мій Telegram ID"
    )
    await update.message.reply_text(text)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 Твій Telegram ID:\n\n{user.id}"
    )


# ================== MAIN ==================

def main():
    if not TOKEN:
        raise RuntimeError("❌ BOT_TOKEN не заданий у Environment Variables")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myid", myid))

    logger.info("🤖 Bot started (polling)...")
    application.run_polling()


if __name__ == "__main__":
    main()
