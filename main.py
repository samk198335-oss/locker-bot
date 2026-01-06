import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

CSV_CACHE = []
CSV_LOADED = False

# =========================
# CSV LOADER
# =========================

def load_csv():
    global CSV_CACHE, CSV_LOADED
    try:
        r = requests.get(CSV_URL, timeout=15)
        r.raise_for_status()
        reader = csv.DictReader(StringIO(r.text))
        CSV_CACHE = list(reader)
        CSV_LOADED = True
        print(f"[CSV] Loaded {len(CSV_CACHE)} rows")
    except Exception as e:
        print("[CSV ERROR]", e)
        CSV_CACHE = []
        CSV_LOADED = False


def get_data():
    if not CSV_LOADED:
        load_csv()
    return CSV_CACHE

# =========================
# HELPERS
# =========================

def has_knife(value: str) -> bool:
    if not value:
        return False
    return value.strip() in ["1", "yes", "Yes", "YES", "+", "так", "Так"]

def has_locker(value: str) -> bool:
    if not value:
        return False
    v = value.strip().lower()
    return v not in ["0", "-", "ні", "нет", "no", ""]

# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Вітаю!\n\n"
        "Команди:\n"
        "/stats — статистика\n"
        "/locker_list — з шафкою\n"
        "/no_locker_list — без шафки\n"
        "/knife_list — з ножем\n"
        "/no_knife_list — без ножа\n"
        "/find <прізвище> — пошук"
    )

# -------------------------

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_data()

    total = len(data)
    knife_yes = 0
    knife_no = 0
    locker_yes = 0
    locker_no = 0

    for row in data:
        if has_knife(row.get("knife", "")):
            knife_yes += 1
        else:
            knife_no += 1

        if has_locker(row.get("locker", "")):
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"👥 Всього: {total}\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

# -------------------------

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_data()
    lines = []

    for row in data:
        if has_knife(row.get("knife", "")):
            lines.append(f"— {row.get('surname', '').strip()}")

    await update.message.reply_text("🔪 З ножем:\n" + ("\n".join(lines) if lines else "Немає"))

# -------------------------

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_data()
    lines = []

    for row in data:
        if not has_knife(row.get("knife", "")):
            lines.append(f"— {row.get('surname', '').strip()}")

    await update.message.reply_text("🚫 Без ножа:\n" + ("\n".join(lines) if lines else "Немає"))

# -------------------------

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_data()
    lines = []

    for row in data:
        locker = row.get("locker", "")
        if has_locker(locker):
            lines.append(f"— {row.get('surname', '').strip()} ({locker.strip()})")

    await update.message.reply_text("🗄️ З шафкою:\n" + ("\n".join(lines) if lines else "Немає"))

# -------------------------

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_data()
    lines = []

    for row in data:
        if not has_locker(row.get("locker", "")):
            lines.append(f"— {row.get('surname', '').strip()}")

    await update.message.reply_text("❌ Без шафки:\n" + ("\n".join(lines) if lines else "Немає"))

# -------------------------

async def find_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Використання:\n/find <прізвище>")
        return

    query = " ".join(context.args).lower()
    data = get_data()

    results = []
    for row in data:
        surname = row.get("surname", "")
        if query in surname.lower():
            knife = "🔪" if has_knife(row.get("knife", "")) else "🚫"
            locker = row.get("locker", "-")
            results.append(f"— {surname} | {knife} | шафка: {locker}")

    await update.message.reply_text("\n".join(results) if results else "❌ Нічого не знайдено")

# =========================
# HEALTHCHECK (Render)
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_healthcheck():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# =========================
# MAIN
# =========================

def main():
    threading.Thread(target=run_healthcheck, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("find", find_person))

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
