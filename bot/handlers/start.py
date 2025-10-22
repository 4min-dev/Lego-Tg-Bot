import datetime
import sqlite3
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler
from bot.config import DB_FILE
import bot.handlers.media as media_handlers
import bot.texts as texts 
from bot.handlers.funnel import send_reminder
from bot.utils.logger import logger
from bot.utils.scheduler import get_scheduler

ADMIN_IDS = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS.split(",") if x.strip().isdigit()]

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id

    logger.info(f"Обработка команды /start для user_id {user.id}, chat_id {chat_id}")

    source = 'qr'
    if update.message.text.startswith('/start '):
        payload = update.message.text.split(' ', 1)[1]
        source = payload if payload in ['qr', 'deeplink'] else 'unknown'

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user.id,))
    if not c.fetchone():
        start_date = datetime.datetime.now().isoformat()
        c.execute(
            'INSERT INTO users (user_id, username, first_name, start_date, source, consent_status) VALUES (?, ?, ?, ?, ?, ?)',
            (user.id, user.username, user.first_name, start_date, source, 'pending')
        )
        conn.commit()
        c.execute('SELECT consent_status FROM users WHERE user_id = ?', (user.id,))
        consent_status = c.fetchone()[0]
        logger.info(f"Создан новый пользователь user_id {user.id} с consent_status='{consent_status}'")
    conn.close()

    await context.bot.send_message(chat_id=chat_id, text=texts.WELCOME_TEXT)
    video_file_id = getattr(media_handlers, 'VIDEO_FILE_ID', None)
    if video_file_id:
        try:
            await context.bot.send_video_note(chat_id=chat_id, video_note=video_file_id)
        except Exception as e:
            logger.warning(f"Не удалось отправить видео: {e}")

    await asyncio.sleep(10)

    await context.bot.send_message(chat_id=chat_id, text=texts.SUPPORT_TEXT)
    await asyncio.sleep(10)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, хочу быть в курсе!", callback_data='consent_yes')],
        [InlineKeyboardButton("❌ Пока нет", callback_data='consent_no')]
    ])
    await context.bot.send_message(chat_id=chat_id, text=texts.CONSENT_TEXT, reply_markup=keyboard)

    logger.info(f"Планирование напоминания для user_id {user.id} через 5 секунд")
    context.job_queue.run_once(
        send_reminder,
        when=5,
        data={'chat_id': chat_id, 'user_id': user.id},
        name=f"reminder_{user.id}"
    )
    logger.info(f"Добавлена задача напоминания для user_id {user.id} через 5 секунд")

def register(application):
    application.add_handler(CommandHandler("start", start))