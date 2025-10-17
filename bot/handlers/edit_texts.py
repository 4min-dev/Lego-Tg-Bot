import json
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from bot.utils.logger import logger
from bot.config import TEXTS_FILE, DB_FILE
from bot.texts import load_texts, reload_texts
import bot.texts as texts

ADMIN_IDS = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS.split(",") if x.strip().isdigit()]

async def edit_texts(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id

    if user.id not in ADMIN_IDS:
        await context.bot.send_message(chat_id=chat_id, text="🚫 У вас нет доступа к этой команде.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1-е сообщение после start", callback_data='edit_WELCOME_TEXT')],
        [InlineKeyboardButton("2-е сообщение после start", callback_data='edit_SUPPORT_TEXT')],
        [InlineKeyboardButton("Заголовок подписки на рассылку", callback_data='edit_CONSENT_TEXT')],
         [InlineKeyboardButton("Сообщение после согласия на рассылку", callback_data='edit_CONSENT_YES_TEXT')],
        [InlineKeyboardButton("Напоминание", callback_data='edit_REMINDER_TEXT')],
        [InlineKeyboardButton("Некорректное сообщение", callback_data='edit_WRONG_MESSAGE_TEXT')],
    ])
    logger.info(f"Отправляем клавиатуру с кнопками: {[btn[0].callback_data for btn in keyboard.inline_keyboard]}")
    await context.bot.send_message(
        chat_id=chat_id,
        text="Выберите текст для редактирования:",
        reply_markup=keyboard
    )

async def handle_edit_selection(update: Update, context: CallbackContext) -> None:
    try:
        query = update.callback_query
        logger.info(f"Получен callback_query: data={query.data}, chat_id={query.message.chat_id if query.message else 'None'}")
        
        await query.answer()
        logger.info("Callback answered")

        chat_id = query.message.chat_id
        text_key = query.data.replace('edit_', '')
        logger.info(f"Обрабатываем text_key: {text_key}")

        context.user_data['editing_text_key'] = text_key
        logger.info(f"Сохранен editing_text_key: {text_key} для user_id={query.from_user.id}")

        if text_key == 'FUNNEL_MESSAGES':
            await query.message.reply_text(
                "Введите номер сообщения (0-3) для редактирования текста воронки или 'cancel' для отмены:"
            )
            logger.info("Отправлен запрос на ввод номера сообщения для FUNNEL_MESSAGES")
        else:
            await query.message.reply_text(
                f"Введите новый текст для {text_key} или 'cancel' для отмены:"
            )
            logger.info(f"Отправлен запрос на ввод текста для {text_key}")
    except Exception as e:
        logger.error(f"Ошибка в handle_edit_selection: {e}")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Произошла ошибка при обработке запроса.")

async def handle_text_input(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text
    user_id = update.effective_user.id
    text_key = context.user_data.get('editing_text_key')
    logger.info(f"handle_text_input: Получен текст '{text}' для text_key={text_key} от user_id={user_id}")

    if not text_key:
        logger.info("handle_text_input: Пропущено - не выбран текст для редактирования, отправляем WRONG_MESSAGE_TEXT")

        await update.message.reply_text(texts.WRONG_MESSAGE_TEXT)

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE users SET dialog = dialog || ? || '\n' WHERE user_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        return

    if text.lower() == 'cancel':
        logger.info("handle_text_input: Редактирование отменено")
        await context.bot.send_message(chat_id=chat_id, text="Редактирование отменено.")
        context.user_data.pop('editing_text_key', None)
        context.user_data.pop('editing_funnel_index', None)
        return

    texts_data = load_texts()
    logger.info(f"handle_text_input: Загружен texts.json для text_key={text_key}")
    if text_key == 'FUNNEL_MESSAGES':
        try:
            index = int(text)
            if 0 <= index < len(texts_data['FUNNEL_MESSAGES']):
                context.user_data['editing_funnel_index'] = index
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Введите новый текст для FUNNEL_MESSAGES[{index}] или 'cancel' для отмены:"
                )
                logger.info(f"handle_text_input: Запрошен текст для FUNNEL_MESSAGES[{index}]")
            else:
                await context.bot.send_message(chat_id=chat_id, text="Неверный номер сообщения.")
                logger.info("handle_text_input: Неверный номер сообщения")
        except ValueError:
            await context.bot.send_message(chat_id=chat_id, text="Введите число от 0 до 3 или 'cancel'.")
            logger.info("handle_text_input: Введено некорректное число")
    else:
        texts_data[text_key] = text
        try:
            with open(TEXTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(texts_data, f, ensure_ascii=False, indent=2)
            reload_texts()
            logger.info("reload_texts вызван после обновления texts.json")
            await context.bot.send_message(chat_id=chat_id, text=f"Текст {text_key} обновлен!")
            logger.info(f"handle_text_input: Текст {text_key} обновлен")
        except Exception as e:
            logger.error(f"handle_text_input: Ошибка при записи в texts.json: {e}")
            await context.bot.send_message(chat_id=chat_id, text="Ошибка при сохранении текста.")
        context.user_data.pop('editing_text_key', None)
        context.user_data.pop('editing_funnel_index', None)

def register(application):
    application.add_handler(CommandHandler("edit_texts", edit_texts))
    application.add_handler(CallbackQueryHandler(handle_edit_selection, pattern='^edit_'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))