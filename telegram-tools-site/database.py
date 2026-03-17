import sqlite3

DB_PATH = "requests.db"


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)


conn = get_connection()
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS requests (
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT,
bot TEXT,
comment TEXT,
status TEXT DEFAULT 'new',
developer TEXT DEFAULT ''
)
""")

conn.commit()
