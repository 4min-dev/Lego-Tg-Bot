import aiosqlite
import sqlite3
import datetime
import asyncio
from telegram.ext import CallbackContext
from bot.config import DB_FILE
from bot.texts import FUNNEL_MESSAGES, REMINDER_TEXT
from bot.utils.logger import logger

def initialize_funnel_messages():
    logger.info('Вызван initialize_funnel_messages')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS user_funnel_history (
            user_id INTEGER,
            funnel_id INTEGER,
            sent_at TEXT,
            scheduled_at TEXT,
            status TEXT,
            PRIMARY KEY(user_id, funnel_id)
        )
    ''')

    c.execute("PRAGMA table_info(user_funnel_history)")
    columns = [info[1] for info in c.fetchall()]
    if 'status' not in columns:
        c.execute("ALTER TABLE user_funnel_history ADD COLUMN status TEXT")
        logger.info("Добавлен столбец status в таблицу user_funnel_history")
    if 'scheduled_at' not in columns:
        c.execute("ALTER TABLE user_funnel_history ADD COLUMN scheduled_at TEXT")
        logger.info("Добавлен столбец scheduled_at в таблицу user_funnel_history")

    # Создаём таблицу funnel_messages, если не существует
    c.execute('''
        CREATE TABLE IF NOT EXISTS funnel_messages (
            order_num INTEGER PRIMARY KEY,
            delay_days INTEGER,
            text TEXT
        )
    ''')

    c.execute("SELECT order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC")
    existing_messages = c.fetchall()
    existing_orders = {row[0] for row in existing_messages}

    for idx, msg in enumerate(FUNNEL_MESSAGES, start=1):
        if idx not in existing_orders:
            c.execute(
                "INSERT INTO funnel_messages (order_num, delay_days, text) VALUES (?, ?, ?)",
                (idx, msg["delay_days"], msg["text"])
            )
            logger.info(f"Добавлено сообщение #{idx} в таблицу funnel_messages")

    conn.commit()
    logger.info("Добавлены дефолтные сообщения в автоворонку.")
    conn.close()

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

def start_funnel(context: CallbackContext, user_id: int, chat_id: int, test_mode=True):
    now = datetime.datetime.now()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC")
    messages = c.fetchall()

    c.execute("SELECT funnel_id FROM user_funnel_history WHERE user_id=? AND status IN ('pending', 'sent')", (user_id,))
    existing_ids = {row[0] for row in c.fetchall()}

    for order_num, delay_days, text in messages:
        if order_num in existing_ids:
            logger.info(f"Пропущено сообщение #{order_num} для user_id {user_id}: уже в истории")
            continue

        delay = delay_days if test_mode else delay_days * 24 * 60 * 60
        run_date = now + datetime.timedelta(seconds=delay)

        c.execute("UPDATE users SET next_send=? WHERE user_id=?", (run_date.isoformat(), user_id))

        context.job_queue.run_once(
            send_funnel_message,
            when=delay,
            data={'chat_id': chat_id, 'user_id': user_id, 'text': text, 'funnel_id': order_num}
        )

        # Помечаем сообщение как запланированное
        c.execute(
            "INSERT OR IGNORE INTO user_funnel_history(user_id, funnel_id, scheduled_at, status) VALUES (?, ?, ?, 'pending')",
            (user_id, order_num, now.isoformat())
        )

        logger.info(f"Запланировано сообщение #{order_num} для user_id {user_id} через {delay} {'секунд' if test_mode else 'дней'}")

    conn.commit()
    conn.close()

async def send_funnel_message(context: CallbackContext):
    data = context.job.data
    chat_id = data["chat_id"]
    user_id = data["user_id"]
    text = data["text"]
    funnel_id = data.get("funnel_id")

    def db_work():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT consent_status FROM users WHERE user_id=?", (user_id,))
        status = c.fetchone()

        already_sent = False
        if funnel_id:
            c.execute("SELECT status FROM user_funnel_history WHERE user_id=? AND funnel_id=?", (user_id, funnel_id))
            result = c.fetchone()
            if result:
                logger.info(f"Статус записи для user_id {user_id}, funnel_id {funnel_id}: {result[0]}")
                if result[0] == 'sent':
                    already_sent = True

        if status and status[0] == 'yes' and not already_sent:
            try:
                if funnel_id:
                    c.execute(
                        "INSERT OR REPLACE INTO user_funnel_history (user_id, funnel_id, sent_at, scheduled_at, status) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (user_id, funnel_id, datetime.datetime.now().isoformat(), None, 'sent')
                    )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка записи в БД для user {user_id}: {e}")
                conn.close()
                return False
        else:
            conn.close()
            return False, status

    send_allowed = await asyncio.get_event_loop().run_in_executor(None, db_work)
    if send_allowed is True:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            logger.info(f"Отправлено funnel сообщение пользователю {user_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке funnel сообщения пользователю {user_id}: {e}")
    else:
        logger.info(f"Пропущено сообщение для user_id {user_id}, статус = {send_allowed[1] if isinstance(send_allowed, tuple) else None}")

async def schedule_new_funnel_messages(context: CallbackContext, user_id: int, chat_id: int, test_mode=True):
    """Ставим в очередь только новые сообщения для пользователя"""
    async with aiosqlite.connect(DB_FILE) as db:
        existing_ids = set()
        async with db.execute(
            "SELECT funnel_id FROM user_funnel_history WHERE user_id=? AND status IN ('pending','sent')", 
            (user_id,)
        ) as cursor:
            async for row in cursor:
                existing_ids.add(row[0])

        messages = []
        async with db.execute(
            "SELECT order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC"
        ) as cursor:
            async for row in cursor:
                messages.append(row)

    now = datetime.datetime.now()

    for order_num, delay_days, text in messages:
        if order_num in existing_ids:
            continue

        delay_seconds = delay_days if test_mode else delay_days * 24 * 60 * 60

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO user_funnel_history(user_id, funnel_id, scheduled_at, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (user_id, order_num, now.isoformat())
            )
            await db.commit()

        context.job_queue.run_once(
            send_funnel_message,
            when=delay_seconds,
            data={'chat_id': chat_id, 'user_id': user_id, 'text': text, 'funnel_id': order_num}
        )

        send_time = now + datetime.timedelta(seconds=delay_seconds)
        logger.info(
            f"Запланировано новое сообщение #{order_num} для user_id {user_id} "
            f"через {delay_seconds} {'секунд' if test_mode else 'дней'} (отправка в {send_time})"
        )



def schedule_funnel_for_user(context: CallbackContext, user_id: int, chat_id: int, test_mode=True):
    """Ставим только новые сообщения автоворонки в очередь для одного пользователя"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT funnel_id FROM user_funnel_history WHERE user_id=? AND status IN ('pending', 'sent')", (user_id,))
    existing_ids = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC")
    messages = c.fetchall()
    conn.close()

    now = datetime.datetime.now()
    for order_num, delay_sec, text in messages:
        if order_num in existing_ids:
            continue
        
        delay = delay_sec if test_mode else delay_sec * 24 * 60 * 60
        context.job_queue.run_once(
            send_funnel_message,
            when=delay,
            data={'chat_id': chat_id, 'user_id': user_id, 'text': text, 'funnel_id': order_num}
        )
        logger.info(f"Запланировано сообщение #{order_num} для user_id {user_id} через {delay} {'секунд' if test_mode else 'дней'}")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO user_funnel_history(user_id, funnel_id, scheduled_at, status) VALUES (?, ?, ?, 'pending')",
            (user_id, order_num, now.isoformat())
        )
        conn.commit()
        conn.close()


def reschedule_funnel_for_all(context: CallbackContext, test_mode=True):
    """Обновляем очередь автоворонки для всех согласившихся пользователей"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, chat_id FROM users WHERE consent_status='yes'")
    users = c.fetchall()
    conn.close()

    for user_id, chat_id in users:
        schedule_new_funnel_messages(context, user_id, chat_id, test_mode=test_mode)
        logger.info(f"Перепланирована автоворонка для user_id {user_id}")