import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===============================
# CONFIG
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ===============================
# RENDER HEALTHCHECK
# ===============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_healthcheck():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_healthcheck, daemon=True).start()

# ===============================
# CSV CACHE
# ===============================
CACHE = {
    "data": [],
}

def load_csv():
    try:
        r = requests.get(CSV_URL, timeout=15)
        r.raise_for_status()
        content = r.content.decode("utf-8")
        reader = csv.DictReader(StringIO(content))
        CACHE["data"] = list(reader)
    except Exception as e:
        print("CSV LOAD ERROR:", e)

# ===============================
# HELPERS
# ===============================
def knife_count(value):
    try:
        v = int(str(value).strip())
        return v if v > 0 else 0
    except:
        return 0

def has_locker(value):
    v = str(value).strip().lower()
    if v in ["", "-", "0", "ні", "нет"]:
        return False
    return True

# ===============================
# COMMANDS
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! 👋\n\n"
        "Доступні команди:\n"
        "/stats — загальна статистика\n"
        "/knife — кількість ножів\n"
        "/knife_list — прізвища з ножами\n"
        "/locker — кількість шафок"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_csv()
    rows = CACHE["data"]

    total = len(rows)
    with_knife = 0
    without_knife = 0
    with_locker = 0
    without_locker = 0

    for r in rows:
        if knife_count(r.get("knife")) > 0:
            with_knife += 1
        else:
            without_knife += 1

        if has_locker(r.get("locker")):
            with_locker += 1
        else:
            without_locker += 1

    await update.message.reply_text(
        "📊 Статистика:\n"
        f"Всього записів: {total}\n\n"
        f"🔪 З ножем: {with_knife}\n"
        f"🔪 Без ножа: {without_knife}\n\n"
        f"🗄 З шафкою: {with_locker}\n"
        f"🗄 Без шафки: {without_locker}"
    )

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_csv()
    rows = CACHE["data"]

    with_knife = sum(1 for r in rows if knife_count(r.get("knife")) > 0)
    without_knife = len(rows) - with_knife

    await update.message.reply_text(
        "🔪 Ніж:\n"
        f"З ножем: {with_knife}\n"
        f"Без ножа: {without_knife}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_csv()
    rows = CACHE["data"]

    result = []
    for r in rows:
        k = knife_count(r.get("knife"))
        if k > 0:
            surname = r.get("surname", "").strip()
            result.append(f"{surname} — {k}")

    if not result:
        await update.message.reply_text("🔪 З ножем нікого не знайдено")
        return

    text = "🔪 Прізвища з ножами:\n" + "\n".join(result)
    await update.message.reply_text(text)

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_csv()
    rows = CACHE["data"]

    with_locker = sum(1 for r in rows if has_locker(r.get("locker")))
    without_locker = len(rows) - with_locker

    await update.message.reply_text(
        "🗄 Шафка:\n"
        f"З шафкою: {with_locker}\n"
        f"Без шафки: {without_locker}"
    )

# ===============================
# MAIN
# ===============================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("locker", locker))

    app.run_polling()

if __name__ == "__main__":
    main()
