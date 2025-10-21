import sqlite3
import aiosqlite
import asyncio
import pandas as pd
from io import BytesIO
from telegram import Update, InputFile
from telegram.ext import CommandHandler, CallbackContext
from bot.config import ADMIN_IDS, DB_FILE, EXCEL_FILE
from bot.utils.logger import logger
from bot.handlers.funnel import schedule_funnel_for_user

async def export(update: Update, context: CallbackContext):
    """Выгрузка данных пользователей в Excel и отправка в Telegram"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")

    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM users", conn)
    conn.close()

    # сохраняем Excel в память
    excel_buffer = BytesIO()
    df.to_excel(excel_buffer, index=False)
    excel_buffer.seek(0)

    # отправляем в Telegram
    await update.message.reply_document(
        document=InputFile(excel_buffer, filename="users_export.xlsx"),
        caption="📊 Вот актуальные данные пользователей"
    )

    logger.info(f"Администратор {update.effective_user.id} запросил экспорт данных.")

async def funnel_preview(update: Update, context: CallbackContext):
    """Отправляет все сообщения автоворонки по очереди администратору без задержки"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")

    async with aiosqlite.connect(DB_FILE) as conn:
        async with conn.execute(
            "SELECT order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC"
        ) as cursor:
            messages = await cursor.fetchall()

    if not messages:
        return await update.message.reply_text("Сообщения автоворонки отсутствуют.")

    await update.message.reply_text("📬 Начинаю предпросмотр сообщений автоворонки...")
    logger.info(f"Администратор {update.effective_user.id} запросил предпросмотр автоворонки")

    for order_num, delay_days, text in messages:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"<b>Сообщение #{order_num}</b> (задержка: {delay_days} сек.)\n{text}",
                parse_mode='HTML'
            )
            logger.info(f"Отправлено сообщение #{order_num} администратору {update.effective_user.id}")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения #{order_num} администратору {update.effective_user.id}: {e}")
            await update.message.reply_text(f"Ошибка при отправке сообщения #{order_num}: {e}")
            break

    await update.message.reply_text("✅ Предпросмотр автоворонки завершён.")

async def broadcast(update: Update, context: CallbackContext):
    """Рассылка сообщения всем, кто дал согласие, с поддержкой HTML-форматирования"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")

    if len(context.args) < 1:
        return await update.message.reply_text("Использование: /broadcast <текст>")

    text = update.message.text_html[len("/broadcast "):]
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE consent_status='yes'")
    users = c.fetchall()
    conn.close()

    logger.info(f"Рассылка сообщения для {len(users)} пользователей: {text}")
    
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode='HTML')
            logger.info(f"Сообщение отправлено пользователю {uid}")
        except Exception as e:
            logger.error(f"Ошибка при отправке пользователю {uid}: {e}")

    await update.message.reply_text(f"📢 Рассылка выполнена для {len(users)} пользователей.")

async def funnel_list(update: Update, context: CallbackContext):
    """Показать все сообщения автоворонки"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, order_num, delay_days, text FROM funnel_messages ORDER BY order_num ASC")
    rows = c.fetchall()
    conn.close()

    if not rows:
        return await update.message.reply_text("Сообщения автоворонки отсутствуют.")

    text = "📬 <b>Список сообщений автоворонки:</b>\n\n"
    for r in rows:
        text += f"<b>#{r[1]}</b> (через {r[2]} сек.)\n{r[3][:200]}{'...' if len(r[3]) > 200 else ''}\n\n"
    await update.message.reply_html(text)


async def funnel_add(update: Update, context: CallbackContext):
    """Добавить новое сообщение в автоворонку и поставить в очередь всем подписанным"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")

    if len(context.args) < 1:
        return await update.message.reply_text(
            "Использование: /funnel_add <секунды задержки> <текст сообщения>"
        )

    try:
        delay_seconds = int(context.args[0])
        text = update.message.text_html[len(f"/funnel_add {context.args[0]} "):]
    except ValueError:
        return await update.message.reply_text("Ошибка: задержка должна быть числом.")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT MAX(order_num) FROM funnel_messages")
    max_order = c.fetchone()[0] or 0
    order_num = max_order + 1

    c.execute(
        "INSERT INTO funnel_messages (order_num, delay_days, text) VALUES (?, ?, ?)",
        (order_num, delay_seconds, text),
    )
    new_id = c.lastrowid 
    conn.commit()

    c.execute("SELECT user_id FROM users WHERE consent_status='yes'")
    users = c.fetchall()
    conn.close()

    for (user_id,) in users:
        schedule_funnel_for_user(context, user_id, user_id, test_mode=True)

    await update.message.reply_text(
        f"✅ Сообщение #{order_num} (ID: {new_id}) добавлено и запланировано для всех подписанных."
    )

async def funnel_edit(update: Update, context: CallbackContext):
    """Редактировать существующее сообщение"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    if len(context.args) < 1:
        return await update.message.reply_text("Использование: /funnel_edit <номер> <новый текст>")
    try:
        order_num = int(context.args[0])
        new_text = update.message.text_html[len(f"/funnel_edit {context.args[0]} "):]
    except ValueError:
        return await update.message.reply_text("Ошибка: номер должен быть числом.")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE funnel_messages SET text=? WHERE order_num=?", (new_text, order_num))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✏️ Сообщение #{order_num} обновлено.")

async def funnel_delete(update: Update, context: CallbackContext):
    """Удалить сообщение из воронки и связанные записи из истории"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    if not context.args:
        return await update.message.reply_text("Использование: /funnel_delete <номер>")
    try:
        order_num = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("Ошибка: номер должен быть числом.")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT id FROM funnel_messages WHERE order_num=?", (order_num,))
    result = c.fetchone()
    if not result:
        conn.close()
        return await update.message.reply_text(f"Сообщение #{order_num} не найдено.")

    funnel_id = result[0]


    c.execute("DELETE FROM user_funnel_history WHERE funnel_id=?", (funnel_id,))

    c.execute("DELETE FROM funnel_messages WHERE order_num=?", (order_num,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🗑 Сообщение #{order_num} удалено, связанные записи очищены.")

def register(application):
    application.add_handler(CommandHandler("export", export))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("funnel_preview", funnel_preview))
    application.add_handler(CommandHandler("funnel_list", funnel_list))
    application.add_handler(CommandHandler("funnel_add", funnel_add))
    application.add_handler(CommandHandler("funnel_edit", funnel_edit))
    application.add_handler(CommandHandler("funnel_delete", funnel_delete))
