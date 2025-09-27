import json
import sqlite3
import threading
import time
from datetime import date
from typing import Any, Dict, List, Set

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - fallback for environments without redis
    redis = None

from settings import OWNER_ID, bot, is_owner

TTL = 60 * 60 * 24 * 7  # 7 дней
_REDIS_CHAT_SET_KEY = "chat:ids"
_last_alert_date: date | None = None
_last_status_ok = True


def _create_redis_client() -> "redis.Redis | None":
    if redis is None:
        return None
    try:
        client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
        client.ping()
        return client
    except redis.RedisError:
        return None


class InMemoryRedis:
    """Простейшая in-memory реализация минимального набора команд Redis."""

    def __init__(self) -> None:
        self._store: Dict[str, tuple[str, float | None]] = {}
        self._sets: Dict[str, Set[str]] = {}

    def _purge_if_expired(self, key: str) -> None:
        value = self._store.get(key)
        if not value:
            return
        _, expires_at = value
        if expires_at is not None and expires_at < time.time():
            self._store.pop(key, None)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self._store[key] = (value, time.time() + ttl)
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        expires_at = time.time() + ex if ex else None
        self._store[key] = (value, expires_at)
        return True

    def get(self, key: str) -> str | None:
        self._purge_if_expired(key)
        entry = self._store.get(key)
        if not entry:
            return None
        return entry[0]

    def delete(self, key: str) -> int:
        existed = key in self._store
        self._store.pop(key, None)
        return int(existed)

    def sadd(self, key: str, member: int) -> int:
        members = self._sets.setdefault(key, set())
        before = len(members)
        members.add(str(member))
        return int(len(members) > before)

    def smembers(self, key: str) -> Set[str]:
        return set(self._sets.get(key, set()))

    def srem(self, key: str, member: int) -> int:
        members = self._sets.get(key)
        if not members:
            return 0
        removed = str(member) in members
        members.discard(str(member))
        if not members:
            self._sets.pop(key, None)
        return int(removed)

    def ping(self) -> bool:
        return True

    def pipeline(self):  # pragma: no cover - совместимость с redis
        return self

    def execute(self):  # pragma: no cover
        return True


