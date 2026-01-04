import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"
PORT = int(os.environ.get("PORT", 10000))


# ===============================
# KEEP ALIVE (RENDER)
# ===============================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

threading.Thread(target=run_health, daemon=True).start()


# ===============================
# CSV
# ===============================
def load_csv():
    r = requests.get(CSV_URL, timeout=10)
    r.raise_for_status()
    return list(csv.DictReader(StringIO(r.text)))


def has_value(v: str) -> bool:
    return bool(v and v.strip())


# ===============================
# STATS
# ===============================
def get_stats():
    rows = load_csv()

    total = len(rows)
    knife_yes = knife_no = 0
    locker_yes = locker_no = 0

    for r in rows:
        if has_value(r.get("Ніж", "")):
            knife_yes += 1
        else:
            knife_no += 1

        if has_value(r.get("Шафка", "")):
            locker_yes += 1
        else:
            locker_no += 1

    return total, knife_yes, knife_no, locker_yes, locker_no


# ===============================
# LISTS (ОДНАКОВА ЛОГІКА)
# ===============================
def list_with_value(column):
    rows = load_csv()
    result = []

    for r in rows:
        name = r.get("Прізвище", "").strip()
        value = r.get(column, "").strip()

        if name and value:
            result.append(f"{name} — {value}")

    return result


def list_without_value(column):
    rows = load_csv()
    result = []

    for r in rows:
        name = r.get("Прізвище", "").strip()
        value = r.get(column, "").strip()

        if name and not value:
            result.append(name)

    return result


# ===============================
# COMMANDS
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Alexpuls_bot працює\n\n"
        "/stats — статистика\n"
        "/knife_list — прізвища з ножами\n"
        "/no_knife_list — без ножів\n"
        "/locker_list — прізвища з шафками\n"
        "/no_locker_list — без шафок"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t, ky, kn, ly, ln = get_stats()
    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"Всього: {t}\n\n"
        f"🔪 З ножем: {ky}\n"
        f"❌ Без ножа: {kn}\n\n"
        f"🗄 З шафкою: {ly}\n"
        f"❌ Без шафки: {ln}"
    )


async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = list_with_value("Ніж")
    await update.message.reply_text(
        "🔪 Прізвища з ножами:\n" + ("\n".join(data) if data else "Немає даних")
    )


async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = list_without_value("Ніж")
    await update.message.reply_text(
        "❌ Без ножів:\n" + ("\n".join(data) if data else "Немає даних")
    )


async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = list_with_value("Шафка")
    await update.message.reply_text(
        "🗄 Прізвища з шафками:\n" + ("\n".join(data) if data else "Немає даних")
    )


async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = list_without_value("Шафка")
    await update.message.reply_text(
        "❌ Без шафок:\n" + ("\n".join(data) if data else "Немає даних")
    )


# ===============================
# MAIN
# ===============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("no_knife_list", no_knife_list))
    app.add_handler(CommandHandler("locker_list", locker_list))
    app.add_handler(CommandHandler("no_locker_list", no_locker_list))

    app.run_polling()


if __name__ == "__main__":
    main()
