from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from telegram.ext import CallbackContext
from bot.utils.logger import logger

def job_listener(event):
    if event.code == EVENT_JOB_EXECUTED:
        logger.info(f"Задача {event.job_id} успешно выполнена")
    elif event.code == EVENT_JOB_ERROR:
        logger.error(f"Ошибка в задаче {event.job_id}: {event.exception}")

def get_scheduler(context: CallbackContext) -> AsyncIOScheduler:
    """Возвращает объект scheduler из контекста JobQueue и убеждается, что он запущен"""
    scheduler = context.application.job_queue.scheduler
    if not hasattr(scheduler, 'listener_added'):
        scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        scheduler.listener_added = True
        logger.info("Добавлен слушатель событий для APScheduler")
    if not scheduler.running:
        logger.info("Планировщик не активен, запускаем...")
        scheduler.start()
        logger.info("AsyncIOScheduler запущен")
    logger.info(f"Планировщик активен: {scheduler.running}")
    return scheduler