import sqlite3
import logging
from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from bot.config import DB_FILE, ADMIN_IDS

logger = logging.getLogger(__name__)

async def stop(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    # Обновляем статус в БД
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE users SET consent_status = 'no', next_send = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Удаляем все запланированные задачи пользователя
    scheduler = context.job_queue.scheduler
    jobs = scheduler.get_jobs()
    user_jobs = [job for job in jobs if job.name and (job.name.startswith(f"funnel_{user_id}_") or job.name == f"reminder_{user_id}")]
    
    if user_jobs:
        for job in user_jobs:
            try:
                scheduler.remove_job(job.id)
                logger.info(f"Удалена задача для user_id {user_id}: {job.name}")
            except Exception as e:
                logger.error(f"Ошибка при удалении задачи для user_id {user_id}: {e}")
    else:
        logger.info(f"Для user_id {user_id} не найдено активных задач.")

    await update.message.reply_text("Вы отписаны от рассылки.")


def register(app):
    app.add_handler(CommandHandler("stop", stop))
