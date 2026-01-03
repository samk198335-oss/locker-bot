import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ===============================
# 🔧 CONFIG
# ===============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ===============================
# 🩺 RENDER KEEP-ALIVE
# ===============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ===============================
# 📄 CSV HELPERS
# ===============================

YES_VALUES = {"yes", "y", "+", "так", "1"}
NO_VALUES = {"no", "n", "-", "ні", "0"}

def normalize(value: str | None):
    if not value:
        return None
    v = value.strip().lower()
    if v in YES_VALUES:
        return True
    if v in NO_VALUES:
        return False
    return None

def load_rows():
    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()

    text = response.content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    return list(reader)

# ===============================
# 🤖 COMMANDS
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/stats — загальна статистика\n"
        "/knife_list — прізвища з ножами\n"
        "/no_knife_list — прізвища без ножа\n"
        "/locker_list — прізвища з шафками\n"
        "/no_locker_list — прізвища без шафки"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()

    knife_yes = knife_no = locker_yes = locker_no = 0

    for r in rows:
        knife = normalize(r.get("Ніж"))
        locker = normalize(r.get("Шафка"))

        if knife is True:
            knife_yes += 1
        elif knife is False:
            knife_no += 1

        if locker is True:
            locker_yes += 1
        elif locker is False:
            locker_no += 1

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🔐 З шафкою: {locker_yes}\n"
        f"🚫 Без шафки: {locker_no}"
    )

async def list_by_field(update, title, field, expected):
    rows = load_rows()
    names = []

    for r in rows:
        value = normalize(r.get(field))
        if value is expected:
            name = r.get("Прізвище")
            if name:
                names.append(name.strip())

    if not names:
        await update.message.reply_text(f"{title}\nНемає даних.")
        return

    await update.message.reply_text(
        f"{title}\n" + "\n".join(f"• {n}" for n in names)
    )

async def knife_list(update, context):
    await list_by_field(update, "🔪 Прізвища з ножами:", "Ніж", True)

async def no_knife_list(update, context):
    await list_by_field(update, "🚫 Прізвища без ножа:", "Ніж", False)

async def locker_list(update, context):
    await list_by_field(update, "🔐 Прізвища з шафками:", "Шафка", True)

async def no_locker_list(update, context):
    await list_by_field(update, "🚫 Прізвища без шафки:", "Шафка", False)

# ===============================
# 🚀 MAIN
# ===============================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

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
