import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
DB_FILE = "data/users.db"
EXCEL_FILE = "data/users.xlsx"
TEXTS_FILE = os.path.join(os.path.dirname(__file__), 'texts.json')
