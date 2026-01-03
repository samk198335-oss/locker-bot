import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# 🔧 RENDER FREE STABILIZATION (healthcheck)
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ==================================================
# 🔧 CONFIG
# ==================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

YES_VALUES = {"1", "yes", "y", "так", "true", "+"}
NO_VALUES = {"0", "no", "n", "ні", "false", "-"}

_cached_rows = None

# ==================================================
# 🔧 CSV LOADER (with cache)
# ==================================================

def load_csv():
    global _cached_rows
    if _cached_rows is not None:
        return _cached_rows

    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()

    content = response.content.decode("utf-8")
    reader = csv.reader(StringIO(content))

    rows = []
    for row in reader:
        if any(cell.strip() for cell in row):
            rows.append([cell.strip() for cell in row])

    _cached_rows = rows
    return rows

# ==================================================
# 🔧 HELPERS
# ==================================================

def normalize(value: str) -> str:
    return value.strip().lower()

def get_name(row):
    for cell in row:
        if cell and not cell.isdigit():
            return cell
    return "—"

# ==================================================
# 🤖 COMMANDS
# ==================================================

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
    rows = load_csv()

    total = len(rows)
    knife_yes = knife_no = 0
    locker_yes = locker_no = 0

    for row in rows:
        knife = normalize(row[2]) if len(row) > 2 else ""
        locker = normalize(row[3]) if len(row) > 3 else ""

        if knife in YES_VALUES:
            knife_yes += 1
        elif knife in NO_VALUES:
            knife_no += 1

        if locker:
            locker_yes += 1
        else:
            locker_no += 1

    await update.message.reply_text(
        "📊 Статистика:\n"
        f"Всього записів: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🔪 Без ножа: {knife_no}\n\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"🗄 Без шафки: {locker_no}"
    )

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    yes = no = 0

    for row in rows:
        knife_val = normalize(row[2]) if len(row) > 2 else ""
        if knife_val in YES_VALUES:
            yes += 1
        elif knife_val in NO_VALUES:
            no += 1

    await update.message.reply_text(
        "🔪 Ніж:\n"
        f"З ножем: {yes}\n"
        f"Без ножа: {no}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    names = []

    for row in rows:
        knife_val = normalize(row[2]) if len(row) > 2 else ""
        if knife_val in YES_VALUES:
            name = get_name(row)
            names.append(name)

    if not names:
        await update.message.reply_text("🔪 З ножем нікого не знайдено")
        return

    text = "🔪 З ножем:\n"
    for i, name in enumerate(names, 1):
        text += f"{i}. {name}\n"

    await update.message.reply_text(text)

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    yes = no = 0

    for row in rows:
        locker_val = row[3].strip() if len(row) > 3 else ""
        if locker_val:
            yes += 1
        else:
            no += 1

    await update.message.reply_text(
        "🗄 Шафка:\n"
        f"З шафкою: {yes}\n"
        f"Без шафки: {no}"
    )

# ==================================================
# 🚀 MAIN
# ==================================================

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
