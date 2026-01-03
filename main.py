import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===============================
# CONFIG
# ===============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

YES = {"yes", "y", "1", "+", "true", "так", "т", "є"}
NO  = {"no", "n", "0", "-", "false", "ні", "н"}

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

threading.Thread(target=run_health_server, daemon=True).start()

# ===============================
# DATA
# ===============================
def load_data():
    r = requests.get(CSV_URL, timeout=10)
    r.raise_for_status()
    reader = csv.DictReader(StringIO(r.text))
    return list(reader)

def norm(val: str) -> str:
    return val.strip().lower()

def is_yes(val: str) -> bool:
    return norm(val) in YES

def is_no(val: str) -> bool:
    return norm(val) in NO

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

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    knife_yes = knife_no = 0
    locker_yes = locker_no = 0

    for r in data:
        if is_yes(r.get("Ніж", "")):
            knife_yes += 1
        elif is_no(r.get("Ніж", "")):
            knife_no += 1

        if is_yes(r.get("Шафка", "")):
            locker_yes += 1
        elif is_no(r.get("Шафка", "")):
            locker_no += 1

    await update.message.reply_text(
        "📊 Статистика:\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🔐 З шафкою: {locker_yes}\n"
        f"🚫 Без шафки: {locker_no}"
    )

def build_list(title, rows):
    if not rows:
        return f"{title}\nНемає даних."
    text = f"{title}\n"
    for i, (name, cnt) in enumerate(rows, 1):
        text += f"{i}. {name} — {cnt}\n"
    return text

def collect(data, field, want_yes=True):
    res = {}
    for r in data:
        name = r.get("Прізвище та імʼя", "").strip()
        if not name:
            continue
        val = r.get(field, "")
        ok = is_yes(val) if want_yes else is_no(val)
        if ok:
            res[name] = res.get(name, 0) + 1
    return sorted(res.items())

async def knife_list(update, context):
    data = load_data()
    rows = collect(data, "Ніж", True)
    await update.message.reply_text(build_list("🔪 Прізвища з ножами:", rows))

async def no_knife_list(update, context):
    data = load_data()
    rows = collect(data, "Ніж", False)
    await update.message.reply_text(build_list("🚫 Прізвища без ножа:", rows))

async def locker_list(update, context):
    data = load_data()
    rows = collect(data, "Шафка", True)
    await update.message.reply_text(build_list("🔐 Прізвища з шафками:", rows))

async def no_locker_list(update, context):
    data = load_data()
    rows = collect(data, "Шафка", False)
    await update.message.reply_text(build_list("🚫 Прізвища без шафки:", rows))

# ===============================
# MAIN
# ===============================
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
