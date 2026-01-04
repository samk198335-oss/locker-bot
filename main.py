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
# CONFIG
# ===============================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI"
    "/export?format=csv"
)

# ===============================
# RENDER HEALTHCHECK
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
# CSV LOADING (UTF-8 SAFE)
# ===============================

def safe_text(value: str) -> str:
    """
    Захист від битого кодування (Ð¡Ñ‚ÐµÑ„Ð°Ð½Ð° → Стефана)
    """
    if not isinstance(value, str):
        return ""
    try:
        return value.encode("latin1").decode("utf-8")
    except Exception:
        return value

def load_csv():
    response = requests.get(CSV_URL, timeout=15)
    response.raise_for_status()

    text = response.content.decode("utf-8")
    reader = csv.DictReader(StringIO(text))

    rows = []
    for row in reader:
        clean_row = {
            "Address": safe_text(row.get("Address", "")).strip(),
            "surname": safe_text(row.get("surname", "")).strip(),
            "knife": safe_text(row.get("knife", "")).strip(),
            "locker": safe_text(row.get("locker", "")).strip(),
        }
        rows.append(clean_row)

    return rows

# ===============================
# NORMALIZATION
# ===============================

def has_knife(value: str) -> bool:
    return value in {"1", "2"}

def no_knife(value: str) -> bool:
    return value == "0"

def has_locker(value: str) -> bool:
    if not value:
        return False
    v = value.lower()
    if v in {"-", "0"}:
        return False
    return True

# ===============================
# COMMANDS
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n"
        "Команди:\n"
        "/stats – статистика\n"
        "/knife_list – прізвища з ножами\n"
        "/no_knife_list – прізвища без ножів"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    total = len(rows)
    knife_yes = sum(1 for r in rows if has_knife(r["knife"]))
    knife_no = sum(1 for r in rows if no_knife(r["knife"]))
    locker_yes = sum(1 for r in rows if has_locker(r["locker"]))
    locker_no = total - locker_yes

    text = (
        "📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"❌ Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

    await update.message.reply_text(text)

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    names = [
        r["surname"]
        for r in rows
        if has_knife(r["knife"]) and r["surname"]
    ]

    if not names:
        await update.message.reply_text("🔪 Прізвища з ножами:\nНемає даних")
        return

    await update.message.reply_text(
        "🔪 Прізвища з ножами:\n" + "\n".join(names)
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    names = [
        r["surname"]
        for r in rows
        if no_knife(r["knife"]) and r["surname"]
    ]

    if not names:
        await update.message.reply_text("❌ Без ножів:\nНемає даних")
        return

    await update.message.reply_text(
        "❌ Без ножів:\n" + "\n".join(names)
    )

# ===============================
# MAIN
# ===============================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))

    app.run_polling()

if __name__ == "__main__":
    main()
