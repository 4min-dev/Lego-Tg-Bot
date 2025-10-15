import json
import os

CONFIG_PATH = "bot/media_config.json"

def save_media_ids(image_id=None, video_id=None):
    """Сохраняет file_id в JSON"""
    data = load_media_ids()
    if image_id:
        data["image"] = image_id
    if video_id:
        data["video"] = video_id
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f)

def load_media_ids():
    """Загружает сохранённые file_id"""
    if not os.path.exists(CONFIG_PATH):
        return {"image": None, "video": None}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)
