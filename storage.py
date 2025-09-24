import json
import sqlite3
from typing import Any, Dict, List

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - fallback for environments without redis
    redis = None

from settings import is_owner

# Имя файла базы (создастся автоматически при первом запуске)
DB_PATH = "users.db"

# --- Redis storage for chat history -------------------------------------------------

_REDIS_TTL = 60 * 60 * 24 * 7  # 7 дней
_REDIS_CHAT_SET_KEY = "chat:ids"

_redis_client: "redis.Redis | None"
if redis is None:
    _redis_client = None
else:
    try:
        _redis_client = redis.Redis(
            host="localhost",
            port=6379,
            db=0,
            decode_responses=True,
        )
        _redis_client.ping()
    except redis.RedisError:
        _redis_client = None

# Локальный fallback, если Redis недоступен (офлайн режим)
_memory_history: Dict[int, List[Dict[str, Any]]] = {}


def _chat_key(chat_id: int) -> str:
    return f"chat:{chat_id}"


def save_history(chat_id: int, messages: List[Dict[str, Any]]) -> None:
    """Сохранить историю диалога в Redis (или локально, если Redis недоступен)."""

    serialized = json.dumps(messages, ensure_ascii=False)

    if _redis_client is not None:
        try:
            pipeline = _redis_client.pipeline()
            pipeline.setex(_chat_key(chat_id), _REDIS_TTL, serialized)
            pipeline.sadd(_REDIS_CHAT_SET_KEY, chat_id)
            pipeline.execute()
            return
        except redis.RedisError:
            pass

    # Fallback: храним историю локально в памяти
    _memory_history[chat_id] = json.loads(serialized)


def load_history(chat_id: int) -> List[Dict[str, Any]]:
    """Загрузить историю диалога."""

    if _redis_client is not None:
        try:
            data = _redis_client.get(_chat_key(chat_id))
        except redis.RedisError:
            data = None
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                # повреждённые данные очищаем
                clear_history(chat_id)

    history = _memory_history.get(chat_id, [])
    # Возвращаем копию, чтобы не модифицировать оригинал
    return json.loads(json.dumps(history)) if history else []


def clear_history(chat_id: int) -> None:
    """Удалить историю вручную."""

    if _redis_client is not None:
        try:
            _redis_client.delete(_chat_key(chat_id))
            _redis_client.srem(_REDIS_CHAT_SET_KEY, chat_id)
        except redis.RedisError:
            pass

    _memory_history.pop(chat_id, None)


def iter_history_chat_ids() -> List[int]:
    """Вернуть список chat_id, у которых есть сохранённая история."""

    if _redis_client is not None:
        try:
            members = _redis_client.smembers(_REDIS_CHAT_SET_KEY)
            return [int(member) for member in members]
        except redis.RedisError:
            pass
    return list(_memory_history.keys())

