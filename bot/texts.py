import json
import os
from bot.utils.logger import logger

TEXTS_FILE = os.path.join(os.path.dirname(__file__), 'texts.json')

def load_texts():
    logger.info(f"Загрузка texts.json из {TEXTS_FILE}")
    with open(TEXTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

texts_data = load_texts()
WELCOME_TEXT = texts_data['WELCOME_TEXT']
SUPPORT_TEXT = texts_data['SUPPORT_TEXT']
CONSENT_TEXT = texts_data['CONSENT_TEXT']
REMINDER_TEXT = texts_data['REMINDER_TEXT']
CONSENT_YES_TEXT = texts_data['CONSENT_YES_TEXT']
WRONG_MESSAGE_TEXT = texts_data['WRONG_MESSAGE_TEXT']
FUNNEL_MESSAGES = texts_data['FUNNEL_MESSAGES']

def reload_texts():
    """Обновляет глобальные переменные после изменения texts.json"""
    global WELCOME_TEXT, SUPPORT_TEXT, CONSENT_TEXT, REMINDER_TEXT, CONSENT_YES_TEXT, WRONG_MESSAGE_TEXT, FUNNEL_MESSAGES
    texts_data = load_texts()  # Используем texts_data вместо texts
    WELCOME_TEXT = texts_data['WELCOME_TEXT']
    SUPPORT_TEXT = texts_data['SUPPORT_TEXT']
    CONSENT_TEXT = texts_data['CONSENT_TEXT']
    REMINDER_TEXT = texts_data['REMINDER_TEXT']
    CONSENT_YES_TEXT = texts_data['CONSENT_YES_TEXT']
    WRONG_MESSAGE_TEXT = texts_data['WRONG_MESSAGE_TEXT']
    FUNNEL_MESSAGES = texts_data['FUNNEL_MESSAGES']
    logger.info("reload_texts: Глобальные переменные обновлены")