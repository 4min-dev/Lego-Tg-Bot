import sqlite3
import logging
from telegram import Update
from telegram.ext import CallbackContext
from bot.config import DB_FILE
from bot.texts import WRONG_MESSAGE_TEXT

logger = logging.getLogger(__name__)

async def handle_user_message(update: Update, context: CallbackContext) -> None:
    """Обрабатываем любые текстовые сообщения пользователя, которые не являются командами"""
    user_id = update.effective_user.id
    msg_text = update.message.text

    # Отправляем текст с инструкцией обращаться в поддержку
    await update.message.reply_text(WRONG_MESSAGE_TEXT)

    # Сохраняем диалог пользователя в БД
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET dialog = dialog || ? || '\n' WHERE user_id = ?", (msg_text, user_id))
    conn.commit()
    conn.close()

def register(app):
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
