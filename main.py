import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# CONFIG
# ==================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ==================================================
# RENDER HEALTH SERVER
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_http_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

# ==================================================
# CSV
# ==================================================

def load_csv():
    r = requests.get(CSV_URL, timeout=10)
    r.raise_for_status()
    return list(csv.DictReader(StringIO(r.text)))

def has_value(v):
    return v is not None and str(v).strip() != ""

# ==================================================
# COMMANDS
# ==================================================

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

# ---------------- KNIFE ----------------

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    result = []

    for r in data:
        if has_value(r.get("knife")):
            num = r.get("number", "").strip()
            name = r.get("surname", "").strip()
            if num:
                result.append(f"{num} — {name}")

    await update.message.reply_text(
        f"🔪 НІЖ\nТак: {len(result)}\n\n" + "\n".join(result)
    )

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    count = sum(1 for r in data if not has_value(r.get("knife")))
    await update.message.reply_text(f"🚫 Без ножа: {count}")

# ---------------- LOCKER ----------------

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    result = []

    for r in data:
        if has_value(r.get("with_locker")):
            num = r.get("number", "").strip()
            name = r.get("surname", "").strip()
            if num:
                result.append(f"{num} — {name}")

    await update.message.reply_text(
        f"🗄 ШАФКА\nТак: {len(result)}\n\n" + "\n".join(result)
    )

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    count = sum(1 for r in data if not has_value(r.get("with_locker")))
    await update.message.reply_text(f"🚫 Без шафки: {count}")

# ==================================================
# MAIN
# ==================================================

def main():
    threading.Thread(target=start_http_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("no_knife", no_knife))
    app.add_handler(CommandHandler("with_locker", with_locker))
    app.add_handler(CommandHandler("no_locker", no_locker))

    print("BOT STARTED")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
