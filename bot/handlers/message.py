import sqlite3
import logging
from telegram import Update
from telegram.ext import CallbackContext
from bot.config import DB_FILE
import bot.texts as texts

logger = logging.getLogger(__name__)

async def handle_user_message(update: Update, context: CallbackContext) -> None:
    """Обрабатываем любые текстовые сообщения пользователя, которые не являются командами"""
    user_id = update.effective_user.id
    msg_text = update.message.text
    logger.info(f"handle_user_message: Получено сообщение '{msg_text}' от user_id={user_id}")

    if context.user_data.get('editing_text_key'):
        logger.info(f"Пропущено сообщение в handle_user_message: пользователь редактирует текст (editing_text_key={context.user_data['editing_text_key']})")
        return

    await update.message.reply_text(texts.WRONG_MESSAGE_TEXT)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET dialog = dialog || ? || '\n' WHERE user_id = ?", (msg_text, user_id))
    conn.commit()
    conn.close()

def register(app):
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))