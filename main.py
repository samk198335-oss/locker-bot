import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# 🔧 RENDER FREE STABILIZATION
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_http_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# ==================================================
# 🔑 CONFIG
# ==================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ==================================================
# 📄 CSV
# ==================================================

def load_csv():
    try:
        r = requests.get(CSV_URL, timeout=10)
        r.raise_for_status()
        return list(csv.DictReader(StringIO(r.content.decode("utf-8"))))
    except Exception as e:
        print("CSV ERROR:", e)
        return []

# ==================================================
# 🧠 HELPERS
# ==================================================

YES_VALUES = {"yes", "y", "1", "+", "так", "є"}

def is_yes(value: str) -> bool:
    return value.strip().lower() in YES_VALUES

def is_no_or_empty(value: str) -> bool:
    return not value.strip() or not is_yes(value)

# ==================================================
# 🤖 COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команди:\n"
        "/find\n"
        "/knife\n"
        "/locker"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    await update.message.reply_text(f"📋 Всього записів: {len(data)}")

# ---------------- KNIFE ----------------

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()

    yes = []
    no = []

    for r in data:
        name = f"{r.get('number','—')} — {r.get('surname','')}"
        if is_yes(r.get("knife", "")):
            yes.append(name)
        else:
            no.append(name)

    text = (
        f"🔪 НІЖ\n"
        f"Так: {len(yes)}\n"
        + "\n".join(yes) +
        f"\n\n🚫 Без ножа: {len(no)}"
    )

    await update.message.reply_text(text)

# ---------------- LOCKER ----------------

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()

    yes = []
    no = []

    for r in data:
        name = f"{r.get('number','—')} — {r.get('surname','')}"
        if is_yes(r.get("locker", "")):
            yes.append(name)
        else:
            no.append(name)

    text = (
        f"🗄 ШАФКА\n"
        f"Так: {len(yes)}\n"
        + "\n".join(yes) +
        f"\n\n🚫 Без шафки: {len(no)}"
    )

    await update.message.reply_text(text)

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("find", find))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("locker", locker))

    print("BOT STARTED")
    app.run_polling()

if __name__ == "__main__":
    main()
