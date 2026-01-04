import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==============================
# CONFIG
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ==============================
# RENDER KEEP-ALIVE
# ==============================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", int(os.getenv("PORT", 10000))), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ==============================
# CSV LOADER
# ==============================

def load_data():
    response = requests.get(CSV_URL)
    response.encoding = "utf-8"
    csv_file = StringIO(response.text)
    reader = csv.DictReader(csv_file)

    data = []
    for row in reader:
        data.append({
            "address": row.get("Address", "").strip(),
            "surname": row.get("surname", "").strip(),
            "knife": row.get("knife", "").strip(),
            "locker": row.get("locker", "").strip(),
        })
    return data

# ==============================
# HELPERS
# ==============================

def has_knife(value: str) -> bool:
    return value == "1"

def no_knife(value: str) -> bool:
    return value == "0"

def has_locker(value: str) -> bool:
    if not value:
        return False
    v = value.lower()
    return (
        v.isdigit()
        or "так" in v
        or "є" in v
        or "име" in v
        or "ключ" in v
    )

def no_locker(value: str) -> bool:
    return not has_locker(value)

# ==============================
# COMMANDS
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт!\n\n"
        "Команди:\n"
        "/stats\n"
        "/knife_list – прізвище + ніж\n"
        "/no_knife_list – без ножа\n"
        "/locker_list – прізвище + шафка\n"
        "/no_locker_list – без шафки"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    total = len(data)
    knife_yes = sum(1 for r in data if has_knife(r["knife"]))
    knife_no = sum(1 for r in data if no_knife(r["knife"]))
    locker_yes = sum(1 for r in data if has_locker(r["locker"]))
    locker_no = sum(1 for r in data if no_locker(r["locker"]))

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"❌ Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        f"{r['surname']} — ніж"
        for r in data
        if has_knife(r["knife"]) and r["surname"]
    ]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        r["surname"]
        for r in data
        if no_knife(r["knife"]) and r["surname"]
    ]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        f"{r['surname']} — {r['locker']}"
        for r in data
        if has_locker(r["locker"]) and r["surname"]
    ]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [
        r["surname"]
        for r in data
        if no_locker(r["locker"]) and r["surname"]
    ]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

# ==============================
# MAIN
# ==============================

def main():
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
