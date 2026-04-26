import os
import io
import requests
import fitz
import anthropic
import sqlite3
from datetime import datetime
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
YOUR_CHAT_ID = os.environ.get("YOUR_CHAT_ID")

PDF_URL = "https://www.caica.ru/ANI_Official/notam/dnldnotam/notam-rus_{date}_0600.pdf"
KEYWORDS = ["УЛКК", "УЛВВ", "УЛВЦ", "УЛВУ"]

def get_today_url():
    moscow = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow)
    date_str = now.strftime("%d%m%y")
    return PDF_URL.format(date=date_str)

def download_and_parse():
    url = get_today_url()
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        return f"❌ Не удалось скачать PDF: {e}"

    pdf = fitz.open(stream=response.content, filetype="pdf")
    full_text = ""
    for page in pdf:
        full_text += page.get_text()

    paragraphs = full_text.split("\n\n")
    found = []
    for para in paragraphs:
        for kw in KEYWORDS:
            if kw in para:
                found.append(para.strip())
                break

    if not found:
        return "📭 Сегодня абзацев с УЛКК, УЛВВ, УЛВЦ, УЛВУ не найдено."

    result = f"📋 NOTAM на {datetime.now(pytz.timezone('Europe/Moscow')).strftime('%d.%m.%Y')}:\n\n"
    result += "\n\n---\n\n".join(found)
    return result

def init_db():
    conn = sqlite3.connect("users.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user):
    conn = sqlite3.connect("users.db")
    conn.execute(
        "INSERT OR IGNORE INTO users (id, username, first_name) VALUES (?, ?, ?)",
        (user.id, user.username, user.first_name)
    )
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("users.db")
    users = conn.execute("SELECT id FROM users").fetchall()
    conn.close()
    return [row[0] for row in users]

MENU = ReplyKeyboardMarkup(
    [["📋 Получить NOTAM сейчас", "🤖 Спросить AI"]],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\n"
        f"Каждый день в 7:00 по Москве я буду присылать NOTAM.\n"
        f"Или нажми кнопку чтобы получить прямо сейчас:",
        reply_markup=MENU
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    text = update.message.text

    if text == "📋 Получить NOTAM сейчас":
        await update.message.reply_text("⏳ Скачиваю PDF...")
        result = download_and_parse()
        for i in range(0, len(result), 4000):
            await update.message.reply_text(result[i:i+4000])
        return

    if text == "🤖 Спросить AI":
        context.user_data["mode"] = "ai"
        await update.message.reply_text("Задайте ваш вопрос:")
        return

    if context.user_data.get("mode") == "ai":
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        await update.message.reply_text("⏳ Думаю...")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": text}]
        )
        context.user_data["mode"] = None
        await update.message.reply_text(response.content[0].text)

async def daily_notam(bot):
    users = get_all_users()
    result = download_and_parse()
    for user_id in users:
        try:
            for i in range(0, len(result), 4000):
                await bot.send_message(chat_id=user_id, text=result[i:i+4000])
        except Exception:
            pass

init_db()
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
scheduler.add_job(daily_notam, "cron", hour=7, minute=0, args=[app.bot])
scheduler.start()

print("Бот запущен...")
app.run_polling()
