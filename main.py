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

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ===============================
# RENDER KEEP-ALIVE
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
# CSV LOADER
# ===============================

def load_csv():
    response = requests.get(CSV_URL, timeout=15)
    response.raise_for_status()
    response.encoding = "utf-8"

    reader = csv.DictReader(StringIO(response.text))
    return list(reader)

def normalize(value: str) -> str:
    if value is None:
        return ""
    return value.strip().lower()

def is_yes(value: str) -> bool:
    v = normalize(value)
    return v in {"1", "yes", "y", "так", "+", "є", "есть"}

def is_no(value: str) -> bool:
    v = normalize(value)
    return v in {"0", "no", "n", "ні", "-", "нема", "нет"}

# ===============================
# COMMANDS
# ===============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Alexpuls_bot працює\n\n"
        "/stats — загальна статистика\n"
        "/knife_list — прізвища з ножами\n"
        "/no_knife_list — прізвища без ножа\n"
        "/locker_list — прізвища з шафками\n"
        "/no_locker_list — прізвища без шафки"
    )

# -------- STATS --------

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    knife_yes = knife_no = 0
    locker_yes = locker_no = 0

    for r in rows:
        if is_yes(r.get("knife")):
            knife_yes += 1
        elif is_no(r.get("knife")):
            knife_no += 1

        if is_yes(r.get("locker")) or r.get("locker", "").isdigit():
            locker_yes += 1
        elif is_no(r.get("locker")):
            locker_no += 1

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🔐 З шафкою: {locker_yes}\n"
        f"🚫 Без шафки: {locker_no}"
    )

# -------- LIST HELPERS --------

def build_list(rows, condition_fn, title):
    result = []
    for r in rows:
        surname = r.get("surname", "").strip()
        if not surname:
            continue
        if condition_fn(r):
            value = r.get("knife") or r.get("locker") or ""
            result.append(f"{surname} — {value}")

    if not result:
        return f"{title}\nНемає даних."

    text = title + "\n\n"
    for i, item in enumerate(result, 1):
        text += f"{i}. {item}\n"
    return text

# -------- KNIFE LIST --------

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    text = build_list(
        rows,
        lambda r: is_yes(r.get("knife")),
        "🔪 Прізвища з ножами:"
    )
    await update.message.reply_text(text)

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    text = build_list(
        rows,
        lambda r: is_no(r.get("knife")),
        "🚫 Прізвища без ножа:"
    )
    await update.message.reply_text(text)

# -------- LOCKER LIST --------

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    text = build_list(
        rows,
        lambda r: is_yes(r.get("locker")) or r.get("locker", "").isdigit(),
        "🔐 Прізвища з шафками:"
    )
    await update.message.reply_text(text)

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    text = build_list(
        rows,
        lambda r: is_no(r.get("locker")),
        "🚫 Прізвища без шафки:"
    )
    await update.message.reply_text(text)

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
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()

if __name__ == "__main__":
    main()
