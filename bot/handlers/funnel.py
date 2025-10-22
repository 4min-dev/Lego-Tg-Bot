import aiosqlite
import sqlite3
import datetime
import asyncio
from telegram.ext import CallbackContext
from bot.config import DB_FILE
from bot.texts import FUNNEL_MESSAGES
import bot.texts as texts
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

    c.execute('''
        CREATE TABLE IF NOT EXISTS funnel_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_num INTEGER,
            delay_days INTEGER,
            text TEXT
        )
    ''')

    c.execute("SELECT id, order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC")
    existing_messages = c.fetchall()
    existing_orders = {row[1] for row in existing_messages}

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

async def send_reminder(context: CallbackContext, chat_id: int = None, user_id: int = None):
    # Если параметры переданы через context.job.data (для job_queue)
    if chat_id is None or user_id is None:
        data = context.job.data
        chat_id = data['chat_id']
        user_id = data['user_id']
    
    logger.info(f"Вызвана функция send_reminder для user_id {user_id}, chat_id {chat_id}")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("SELECT consent_status FROM users WHERE user_id=?", (user_id,))
        status = c.fetchone()
        logger.info(f"Статус согласия для user_id {user_id}: {status[0] if status else 'не найден'}")
        if status and status[0] == 'pending':
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, хочу быть в курсе!", callback_data='consent_yes')],
                [InlineKeyboardButton("❌ Пока нет", callback_data='consent_no')]
            ])
            try:
                await context.bot.send_message(chat_id=chat_id, text=texts.REMINDER_TEXT, reply_markup=keyboard)
                logger.info(f"Напоминание успешно отправлено для user_id {user_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке напоминания для user_id {user_id}: {e}")
        else:
            logger.info(f"Напоминание не отправлено для user_id {user_id}: consent_status не 'pending' (текущий статус: {status[0] if status else 'не найден'})")
    except Exception as e:
        logger.error(f"Ошибка при доступе к базе данных для user_id {user_id}: {e}")
    finally:
        conn.close()

def start_funnel(context: CallbackContext, user_id: int, chat_id: int, test_mode=True):
    now = datetime.datetime.now()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT id, order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC")
    messages = c.fetchall()

    c.execute("SELECT funnel_id FROM user_funnel_history WHERE user_id=? AND status IN ('pending', 'sent')", (user_id,))
    existing_ids = {row[0] for row in c.fetchall()}

    earliest_send_time = None

    for funnel_id, order_num, delay_days, text in messages:
        if funnel_id in existing_ids:
            logger.info(f"Пропущено сообщение #{order_num} для user_id {user_id}: уже в истории")
            continue

        delay = delay_days * 24 * 60 * 60 
        run_date = now + datetime.timedelta(seconds=delay)

        if earliest_send_time is None or run_date < earliest_send_time:
            earliest_send_time = run_date

        context.job_queue.run_once(
            send_funnel_message,
            when=delay,
            data={'chat_id': chat_id, 'user_id': user_id, 'text': text, 'funnel_id': funnel_id}
        )

        c.execute(
            "INSERT OR IGNORE INTO user_funnel_history(user_id, funnel_id, scheduled_at, status) VALUES (?, ?, ?, 'pending')",
            (user_id, funnel_id, now.isoformat())
        )

        logger.info(f"Запланировано сообщение #{order_num} для user_id {user_id} через {delay_days} дней")

    if earliest_send_time:
        c.execute("UPDATE users SET next_send=? WHERE user_id=?", (earliest_send_time.isoformat(), user_id))

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
                    
                c.execute(
                    "SELECT scheduled_at FROM user_funnel_history WHERE user_id=? AND status='pending' ORDER BY scheduled_at ASC LIMIT 1",
                    (user_id,)
                )
                next_scheduled = c.fetchone()
                if next_scheduled:
                    c.execute(
                        "UPDATE users SET next_send=? WHERE user_id=?",
                        (next_scheduled[0], user_id)
                    )
                else:
                    c.execute("UPDATE users SET next_send=NULL WHERE user_id=?", (user_id,))
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
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
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
            "SELECT id, order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC"
        ) as cursor:
            async for row in cursor:
                messages.append(row)

    now = datetime.datetime.now()
    earliest_send_time = None 

    for funnel_id, order_num, delay_days, text in messages:
        if funnel_id in existing_ids:
            continue

        delay_seconds = delay_days * 24 * 60 * 60 
        send_time = now + datetime.timedelta(seconds=delay_seconds)

        if earliest_send_time is None or send_time < earliest_send_time:
            earliest_send_time = send_time

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO user_funnel_history(user_id, funnel_id, scheduled_at, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (user_id, funnel_id, now.isoformat())
            )
            await db.commit()

        context.job_queue.run_once(
            send_funnel_message,
            when=delay_seconds,
            data={'chat_id': chat_id, 'user_id': user_id, 'text': text, 'funnel_id': funnel_id}
        )

        logger.info(
            f"Запланировано новое сообщение #{order_num} (ID: {funnel_id}) для user_id {user_id} "
            f"через {delay_days} дней (отправка в {send_time})"
        )

    if earliest_send_time:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE users SET next_send=? WHERE user_id=?",
                (earliest_send_time.isoformat(), user_id)
            )
            await db.commit()



def schedule_funnel_for_user(context: CallbackContext, user_id: int, chat_id: int, test_mode=True):
    """Ставим только новые сообщения автоворонки в очередь для одного пользователя"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute(
        "SELECT funnel_id FROM user_funnel_history WHERE user_id=? AND status IN ('pending', 'sent')",
        (user_id,)
    )
    existing_ids = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT id, order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC")
    messages = c.fetchall()

    now = datetime.datetime.now()
    scheduled_any = False
    earliest_send_time = None

    for funnel_id, order_num, delay_days, text in messages:
        if funnel_id in existing_ids:
            continue

        delay = delay_days * 24 * 60 * 60 
        send_time = now + datetime.timedelta(seconds=delay)

        if earliest_send_time is None or send_time < earliest_send_time:
            earliest_send_time = send_time

        async def send_async(context: CallbackContext):
            await send_funnel_message(context)

        context.job_queue.run_once(
            send_async,
            when=delay,
            data={'chat_id': chat_id, 'user_id': user_id, 'text': text, 'funnel_id': funnel_id}
        )

        c.execute(
            """
            INSERT OR IGNORE INTO user_funnel_history(user_id, funnel_id, scheduled_at, status)
            VALUES (?, ?, ?, 'pending')
            """,
            (user_id, funnel_id, now.isoformat())
        )

        scheduled_any = True
        logger.info(
            f"Запланировано новое сообщение #{order_num} (ID: {funnel_id}) для user_id {user_id} через {delay_days} дней (в {send_time})"
        )

    if earliest_send_time:
        c.execute(
            "UPDATE users SET next_send=? WHERE user_id=?",
            (earliest_send_time.isoformat(), user_id)
        )

    conn.commit()
    conn.close()

    if not scheduled_any:
        logger.info(f"Для user_id {user_id} нет новых сообщений для планирования.")

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