class SafeRedis:
    """Обёртка, которая прозрачно переключается на in-memory при ошибках."""

    def __init__(self, client: "redis.Redis | None") -> None:
        self._client = client
        self._memory = InMemoryRedis()

    @property
    def is_real(self) -> bool:
        return self._client is not None

    @property
    def client(self) -> "redis.Redis | None":
        return self._client

    @client.setter
    def client(self, value: "redis.Redis | None") -> None:
        self._client = value

    def _execute(self, command: str, *args, **kwargs):
        global _last_status_ok
        if self._client is not None:
            try:
                method = getattr(self._client, command)
                return method(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - хотим поймать любые сбои клиента
                _last_status_ok = False
                notify_owner(f"Redis command '{command}' failed: {exc}")
                self._client = None
        memory_method = getattr(self._memory, command)
        return memory_method(*args, **kwargs)

    def setex(self, *args, **kwargs):
        return self._execute("setex", *args, **kwargs)

    def set(self, *args, **kwargs):
        return self._execute("set", *args, **kwargs)

    def get(self, *args, **kwargs):
        return self._execute("get", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._execute("delete", *args, **kwargs)

    def sadd(self, *args, **kwargs):
        return self._execute("sadd", *args, **kwargs)

    def smembers(self, *args, **kwargs):
        return self._execute("smembers", *args, **kwargs)

    def srem(self, *args, **kwargs):
        return self._execute("srem", *args, **kwargs)

    def ping(self, *args, **kwargs):
        return self._execute("ping", *args, **kwargs)

    def pipeline(self, *args, **kwargs):  # pragma: no cover - совместимость
        return self._execute("pipeline", *args, **kwargs)

    def execute(self, *args, **kwargs):  # pragma: no cover
        return self._execute("execute", *args, **kwargs)


r = SafeRedis(_create_redis_client())

# Имя файла базы (создастся автоматически при первом запуске)
DB_PATH = "users.db"

# Локальный fallback, если Redis недоступен (офлайн режим)
_memory_history: Dict[int, List[Dict[str, Any]]] = {}

def notify_owner(msg: str) -> None:
    """Уведомить владельца о проблеме с Redis (не чаще одного раза в день)."""

    global _last_alert_date
    today = date.today()
    if _last_alert_date == today:
        return
    try:
        bot.send_message(OWNER_ID, f"⚠️ Redis alert: {msg}")
        _last_alert_date = today
    except Exception:  # pragma: no cover - в офлайн среде уведомление не доставится
        pass


def notify_restored() -> None:
    """Уведомить владельца, что Redis снова доступен."""

    global _last_alert_date
    try:
        bot.send_message(OWNER_ID, "✅ Redis restored and working fine again")
        _last_alert_date = None
    except Exception:  # pragma: no cover - офлайн среда
        pass


def redis_health_check() -> None:
    """Фоновая проверка доступности Redis и попытка переподключения."""

    global _last_status_ok
    while True:
        if redis is None:
            time.sleep(86400)
            continue

        if not r.is_real:
            client = _create_redis_client()
            if client is None:
                _last_status_ok = False
                notify_owner("Redis reconnect attempt failed")
                time.sleep(86400)
                continue
            r.client = client

        try:
            pong = r.ping()
        except Exception as exc:  # noqa: BLE001
            _last_status_ok = False
            notify_owner(f"Redis health-check failed: {exc}")
            r.client = None
            time.sleep(86400)
            continue

        if pong:
            if not _last_status_ok:
                notify_restored()
            _last_status_ok = True
        else:
            _last_status_ok = False
            notify_owner("Redis ping failed (no PONG)")
            r.client = None

        time.sleep(86400)


threading.Thread(target=redis_health_check, daemon=True).start()


def _chat_key(chat_id: int) -> str:
    return f"chat:{chat_id}"


def save_history(chat_id: int, messages: List[Dict[str, Any]]) -> None:
    """Сохранить историю диалога в Redis (или локально, если Redis недоступен)."""

    serialized = json.dumps(messages, ensure_ascii=False)

    try:
        r.setex(_chat_key(chat_id), TTL, serialized)
        r.sadd(_REDIS_CHAT_SET_KEY, chat_id)
    except Exception:  # pragma: no cover - fallback на память
        notify_owner("save_history failed (unexpected error)")

    # Храним локально, чтобы не потерять при офлайн-режиме
    _memory_history[chat_id] = json.loads(serialized)


def load_history(chat_id: int) -> List[Dict[str, Any]]:
    """Загрузить историю диалога."""

    data = None
    try:
        data = r.get(_chat_key(chat_id))
    except Exception:  # pragma: no cover
        notify_owner("load_history failed (unexpected error)")

    if data:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            clear_history(chat_id)

    history = _memory_history.get(chat_id, [])
    # Возвращаем копию, чтобы не модифицировать оригинал
    return json.loads(json.dumps(history)) if history else []


def clear_history(chat_id: int) -> None:
    """Удалить историю вручную."""

    try:
        r.delete(_chat_key(chat_id))
        r.srem(_REDIS_CHAT_SET_KEY, chat_id)
    except Exception:  # pragma: no cover
        notify_owner("clear_history failed (unexpected error)")

    _memory_history.pop(chat_id, None)


def iter_history_chat_ids() -> List[int]:
    """Вернуть список chat_id, у которых есть сохранённая история."""

    chat_ids = set(_memory_history.keys())
    try:
        members = r.smembers(_REDIS_CHAT_SET_KEY)
        chat_ids.update(int(member) for member in members)
    except Exception:  # pragma: no cover
        notify_owner("iter_history_chat_ids failed (unexpected error)")
    return list(chat_ids)

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


def reset_used_free(chat_id: int) -> None:
    """Сбросить счётчик бесплатных сообщений пользователя."""

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users(chat_id, used_free, has_tariff) VALUES(?, 0, 0)",
        (chat_id,),
    )
    c.execute("UPDATE users SET used_free = 0 WHERE chat_id = ?", (chat_id,))
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
