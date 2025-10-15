from telegram.ext import MessageHandler, filters, CallbackContext
from telegram import Update
from bot.config import ADMIN_IDS
from bot.utils.logger import logger
from bot.utils.media_storage import save_media_ids, load_media_ids

media_data = load_media_ids()
DESCRIPTION_IMAGE_FILE_ID = media_data.get("image")
VIDEO_FILE_ID = media_data.get("video")

async def handle_image(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    if update.message.photo:
        global DESCRIPTION_IMAGE_FILE_ID
        DESCRIPTION_IMAGE_FILE_ID = update.message.photo[-1].file_id
        save_media_ids(image_id=DESCRIPTION_IMAGE_FILE_ID)
        await update.message.reply_text(f"✅ Новое изображение сохранено: {DESCRIPTION_IMAGE_FILE_ID}")
        logger.info(f"Описание обновлено: {DESCRIPTION_IMAGE_FILE_ID}")

async def handle_video(update: Update, context: CallbackContext):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.message.reply_text("Доступ запрещён.")
    if update.message.video_note:
        global VIDEO_FILE_ID
        VIDEO_FILE_ID = update.message.video_note.file_id
        save_media_ids(video_id=VIDEO_FILE_ID)
        await update.message.reply_text(f"✅ Новое видео сохранено: {VIDEO_FILE_ID}")
        logger.info(f"Видео обновлено: {VIDEO_FILE_ID}")

def register(application):
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video))

__all__ = ['DESCRIPTION_IMAGE_FILE_ID', 'VIDEO_FILE_ID', 'load_media_ids']