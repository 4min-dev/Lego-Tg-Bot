import sqlite3
import logging
from telegram import Update
from telegram.ext import CallbackContext
from .funnel import start_funnel
from bot.config import DB_FILE
from bot.texts import CONSENT_YES_TEXT

logger = logging.getLogger(__name__)

async def subscribe(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Обновляем статус пользователя в БД
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET consent_status = 'yes' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Отправляем приветственное сообщение
    await update.message.reply_text(CONSENT_YES_TEXT)

    # Запускаем автоворонку
    start_funnel(context, user_id, chat_id)

def register(app):
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("subscribe", subscribe))
