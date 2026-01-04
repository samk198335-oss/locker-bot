import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ===============================
# KEEP ALIVE
# ===============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health():
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 10000))), HealthHandler).serve_forever()

# ===============================
# CSV
# ===============================
def load_data():
    r = requests.get(CSV_URL)
    r.encoding = "utf-8-sig"   # 🔴 ВАЖЛИВО
    reader = csv.DictReader(StringIO(r.text))
    return list(reader)

def n(v):
    return (v or "").strip().lower()

# ===============================
# LOGIC
# ===============================
def has_knife(r):
    return n(r.get("knife")) in {"1", "2"}

def no_knife(r):
    return n(r.get("knife")) == "0"

def has_locker(r):
    v = n(r.get("locker"))
    return v not in {"", "-", "ні", "no"}

def no_locker(r):
    v = n(r.get("locker"))
    return v in {"", "-", "ні", "no"}

# ===============================
# COMMANDS
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/stats\n"
        "/knife_list\n"
        "/no_knife_list\n"
        "/locker_list\n"
        "/no_locker_list"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = load_data()
    await update.message.reply_text(
        f"Всього: {len(d)}\n"
        f"З ножем: {sum(has_knife(x) for x in d)}\n"
        f"Без ножа: {sum(no_knife(x) for x in d)}\n"
        f"З шафкою: {sum(has_locker(x) for x in d)}\n"
        f"Без шафки: {sum(no_locker(x) for x in d)}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = load_data()
    rows = [f"• {x['Address']}" for x in d if has_knife(x)]
    await update.message.reply_text("\n".join(rows) or "Немає даних")

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = load_data()
    rows = [f"• {x['Address']}" for x in d if no_knife(x)]
    await update.message.reply_text("\n".join(rows) or "Немає даних")

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = load_data()
    rows = [f"• {x['Address']} — {x['locker']}" for x in d if has_locker(x)]
    await update.message.reply_text("\n".join(rows) or "Немає даних")

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = load_data()
    rows = [f"• {x['Address']}" for x in d if no_locker(x)]
    await update.message.reply_text("\n".join(rows) or "Немає даних")

# ===============================
# MAIN
# ===============================
def main():
    threading.Thread(target=run_health, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()

if __name__ == "__main__":
    main()
