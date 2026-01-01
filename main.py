import os
import threading
import csv
import io
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔗 GOOGLE SHEET (CSV)
SHEET_URL = "PASTE_YOUR_GOOGLE_SHEET_CSV_LINK_HERE"

# ---------- FAKE HTTP SERVER (Render Free) ----------
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

# ---------- HELPERS ----------
def normalize(value: str) -> str:
    return value.strip().lower()

def is_yes(value: str) -> bool:
    return normalize(value) in ["yes", "true", "1", "так", "+"]

def is_no(value: str) -> bool:
    return normalize(value) in ["no", "false", "0", "ні", "-"]

# ---------- DATA ----------
def load_data():
    try:
        r = requests.get(SHEET_URL, timeout=10)
        r.raise_for_status()
        csv_file = io.StringIO(r.text)
        reader = csv.DictReader(csv_file)
        return list(reader)
    except Exception as e:
        print("❌ Error loading sheet:", e)
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

    return "\n\n".join(messages)

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
    data = load_data()
    await update.message.reply_text(format_results(data))

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(format_results(filter_data(data, knife="yes")))

async def no_knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(format_results(filter_data(data, knife="no")))

async def with_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(format_results(filter_data(data, locker="yes")))

async def no_locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(format_results(filter_data(data, locker="no")))

# ---------- MAIN ----------
def main():
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
