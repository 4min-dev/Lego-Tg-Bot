import sqlite3
import datetime
from telegram.ext import CallbackContext
from bot.config import DB_FILE
from bot.texts import FUNNEL_MESSAGES, REMINDER_TEXT
from bot.utils.logger import logger

async def send_reminder(context: CallbackContext, chat_id: int, user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT consent_status FROM users WHERE user_id=?", (user_id,))
    status = c.fetchone()
    if status and status[0] == 'pending':
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, хочу быть в курсе!", callback_data='consent_yes')],
            [InlineKeyboardButton("❌ Пока нет", callback_data='consent_no')]
        ])
        await context.bot.send_message(chat_id=chat_id, text=REMINDER_TEXT, reply_markup=keyboard)
    conn.close()

def start_funnel(context: CallbackContext, user_id: int, chat_id: int):
    now = datetime.datetime.now()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for idx, msg in enumerate(FUNNEL_MESSAGES):
        run_date = now + datetime.timedelta(days=msg["delay_days"])
        c.execute("UPDATE users SET next_send=? WHERE user_id=?", (run_date.isoformat(), user_id))
        conn.commit()
        context.job_queue.run_once(
            send_funnel_message,
            when=run_date,
            data={'chat_id': chat_id, 'user_id': user_id, 'text': msg["text"]}
        )
        logger.info(f"План сообщение {idx+1} для user_id {user_id}")
    conn.close()

async def send_funnel_message(context: CallbackContext):
    data = context.job.data
    chat_id = data["chat_id"]
    user_id = data["user_id"]
    text = data["text"]
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT consent_status FROM users WHERE user_id=?", (user_id,))
    status = c.fetchone()
    if status and status[0] == 'yes':
        await context.bot.send_message(chat_id=chat_id, text=text)
    conn.close()
