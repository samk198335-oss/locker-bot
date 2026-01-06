import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# =========================
# RENDER KEEP-ALIVE
# =========================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# =========================
# CSV LOAD
# =========================
def load_csv():
    response = requests.get(CSV_URL, timeout=10)
    response.raise_for_status()
    content = response.content.decode("utf-8")
    reader = csv.DictReader(StringIO(content))
    return list(reader)

def has_value(val):
    return val and val.strip() not in ["", "-", "ні", "нет", "no", "0"]

def knife_yes(val):
    return val and val.strip() in ["1", "2", "так", "yes", "+"]

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

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    total = len(rows)

    knife_yes_count = sum(1 for r in rows if knife_yes(r.get("knife", "")))
    knife_no_count = total - knife_yes_count

    locker_yes_count = sum(1 for r in rows if has_value(r.get("locker", "")))
    locker_no_count = total - locker_yes_count

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes_count}\n"
        f"🚫 Без ножа: {knife_no_count}\n\n"
        f"🗄 З шафкою: {locker_yes_count}\n"
        f"❌ Без шафки: {locker_no_count}"
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    lines = []

    for r in rows:
        locker = r.get("locker", "").strip()
        if has_value(locker):
            name = r.get("surname", "").strip()
            lines.append(f"— {name} ({locker})")

    await update.message.reply_text("🗄 З шафкою:\n\n" + "\n".join(lines) if lines else "Немає даних")

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    lines = []

    for r in rows:
        if not has_value(r.get("locker", "")):
            name = r.get("surname", "").strip()
            lines.append(f"— {name}")

    await update.message.reply_text("❌ Без шафки:\n\n" + "\n".join(lines) if lines else "Немає даних")

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    lines = []

    for r in rows:
        if knife_yes(r.get("knife", "")):
            name = r.get("surname", "").strip()
            lines.append(f"— {name}")

    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(lines) if lines else "Немає даних")

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    lines = []

    for r in rows:
        if not knife_yes(r.get("knife", "")):
            name = r.get("surname", "").strip()
            lines.append(f"— {name}")

    await update.message.reply_text("🚫 Без ножа:\n\n" + "\n".join(lines) if lines else "Немає даних")

# =========================
# FIND COMMAND
# =========================
async def find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Використання:\n/find <прізвище>")
        return

    query = " ".join(context.args).lower()
    rows = load_csv()
    results = []

    for r in rows:
        name = r.get("surname", "")
        if query in name.lower():
            knife = "так" if knife_yes(r.get("knife", "")) else "ні"
            locker = r.get("locker", "").strip()
            locker = locker if has_value(locker) else "немає"
            address = r.get("Address", "").strip()

            results.append(
                f"👤 {name}\n"
                f"🔪 Ніж: {knife}\n"
                f"🗄 Шафка: {locker}\n"
                f"📍 {address}"
            )

    if not results:
        await update.message.reply_text("❌ Нічого не знайдено")
    else:
        await update.message.reply_text("\n\n".join(results))

# =========================
# MAIN
# =========================
def main():
    threading.Thread(target=start_health_server, daemon=True).start()

    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("find", find))

    app.run_polling()

if __name__ == "__main__":
    main()
