import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# =========================
# RENDER KEEP-ALIVE
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(("0.0.0.0", 10000), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# =========================
# DATA LOADING
# =========================

def load_data():
    resp = requests.get(CSV_URL, timeout=10)
    resp.raise_for_status()
    csv_file = StringIO(resp.text)
    reader = csv.DictReader(csv_file)
    return list(reader)

# =========================
# NORMALIZERS
# =========================

def has_knife(value: str) -> bool:
    if not value:
        return False
    return value.strip() in ["1", "yes", "так", "+"]

def has_locker(value: str) -> bool:
    if not value:
        return False
    v = value.strip().lower()
    return v not in ["-", "ні", "нема", "no", "нет", ""]

# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Привіт!\n\n"
        "/stats\n"
        "/locker_list\n"
        "/no_locker_list\n"
        "/knife_list\n"
        "/no_knife_list\n"
        "/find <прізвище>\n"
        "/filter"
    )
    await update.message.reply_text(text)

# -------------------------

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    total = len(data)
    knife_yes = sum(1 for r in data if has_knife(r.get("knife", "")))
    knife_no = total - knife_yes

    locker_yes = sum(1 for r in data if has_locker(r.get("locker", "")))
    locker_no = total - locker_yes

    text = (
        f"📊 Статистика:\n\n"
        f"Всього: {total}\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n"
        f"🗄 З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

    await update.message.reply_text(text)

# -------------------------

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [r["surname"] for r in data if has_knife(r.get("knife", ""))]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

# -------------------------

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    rows = [r["surname"] for r in data if not has_knife(r.get("knife", ""))]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

# -------------------------

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    rows = [
        f'{r["surname"]} — шафка {r["locker"]}'
        for r in data
        if has_locker(r.get("locker", ""))
    ]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

# -------------------------

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    rows = [
        r["surname"]
        for r in data
        if not has_locker(r.get("locker", ""))
    ]

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

# -------------------------

async def find_person(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗ Використання:\n/find <прізвище>")
        return

    query = " ".join(context.args).lower()
    data = load_data()

    results = []
    for r in data:
        if query in r["surname"].lower():
            knife = "🔪" if has_knife(r.get("knife", "")) else "—"
            locker = r["locker"] if has_locker(r.get("locker", "")) else "—"
            results.append(
                f'{r["surname"]} | ніж: {knife} | шафка: {locker}'
            )

    await update.message.reply_text(
        "\n".join(results) if results else "Не знайдено"
    )

# =========================
# FILTER MENU
# =========================

async def filter_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🔪 З ножем", "🚫 Без ножа"],
        ["🗄 З шафкою", "❌ Без шафки"],
        ["👥 Всі"]
    ]
    await update.message.reply_text(
        "🔍 Обери фільтр:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# -------------------------

async def filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    data = load_data()

    if text == "🔪 З ножем":
        rows = [r["surname"] for r in data if has_knife(r.get("knife", ""))]

    elif text == "🚫 Без ножа":
        rows = [r["surname"] for r in data if not has_knife(r.get("knife", ""))]

    elif text == "🗄 З шафкою":
        rows = [
            f'{r["surname"]} — шафка {r["locker"]}'
            for r in data
            if has_locker(r.get("locker", ""))
        ]

    elif text == "❌ Без шафки":
        rows = [
            r["surname"]
            for r in data
            if not has_locker(r.get("locker", ""))
        ]

    elif text == "👥 Всі":
        rows = [r["surname"] for r in data]

    else:
        return

    await update.message.reply_text(
        "\n".join(rows) if rows else "Немає даних"
    )

# =========================
# MAIN
# =========================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))
    app.add_handler(CommandHandler("find", find_person))
    app.add_handler(CommandHandler("filter", filter_menu))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, filter_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
