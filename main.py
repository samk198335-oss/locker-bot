import os
import csv
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# 🌐 KEEP ALIVE (Render Free)
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def keep_alive():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

threading.Thread(target=keep_alive, daemon=True).start()

# ==================================================
# 🔑 CONFIG
# ==================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

YES_VALUES = {"yes", "y", "1", "+", "так", "є"}

# ==================================================
# 📄 CSV
# ==================================================

def load_csv():
    r = requests.get(CSV_URL, timeout=10)
    r.raise_for_status()
    return list(csv.DictReader(StringIO(r.content.decode("utf-8"))))

def is_yes(v: str) -> bool:
    return v.strip().lower() in YES_VALUES if v else False

# ==================================================
# 🤖 COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/find – всього записів\n"
        "/knife – ніж\n"
        "/locker – шафка"
    )

async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()
    await update.message.reply_text(f"📋 Всього записів: {len(data)}")

# ---------------- KNIFE ----------------

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()

    yes = []

    for r in data:
        number = r.get("number", "").strip()
        surname = r.get("surname", "").strip()

        if not number:
            continue  # немає номера — не показуємо

        if is_yes(r.get("knife", "")):
            yes.append(f"{number} — {surname}")

    text = (
        f"🔪 НІЖ\n"
        f"Так: {len(yes)}\n\n"
        + "\n".join(yes)
    )

    await update.message.reply_text(text)

# ---------------- LOCKER ----------------

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_csv()

    yes = []

    for r in data:
        number = r.get("number", "").strip()
        surname = r.get("surname", "").strip()

        if not number:
            continue

        if is_yes(r.get("locker", "")):
            yes.append(f"{number} — {surname}")

    text = (
        f"🗄 ШАФКА\n"
        f"Так: {len(yes)}\n\n"
        + "\n".join(yes)
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
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
