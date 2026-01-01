import os
import csv
import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")

CSV_URL = "https://docs.google.com/spreadsheets/d/1blFK5rFOZ2PzYAQldcQd8GkmgK/export?format=csv"
# ============================================


def load_data():
    response = requests.get(CSV_URL, timeout=20)
    response.encoding = "utf-8"
    reader = csv.DictReader(response.text.splitlines())
    return list(reader)


def format_row(row):
    return (
        f"📍 Адреса: {row.get('Adress', '-')}\n"
        f"👤 Прізвище: {row.get('surname', '-')}\n"
        f"🔪 Ніж: {row.get('knife', '-')}\n"
        f"🔐 Шафка: {row.get('locker', '-')}\n"
        "----------------------"
    )


def has_knife(value):
    try:
        return int(value) > 0
    except:
        return False


def has_locker(value):
    if not value:
        return
