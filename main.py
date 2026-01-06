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

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# =========================
# RENDER KEEP ALIVE
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# =========================
# CSV LOADER
# =========================

def load_csv():
    response = requests.get(CSV_URL, timeout=10)
    response.encoding = "utf-8"
    reader = csv.DictReader(StringIO(response.text))
    return list(reader)

# =========================
# HELPERS
# =========================

def has_knife(value: str) -> bool:
    return str(value).strip() in ("1", "2", "yes", "так", "Так", "+")

def has_locker(value: str) -> bool:
    v = str(value).strip()
    return v not in ("", "-", "0", "ні", "Ні", "no")

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

# -------- STATS --------

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()

    total = len(rows)
    knife_yes = 0
    knife_no = 0
    locker_yes = 0
    locker_no = 0

    for r in rows:
        if has_knife(r.get("knife", "")):
            knife_yes += 1
        else:
            knife_no += 1

        if has_locker(r.get("locker", "")):
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"👥 Всього: {total}\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

# -------- LISTS --------

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        if has_locker(r.get("locker", "")):
            result.append(f"{r.get('surname','')} — {r.get('locker')}")

    text = "🗄 З шафкою:\n\n" + "\n".join(result) if result else "Немає даних"
    await update.message.reply_text(text)

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        if not has_locker(r.get("locker", "")):
            result.append(r.get("surname", ""))

    text = "❌ Без шафки:\n\n" + "\n".join(result) if result else "Немає даних"
    await update.message.reply_text(text)

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        if has_knife(r.get("knife", "")):
            result.append(r.get("surname", ""))

    text = "🔪 З ножем:\n\n" + "\n".join(result) if result else "Немає даних"
    await update.message.reply_text(text)

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    result = []

    for r in rows:
        if not has_knife(r.get("knife", "")):
            result.append(r.get("surname", ""))

    text = "🚫 Без ножа:\n\n" + "\n".join(result) if result else "Немає даних"
    await update.message.reply_text(text)

# -------- FIND --------

async def find_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Використання:\n/find <прізвище>")
        return

    query = " ".join(context.args).lower()
    rows = load_csv()

    found = []

    for r in rows:
        surname = r.get("surname", "")
        if query in surname.lower():
            knife = "так" if has_knife(r.get("knife", "")) else "ні"
            locker = r.get("locker", "")
            locker_text = locker if has_locker(locker) else "немає"
            address = r.get("Address", "")

            found.append(
                f"👤 {surname}\n"
                f"🔪 Ніж: {knife}\n"
                f"🗄 Шафка: {locker_text}\n"
                f"📍 {address}\n"
            )

    if not found:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text("\n".join(found))

# =========================
# MAIN
# =========================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("find", find_person))

    app.run_polling()

if __name__ == "__main__":
    main()
