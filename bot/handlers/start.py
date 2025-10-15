import datetime
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler
from bot.config import DB_FILE
import bot.handlers.media as media_handlers  # Импорт модуля как алиас, без импорта переменных
from bot.texts import DESCRIPTION_TEXT, WELCOME_TEXT, SUPPORT_TEXT, CONSENT_TEXT
from bot.handlers.funnel import send_reminder
from bot.utils.logger import logger
from bot.utils.scheduler import get_scheduler

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Источник (qr / deeplink)
    source = 'qr'
    if update.message.text.startswith('/start '):
        payload = update.message.text.split(' ', 1)[1]
        source = payload if payload in ['qr', 'deeplink'] else 'unknown'

    # --- Сохраняем пользователя ---
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user.id,))
    if not c.fetchone():
        start_date = datetime.datetime.now().isoformat()
        c.execute('INSERT INTO users (user_id, username, first_name, start_date, source) VALUES (?, ?, ?, ?, ?)',
                  (user.id, user.username, user.first_name, start_date, source))
        conn.commit()
    conn.close()

    # --- Отправка description (динамически берём из media_handlers) ---
    if media_handlers.DESCRIPTION_IMAGE_FILE_ID:
        await context.bot.send_photo(chat_id=chat_id, photo=media_handlers.DESCRIPTION_IMAGE_FILE_ID, caption=DESCRIPTION_TEXT)
    else:
        await context.bot.send_message(chat_id=chat_id, text=DESCRIPTION_TEXT)

    # --- Приветственное сообщение и кружок (динамически берём из media_handlers) ---
    await context.bot.send_message(chat_id=chat_id, text=WELCOME_TEXT)
    if media_handlers.VIDEO_FILE_ID:
        await context.bot.send_video_note(chat_id=chat_id, video_note=media_handlers.VIDEO_FILE_ID)
    await context.bot.send_message(chat_id=chat_id, text=SUPPORT_TEXT)

    # --- Кнопки согласия ---
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, хочу быть в курсе!", callback_data='consent_yes')],
        [InlineKeyboardButton("❌ Пока нет", callback_data='consent_no')]
    ])
    await context.bot.send_message(chat_id=chat_id, text=CONSENT_TEXT, reply_markup=keyboard)

    # --- Планируем напоминание через 3 часа ---
    scheduler = get_scheduler(context)
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=datetime.datetime.now() + datetime.timedelta(hours=3),
        args=(context, chat_id, user.id),
        name=f"reminder_{user.id}"
    )
    logger.info(f"Добавлена задача напоминания для user_id {user.id}")


def register(application):
    application.add_handler(CommandHandler("start", start))