import os
import anthropic
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")

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
    [["🤖 Спросить AI", "📢 Рассылка"]],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}! 👋\nВыбери действие:",
        reply_markup=MENU
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    text = update.message.text

    if text == "📢 Рассылка":
        context.user_data["mode"] = "broadcast"
        await update.message.reply_text("Введите текст для рассылки:")
        return

    if text == "🤖 Спросить AI":
        context.user_data["mode"] = "ai"
        await update.message.reply_text("Задайте ваш вопрос:")
        return

    if context.user_data.get("mode") == "broadcast":
        context.user_data["mode"] = None
        users = get_all_users()
        sent = 0
        for user_id in users:
            try:
                await context.bot.send_message(chat_id=user_id, text=text)
                sent += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ Рассылка отправлена {sent} пользователям.")
        return

    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    await update.message.reply_text("⏳ Думаю...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": text}]
    )
    reply = response.content[0].text
    context.user_data["mode"] = None
    await update.message.reply_text(reply)

init_db()
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен...")
app.run_polling()
