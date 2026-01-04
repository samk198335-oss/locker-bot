import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# =========================
# Render keep-alive
# =========================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_healthcheck():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_healthcheck, daemon=True).start()

# =========================
# CSV loader
# =========================
def load_rows():
    r = requests.get(CSV_URL, timeout=15)
    r.raise_for_status()
    data = StringIO(r.text)
    reader = csv.reader(data)
    rows = list(reader)
    return rows[1:]  # skip header

# =========================
# Helpers
# =========================
def is_locker_present(value: str) -> bool:
    if not value:
        return False
    value = value.strip()
    return value != "-" and value != ""

# =========================
# Commands
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Alexpuls_bot працює\n\n"
        "/stats — загальна статистика\n"
        "/knife_list — прізвища з ножами\n"
        "/no_knife_list — без ножів\n"
        "/locker_list — прізвища з шафками\n"
        "/no_locker_list — без шафок"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()

    total = len(rows)
    knife_yes = 0
    knife_no = 0
    locker_yes = 0
    locker_no = 0

    for r in rows:
        surname = r[1].strip()
        knife_raw = r[2].strip()
        locker_raw = r[3].strip()

        knife_count = int(knife_raw) if knife_raw.isdigit() else 0

        if knife_count > 0:
            knife_yes += 1
        else:
            knife_no += 1

        if is_locker_present(locker_raw):
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"❌ Без ножа: {knife_no}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = []

    for r in rows:
        surname = r[1].strip()
        knife_raw = r[2].strip()
        count = int(knife_raw) if knife_raw.isdigit() else 0
        if count > 0:
            result.append(f"{surname} — {count}")

    if not result:
        await update.message.reply_text("🔪 Прізвища з ножами:\nНемає даних")
        return

    await update.message.reply_text("🔪 Прізвища з ножами:\n" + "\n".join(result))

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = []

    for r in rows:
        surname = r[1].strip()
        knife_raw = r[2].strip()
        count = int(knife_raw) if knife_raw.isdigit() else 0
        if count == 0:
            result.append(surname)

    await update.message.reply_text(
        "❌ Без ножів:\n" + ("\n".join(result) if result else "Немає даних")
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = []

    for r in rows:
        surname = r[1].strip()
        locker_raw = r[3].strip()
        if is_locker_present(locker_raw):
            result.append(surname)

    await update.message.reply_text(
        "🗄️ Прізвища з шафками:\n" + ("\n".join(result) if result else "Немає даних")
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_rows()
    result = []

    for r in rows:
        surname = r[1].strip()
        locker_raw = r[3].strip()
        if not is_locker_present(locker_raw):
            result.append(surname)

    await update.message.reply_text(
        "❌ Без шафок:\n" + ("\n".join(result) if result else "Немає даних")
    )

# =========================
# Main
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()

if __name__ == "__main__":
    main()
