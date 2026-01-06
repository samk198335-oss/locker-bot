import os
import csv
import json
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==================================================
# 🔧 CONFIG
# ==================================================

TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
LOCAL_DB = "local_db.json"

# ==================================================
# 🔧 RENDER KEEP-ALIVE
# ==================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", int(os.getenv("PORT", 10000))), HealthHandler)
    server.serve_forever()

# ==================================================
# 📦 DATA LAYER (CSV → JSON)
# ==================================================

def load_csv_data():
    response = requests.get(CSV_URL, timeout=10)
    response.raise_for_status()

    f = StringIO(response.text)
    reader = csv.DictReader(f)

    data = []
    for row in reader:
        data.append({
            "Address": row.get("Address", "").strip(),
            "surname": row.get("surname", "").strip(),
            "knife": row.get("knife", "").strip(),
            "locker": row.get("locker", "").strip(),
        })
    return data

def load_data():
    if os.path.exists(LOCAL_DB):
        with open(LOCAL_DB, "r", encoding="utf-8") as f:
            return json.load(f)

    data = load_csv_data()
    save_data(data)
    return data

def save_data(data):
    with open(LOCAL_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================================================
# 🧠 HELPERS
# ==================================================

def is_yes(value: str) -> bool:
    if not value:
        return False
    value = value.strip().lower()
    return value in ["1", "yes", "+", "так", "є", "true"]

def has_locker(value: str) -> bool:
    if not value:
        return False
    value = value.strip().lower()
    return value not in ["-", "ні", "нема", "no", "0"]

# ==================================================
# 🧾 LOAD DATA ON START
# ==================================================

DATA = load_data()

# ==================================================
# 🧩 UI
# ==================================================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄 З шафкою", "❌ Без шафки"],
        ["👥 Всі", "📊 Статистика"],
    ],
    resize_keyboard=True,
)

# ==================================================
# 🤖 HANDLERS
# ==================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вибери потрібний фільтр 👇",
        reply_markup=MAIN_KEYBOARD,
    )

def build_list(rows):
    return "\n".join(rows) if rows else "Немає даних"

async def handle_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    rows = []

    if text == "🔪 З ножем":
        rows = [r["surname"] for r in DATA if is_yes(r["knife"])]

    elif text == "🚫 Без ножа":
        rows = [r["surname"] for r in DATA if not is_yes(r["knife"])]

    elif text == "🗄 З шафкою":
        rows = [
            f'{r["surname"]} — {r["locker"]}'
            for r in DATA
            if has_locker(r["locker"])
        ]

    elif text == "❌ Без шафки":
        rows = [r["surname"] for r in DATA if not has_locker(r["locker"])]

    elif text == "👥 Всі":
        rows = [r["surname"] for r in DATA]

    elif text == "📊 Статистика":
        total = len(DATA)
        knife_yes = sum(1 for r in DATA if is_yes(r["knife"]))
        knife_no = total - knife_yes
        locker_yes = sum(1 for r in DATA if has_locker(r["locker"]))
        locker_no = total - locker_yes

        msg = (
            f"📊 Статистика:\n\n"
            f"Всього: {total}\n"
            f"🔪 З ножем: {knife_yes}\n"
            f"🚫 Без ножа: {knife_no}\n"
            f"🗄 З шафкою: {locker_yes}\n"
            f"❌ Без шафки: {locker_no}"
        )
        await update.message.reply_text(msg)
        return

    await update.message.reply_text(build_list(rows))

# ==================================================
# 🚀 MAIN
# ==================================================

def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filters))

    app.run_polling()

if __name__ == "__main__":
    main()
