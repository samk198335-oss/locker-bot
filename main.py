import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ---------- FAKE HTTP SERVER (для Render) ----------
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

# ---------- TELEGRAM COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\nAvailable commands:\n"
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
    await update.message.reply_text("Find command")

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Knife")

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("No knife")

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("With locker")

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("No locker")

# ---------- MAIN ----------
def main():
    # HTTP server в окремому потоці
    threading.Thread(target=run_http_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    app.run_polling()

if __name__ == "__main__":
    main()
