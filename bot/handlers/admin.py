import sqlite3
import pandas as pd
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from bot.config import ADMIN_IDS, DB_FILE, EXCEL_FILE
from bot.texts import FUNNEL_MESSAGES
from bot.utils.logger import logger

async def export(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM users", conn)
    conn.close()
    df.to_excel(EXCEL_FILE, index=False)
    await update.message.reply_text(f"Данные сохранены в {EXCEL_FILE}")

async def broadcast(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    text = ' '.join(context.args)
    if not text:
        return await update.message.reply_text("Использование: /broadcast <текст>")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE consent_status='yes'")
    users = c.fetchall()
    conn.close()
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            logger.error(f"Ошибка при отправке {uid}: {e}")

def register(application):
    application.add_handler(CommandHandler("export", export))
    application.add_handler(CommandHandler("broadcast", broadcast))
