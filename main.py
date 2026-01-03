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

# =========================
# KEEP ALIVE (RENDER)
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health():
    HTTPServer(("0.0.0.0", 10000), HealthHandler).serve_forever()

threading.Thread(target=run_health, daemon=True).start()

# =========================
# CSV LOAD + NORMALIZE
# =========================

_cached = None

def load_csv():
    global _cached
    if _cached:
        return _cached

    r = requests.get(CSV_URL, timeout=10)
    r.raise_for_status()

    reader = csv.DictReader(StringIO(r.text))
    rows = []

    for row in reader:
        clean = {}
        for k, v in row.items():
            if k:
                clean[k.strip().lower()] = v
        rows.append(clean)

    _cached = rows
    return rows

def safe_int(v):
    try:
        return int(str(v).strip())
    except:
        return 0

def has_value(v):
    if not v:
        return False
    s = str(v).strip().lower()
    return s not in ["0", "-", "ні", "нет", "no", ""]

# =========================
# COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступні команди:\n"
        "/stats\n"
        "/knife\n"
        "/knife_list\n"
        "/locker"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    total = len(rows)

    knife_yes = sum(safe_int(r.get("knife")) for r in rows if safe_int(r.get("knife")) > 0)
    knife_no = total - sum(1 for r in rows if safe_int(r.get("knife")) > 0)

    locker_yes = sum(1 for r in rows if has_value(r.get("locker")))
    locker_no = total - locker_yes

    await update.message.reply_text(
        f"📊 Статистика:\n"
        f"Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🔪 Без ножа: {knife_no}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"🗄️ Без шафки: {locker_no}"
    )

async def knife(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    with_knife = sum(safe_int(r.get("knife")) for r in rows if safe_int(r.get("knife")) > 0)
    without_knife = len(rows) - sum(1 for r in rows if safe_int(r.get("knife")) > 0)

    await update.message.reply_text(
        f"🔪 Ніж:\n"
        f"З ножем: {with_knife}\n"
        f"Без ножа: {without_knife}"
    )

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    lines = ["🔪 Прізвища з ножами:"]

    i = 1
    for r in rows:
        name = str(r.get("surname", "")).strip()
        count = safe_int(r.get("knife"))
        if name and count > 0:
            lines.append(f"{i}. {name} — {count}")
            i += 1

    if i == 1:
        await update.message.reply_text("🔪 Немає даних по ножах.")
    else:
        await update.message.reply_text("\n".join(lines))

async def locker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    yes = sum(1 for r in rows if has_value(r.get("locker")))
    no = len(rows) - yes

    await update.message.reply_text(
        f"🗄️ Шафки:\n"
        f"З шафкою: {yes}\n"
        f"Без шафки: {no}"
    )

# =========================
# START APP
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("knife", knife))
    app.add_handler(CommandHandler("knife_list", knife_list))
    app.add_handler(CommandHandler("locker", locker))

    app.run_polling()

if __name__ == "__main__":
    main()
