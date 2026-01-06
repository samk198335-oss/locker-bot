import os
import csv
import threading
import requests
from io import StringIO
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgKmgqr1G5BkD40wtOMI/export?format=csv"

# ================== RENDER KEEP-ALIVE ==================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()

# ================== CSV ==================
def load_csv():
    resp = requests.get(CSV_URL, timeout=15)
    resp.encoding = "utf-8"
    reader = csv.DictReader(StringIO(resp.text))
    return list(reader)

def has_value(val):
    if not val:
        return False
    v = str(val).strip().lower()
    return v not in ["", "-", "нет", "ні", "no", "0"]

def has_knife(val):
    if not val:
        return False
    return str(val).strip() in ["1", "yes", "так", "+"]

# ================== COMMANDS ==================
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
    knife_yes = sum(1 for r in rows if has_knife(r.get("knife")))
    knife_no = total - knife_yes

    locker_yes = sum(1 for r in rows if has_value(r.get("locker")))
    locker_no = total - locker_yes

    await update.message.reply_text(
        f"📊 Статистика:\n\n"
        f"👥 Всього: {total}\n\n"
        f"🔪 З ножем: {knife_yes}\n"
        f"🚫 Без ножа: {knife_no}\n\n"
        f"🗄️ З шафкою: {locker_yes}\n"
        f"❌ Без шафки: {locker_no}"
    )

async def locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        f"{r['surname']} — {r['locker']}"
        for r in rows
        if has_value(r.get("locker"))
    ]

    if not data:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text("🗄️ З шафкою:\n\n" + "\n".join(data))

async def no_locker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        r["surname"]
        for r in rows
        if not has_value(r.get("locker"))
    ]

    if not data:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text("❌ Без шафки:\n\n" + "\n".join(data))

async def knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        r["surname"]
        for r in rows
        if has_knife(r.get("knife"))
    ]

    if not data:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text("🔪 З ножем:\n\n" + "\n".join(data))

async def no_knife_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = load_csv()
    data = [
        r["surname"]
        for r in rows
        if not has_knife(r.get("knife"))
    ]

    if not data:
        await update.message.reply_text("❌ Немає даних")
        return

    await update.message.reply_text("🚫 Без ножа:\n\n" + "\n".join(data))

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
            locker = r.get("locker", "")
            knife = "🔪" if has_knife(r.get("knife")) else "🚫"
            locker_text = locker if has_value(locker) else "без шафки"
            results.append(f"{name} — {locker_text} — {knife}")

    if not results:
        await update.message.reply_text("❌ Нічого не знайдено")
        return

    await update.message.reply_text("🔍 Результати:\n\n" + "\n".join(results))

# ================== MAIN ==================
def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

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