# --- Инициализация базы ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        used_free INT DEFAULT 0,
        has_tariff INTEGER DEFAULT 0
    )
    """)
    # Миграция: если колонка has_tariff отсутствует в старой таблице — добавляем
    c.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in c.fetchall()]
    if "has_tariff" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN has_tariff INTEGER DEFAULT 0")
    conn.commit()
    conn.close()

# --- Получить информацию об использовании и тарифе пользователя ---
def get_user_usage(chat_id: int) -> tuple[int, int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT used_free, has_tariff FROM users WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return 0, 0
    used_free = row[0] if row[0] is not None else 0
    has_tariff = row[1] if row[1] is not None else 0
    return used_free, has_tariff


# --- Получить, сколько бесплатных сообщений уже использовал пользователь ---
def get_used_free(chat_id: int) -> int:
    used_free, _ = get_user_usage(chat_id)
    return used_free

# --- Увеличить счётчик использованных сообщений ---
def increment_used(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Если пользователя ещё нет в базе — создаём
    c.execute(
        "INSERT OR IGNORE INTO users(chat_id, used_free, has_tariff) VALUES(?, 0, 0)",
        (chat_id,),
    )
    # Увеличиваем количество использованных сообщений
    c.execute("UPDATE users SET used_free = used_free + 1 WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

# ---- НИЖЕ ДОБАВИТЬ код для мультимедиа-лимитов ----
import datetime

def _month_key(d: datetime.date | None = None) -> str:
    d = d or datetime.date.today()
    return d.strftime("%Y-%m")  # например '2025-09'

def init_media_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Текущий баланс лимитов на месяц (осталось)
    c.execute("""
    CREATE TABLE IF NOT EXISTS media_balance (
        chat_id INTEGER,
        month TEXT,
        photos_left INT DEFAULT 0,
        docs_left INT DEFAULT 0,
        analysis_left INT DEFAULT 0,
        PRIMARY KEY (chat_id, month)
    )
    """)
    # Триальные разовые лимиты для неоформивших тариф
    c.execute("""
    CREATE TABLE IF NOT EXISTS media_trials (
        chat_id INTEGER PRIMARY KEY,
        photo_used INT DEFAULT 0,
        doc_used INT DEFAULT 0,
        analysis_used INT DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

# вызывать при старте приложения
init_media_tables()

def get_media_balance(chat_id: int) -> dict:
    """Вернёт текущий остаток лимитов за этот месяц (или пусто, если ещё не инициализировали)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    mk = _month_key()
    c.execute("SELECT photos_left, docs_left, analysis_left FROM media_balance WHERE chat_id=? AND month=?",
              (chat_id, mk))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"photos_left": None, "docs_left": None, "analysis_left": None}
    return {"photos_left": row[0], "docs_left": row[1], "analysis_left": row[2]}

def set_media_balance(chat_id: int, photos: int, docs: int, analysis: int):
    """Жёстко выставить баланс на текущий месяц (используется при активации тарифа/первом обращении)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    mk = _month_key()
    c.execute("""INSERT INTO media_balance(chat_id, month, photos_left, docs_left, analysis_left)
                 VALUES(?,?,?,?,?)
                 ON CONFLICT(chat_id, month) DO UPDATE SET
                 photos_left=excluded.photos_left,
                 docs_left=excluded.docs_left,
                 analysis_left=excluded.analysis_left
                 """, (chat_id, mk, photos, docs, analysis))
    conn.commit()
    conn.close()

def dec_media(chat_id: int, kind: str, amount: int = 1) -> bool:
    """Пробует списать лимит (photos/docs/analysis). Возвращает True при успехе."""
    if is_owner(chat_id):
        return True
    assert kind in ("photos", "docs", "analysis")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    mk = _month_key()
    col = {"photos":"photos_left", "docs":"docs_left", "analysis":"analysis_left"}[kind]
    # Прочитать текущий остаток
    c.execute(f"SELECT {col} FROM media_balance WHERE chat_id=? AND month=?", (chat_id, mk))
    row = c.fetchone()
    if not row or row[0] is None:
        conn.close()
        return False
    left = row[0]
    if left < amount:
        conn.close()
        return False
    # Списать
    c.execute(f"UPDATE media_balance SET {col} = {col} - ? WHERE chat_id=? AND month=?", (amount, chat_id, mk))
    conn.commit()
    conn.close()
    return True

def add_package(chat_id: int, kind: str, amount: int):
    """Добавить купленный пакет в остаток лимитов текущего месяца."""
    assert kind in ("photos", "docs", "analysis")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    mk = _month_key()
    col = {"photos":"photos_left", "docs":"docs_left", "analysis":"analysis_left"}[kind]
    # гарантируем строку
    c.execute("""INSERT OR IGNORE INTO media_balance(chat_id, month, photos_left, docs_left, analysis_left)
                 VALUES(?,?,0,0,0)""", (chat_id, mk))
    c.execute(f"UPDATE media_balance SET {col} = {col} + ? WHERE chat_id=? AND month=?", (amount, chat_id, mk))
    conn.commit()
    conn.close()

def get_or_init_month_balance(chat_id: int, defaults: dict):
    """Если нет строки на месяц — создаём по дефолтам (из тарифа)."""
    bal = get_media_balance(chat_id)
    if bal["photos_left"] is None:
        set_media_balance(chat_id, defaults.get("photos", 0), defaults.get("docs", 0), defaults.get("analysis", 0))
        return get_media_balance(chat_id)
    return bal

# Триал (по 1 штуке без тарифа)
def read_trials(chat_id: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT photo_used, doc_used, analysis_used FROM media_trials WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"photo_used": 0, "doc_used": 0, "analysis_used": 0}
    return {"photo_used": row[0], "doc_used": row[1], "analysis_used": row[2]}

def mark_trial_used(chat_id: int, kind: str):
    col = {"photos":"photo_used", "docs":"doc_used", "analysis":"analysis_used"}[kind]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO media_trials(chat_id) VALUES(?)", (chat_id,))
    c.execute(f"UPDATE media_trials SET {col}=1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()
