def get_scheduler(context):
    """Возвращает объект scheduler из контекста JobQueue"""
    return context.application.job_queue.scheduler
