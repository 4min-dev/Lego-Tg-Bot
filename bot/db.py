import sqlite3
from bot.config import DB_FILE

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  start_date TEXT,
                  consent_status TEXT DEFAULT 'pending',
                  next_send TEXT,
                  source TEXT,
                  dialog TEXT DEFAULT '')''')
    conn.commit()
    conn.close()
