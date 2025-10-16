import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder

from bot.config import TOKEN
from bot.utils.logger import logger

from bot.handlers import admin, consent, funnel, media, start, stop, subscribe, message
from bot.handlers.funnel import initialize_funnel_messages
from bot.db import init_db

load_dotenv()

if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

def main():
    init_db()
    initialize_funnel_messages()

    app = ApplicationBuilder().token(TOKEN).build()

    start.register(app)
    stop.register(app)
    admin.register(app)
    consent.register(app)
    media.register(app)
    subscribe.register(app)
    message.register(app)

    logger.info("Все хендлеры зарегистрированы. Бот запускается...")
    app.run_polling()

if __name__ == "__main__":
    main()
