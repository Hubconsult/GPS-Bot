import sqlite3

# Имя файла базы (создастся автоматически при первом запуске)
DB_PATH = "users.db"

# --- Инициализация базы ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        used_free INT DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

# --- Получить, сколько бесплатных сообщений уже использовал пользователь ---
def get_used_free(chat_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT used_free FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

# --- Увеличить счётчик использованных сообщений ---
def increment_used(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Если пользователя ещё нет в базе — создаём
    c.execute("INSERT OR IGNORE INTO users(chat_id, used_free) VALUES(?, 0)", (chat_id,))
    # Увеличиваем количество использованных сообщений
    c.execute("UPDATE users SET used_free = used_free + 1 WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
