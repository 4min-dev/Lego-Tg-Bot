import sqlite3
import pandas as pd
from telegram import Update
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

async def broadcast(update: Update, context: CallbackContext):
    """Рассылка сообщения всем, кто дал согласие"""
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

    if len(context.args) < 2:
        return await update.message.reply_text(
            "Использование: /funnel_add <секунды задержки> <текст сообщения>"
        )

    try:
        delay_seconds = int(context.args[0])
        text = ' '.join(context.args[1:])
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
    conn.commit()

    c.execute("SELECT user_id FROM users WHERE consent_status='yes'")
    users = c.fetchall()
    conn.close()

    for (user_id,) in users:
        chat_id = user_id 
        schedule_funnel_for_user(context, user_id, chat_id, test_mode=True)

    await update.message.reply_text(
        f"✅ Сообщение #{order_num} добавлено и запланировано для всех подписанных."
    )


async def funnel_edit(update: Update, context: CallbackContext):
    """Редактировать существующее сообщение"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    if len(context.args) < 2:
        return await update.message.reply_text("Использование: /funnel_edit <номер> <новый текст>")
    try:
        order_num = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("Ошибка: номер должен быть числом.")
    new_text = ' '.join(context.args[1:])

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE funnel_messages SET text=? WHERE order_num=?", (new_text, order_num))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✏️ Сообщение #{order_num} обновлено.")


async def funnel_delete(update: Update, context: CallbackContext):
    """Удалить сообщение из воронки"""
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
    c.execute("DELETE FROM funnel_messages WHERE order_num=?", (order_num,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑 Сообщение #{order_num} удалено.")

def register(application):
    application.add_handler(CommandHandler("export", export))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("funnel_list", funnel_list))
    application.add_handler(CommandHandler("funnel_add", funnel_add))
    application.add_handler(CommandHandler("funnel_edit", funnel_edit))
    application.add_handler(CommandHandler("funnel_delete", funnel_delete))
