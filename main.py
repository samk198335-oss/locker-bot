import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================================================
# 🔧 RENDER FREE STABILIZATION (Health Check)
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ==================================================
# ⚙️ CONFIG
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI"
    "/export?format=csv"
)

YES_VALUES = {"yes", "+", "так", "y"}
NO_VALUES = {"no", "-", "ні", "n"}

# ==================================================
# 📥 CSV LOADER
# ==================================================

def load_csv():
    response = requests.get(CSV_URL, timeout=20)
    response.raise_for_status()
    content = response.content.decode("utf-8")
    reader = csv.DictReader(StringIO(content))
    return list(reader)

def normalize(value: str):
    if not value:
        return None
    value = value.strip().lower()
    if value in YES_VALUES:
        return True
    if value in NO_VALUES:
        return False
    return None

# ==================================================
# 📊 LOGIC
# ==================================================

def analyze_data(rows):
    total = 0

    knife_yes = 0
    knife_no = 0
    knife_people = []

    locker_yes = 0
    locker_no = 0
    locker_people = []

    for row in rows:
        name = (row.get("Прізвище") or "").strip()
        number = (row.get("№") or "").strip()

        knife = normalize(row.get("Ніж"))
        locker = normalize(row.get("Шафка"))

        if knife is None and locker is None:
            continue

        total += 1
        person = f"{number} {name}".strip()

        if knife is True:
            knife_yes += 1
            if person:
                knife_people.append(person)
        elif knife is False:
            knife_no += 1

        if locker is True:
            locker_yes += 1
            if person:
                locker_people.append(person)
        elif locker is False:
            locker_no += 1

    return {
        "total": total,
        "knife_yes": knife_yes,
        "knife_no": knife_no,
        "knife_people": knife_people,
        "locker_yes": locker_yes,
        "locker_no": locker_no,
        "locker_people": locker_people,
    }

# ==================================================
# 🤖 COMMANDS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! 👋\n"
        "Доступні команди:\n"
        "/stats — загальна статистика\n"
        "/knife — хто з ножем\n"
        "/locker — хто з шафкою"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = analyze_data(rows)

    text = (
        f"📊 Статистика:\n"
        f"Всього записів: {data['total']}\n\n"
        f"🔪 З ножем: {data['knife_yes']}\n"
        f"🔪 Без ножа: {data['knife_no']}\n\n"
        f"🗄 З шафкою: {data['locker_yes']}\n"
        f"🗄 Без шафки: {data['locker_no']}"
    )

    await update.message.reply_text(text)

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = analyze_data(rows)

    if not data["knife_people"]:
        await update.message.reply_text("Немає людей з ножем.")
        return

    text = "🔪 З ножем:\n" + "\n".join(data["knife_people"])
    await update.message.reply_text(text)

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = analyze_data(rows)

    if not data["locker_people"]:
        await update.message.reply_text("Немає людей з шафкою.")
        return

    text = "🗄 З шафкою:\n" + "\n".join(data["locker_people"])
    await update.message.reply_text(text)

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("locker", locker))

    app.run_polling()

if __name__ == "__main__":
    main()
