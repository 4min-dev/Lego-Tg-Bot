import sqlite3
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import CallbackQueryHandler, CallbackContext
from bot.texts import REMINDER_TEXT, CONSENT_YES_TEXT
from bot.handlers.funnel import start_funnel
from bot.config import DB_FILE
from bot.utils.logger import logger

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if data == 'consent_yes':
        c.execute("UPDATE users SET consent_status='yes' WHERE user_id=?", (user_id,))
        conn.commit()
        await query.edit_message_text(CONSENT_YES_TEXT)
        start_funnel(context, user_id, chat_id)

    elif data == 'consent_no':
        c.execute("UPDATE users SET consent_status='no' WHERE user_id=?", (user_id,))
        conn.commit()
        await query.edit_message_text("Хорошо, если передумаете, напишите /subscribe")

    conn.close()

def register(application):
    application.add_handler(CallbackQueryHandler(button_handler))
