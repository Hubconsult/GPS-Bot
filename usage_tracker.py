"""Утилиты для учёта активности пользователей в SynteraGPT."""
from __future__ import annotations

import html
import json
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from storage import DB_PATH, r

_USAGE_USER_KEY_PREFIX = "usage:user:"
_USAGE_USER_SET_KEY = "usage:user_ids"
_USAGE_INIT_MARKER_KEY = "usage:initialized"

_SQLITE_READY = False


def _user_key(user_id: int) -> str:
    return f"{_USAGE_USER_KEY_PREFIX}{user_id}"


def _ensure_sqlite_ready() -> None:
    global _SQLITE_READY
    if _SQLITE_READY:
        return

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                total_requests INTEGER DEFAULT 0,
                text_requests INTEGER DEFAULT 0,
                image_generations INTEGER DEFAULT 0,
                doc_generations INTEGER DEFAULT 0,
                last_used_at INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
        _SQLITE_READY = True
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()


def init_usage_tracking() -> None:
    """Инициализировать учёт в Redis и выполнить миграцию из SQLite при необходимости."""

    if getattr(init_usage_tracking, "_initialized", False):
        return

    setattr(init_usage_tracking, "_initialized", True)

    try:
        _ensure_sqlite_ready()
    except Exception:
        pass

    try:
        r.ping()
    except Exception:  # pragma: no cover - Redis недоступен, используем in-memory
        return

    if r.get(_USAGE_INIT_MARKER_KEY):
        return

    migrated = False
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='usage_stats'"
        )
        if cursor.fetchone():
            cursor.execute(
                """
                SELECT user_id, username, total_requests, text_requests,
                       image_generations, doc_generations, last_used_at
                FROM usage_stats
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                user_id = int(row[0])
                data = {
                    "user_id": user_id,
                    "username": row[1] or "",
                    "total_requests": int(row[2] or 0),
                    "text_requests": int(row[3] or 0),
                    "image_generations": int(row[4] or 0),
                    "doc_generations": int(row[5] or 0),
                    "last_used_at": int(row[6] or 0),
                }
                r.set(_user_key(user_id), json.dumps(data, ensure_ascii=False))
                r.sadd(_USAGE_USER_SET_KEY, user_id)
            migrated = bool(rows)
    except Exception:  # pragma: no cover - ошибки миграции не критичны
        pass
    finally:
        if conn is not None:
            conn.close()

    r.set(
        _USAGE_INIT_MARKER_KEY,
        json.dumps({"migrated": migrated, "ts": int(time.time())}),
    )


def compose_display_name(
    *, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None
) -> str:
    """Сформировать наглядное представление пользователя."""

    if username:
        if username.startswith("@"):
            return username
        return f"@{username}"

    parts = [part for part in (first_name, last_name) if part]
    return " ".join(parts).strip()


def _resolve_category_increments(category: str) -> Tuple[int, int, int]:
    normalized = (category or "text").strip().lower()
    if normalized == "image":
        return 0, 1, 0
    if normalized in {"doc", "document", "documents", "file"}:
        return 0, 0, 1
    return 1, 0, 0


def _load_user_record(user_id: int) -> Optional[Dict[str, int | str]]:
    raw = r.get(_user_key(user_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "user_id": int(data.get("user_id") or user_id),
        "username": str(data.get("username") or ""),
        "total_requests": int(data.get("total_requests") or 0),
        "text_requests": int(data.get("text_requests") or 0),
        "image_generations": int(data.get("image_generations") or 0),
        "doc_generations": int(data.get("doc_generations") or 0),
        "last_used_at": int(data.get("last_used_at") or 0),
    }


def _save_user_record(data: Dict[str, int | str]) -> None:
    user_id = int(data["user_id"])
    r.set(_user_key(user_id), json.dumps(data, ensure_ascii=False))
    r.sadd(_USAGE_USER_SET_KEY, user_id)


def _write_sqlite_record(data: Dict[str, int | str]) -> None:
    if not data:
        return

    try:
        _ensure_sqlite_ready()
    except Exception:
        return

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usage_stats (
                user_id, username, total_requests, text_requests,
                image_generations, doc_generations, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                total_requests=excluded.total_requests,
                text_requests=excluded.text_requests,
                image_generations=excluded.image_generations,
                doc_generations=excluded.doc_generations,
                last_used_at=excluded.last_used_at
            """,
            (
                int(data.get("user_id", 0)),
                str(data.get("username") or ""),
                int(data.get("total_requests", 0)),
                int(data.get("text_requests", 0)),
                int(data.get("image_generations", 0)),
                int(data.get("doc_generations", 0)),
                int(data.get("last_used_at", 0)),
            ),
        )
        conn.commit()
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()


def _load_user_record_sqlite(user_id: int) -> Optional[Dict[str, int | str]]:
    try:
        _ensure_sqlite_ready()
    except Exception:
        return None

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, total_requests, text_requests,
                   image_generations, doc_generations, last_used_at
            FROM usage_stats
            WHERE user_id = ?
            """,
            (int(user_id),),
        )
        row = cursor.fetchone()
    except Exception:
        return None
    finally:
        if conn is not None:
            conn.close()

    if not row:
        return None

    return {
        "user_id": int(row[0]),
        "username": row[1] or "",
        "total_requests": int(row[2] or 0),
        "text_requests": int(row[3] or 0),
        "image_generations": int(row[4] or 0),
        "doc_generations": int(row[5] or 0),
        "last_used_at": int(row[6] or 0),
    }


def _load_all_sqlite() -> List[Dict[str, int | str]]:
    try:
        _ensure_sqlite_ready()
    except Exception:
        return []

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, username, total_requests, text_requests,
                   image_generations, doc_generations, last_used_at
            FROM usage_stats
            ORDER BY total_requests DESC, last_used_at DESC
            """
        )
        rows = cursor.fetchall()
    except Exception:
        return []
    finally:
        if conn is not None:
            conn.close()

    result: List[Dict[str, int | str]] = []
    for row in rows:
        result.append(
            {
                "user_id": int(row[0]),
                "username": row[1] or "",
                "total_requests": int(row[2] or 0),
                "text_requests": int(row[3] or 0),
                "image_generations": int(row[4] or 0),
                "doc_generations": int(row[5] or 0),
                "last_used_at": int(row[6] or 0),
            }
        )
    return result


def record_user_activity(
    user_id: int,
    *,
    category: str = "text",
    display_name: Optional[str] = None,
) -> None:
    """Сохранить факт использования бота конкретным пользователем."""

    if not user_id:
        return

    init_usage_tracking()

    now = int(time.time())
    text_inc, image_inc, doc_inc = _resolve_category_increments(category)
    data = _load_user_record(user_id) or {
        "user_id": int(user_id),
        "username": "",
        "total_requests": 0,
        "text_requests": 0,
        "image_generations": 0,
        "doc_generations": 0,
        "last_used_at": 0,
    }

    username = (display_name or "").strip()
    if username:
        data["username"] = username

    data["total_requests"] = int(data.get("total_requests", 0)) + 1
    data["text_requests"] = int(data.get("text_requests", 0)) + text_inc
    data["image_generations"] = int(data.get("image_generations", 0)) + image_inc
    data["doc_generations"] = int(data.get("doc_generations", 0)) + doc_inc
    data["last_used_at"] = now

    _save_user_record(data)
    _write_sqlite_record(data)


def get_top_users(limit: int = 10) -> List[Tuple[int, Optional[str], int, int, int, int, int]]:
    """Получить список самых активных пользователей."""

    init_usage_tracking()

    try:
        user_ids = r.smembers(_USAGE_USER_SET_KEY)
    except Exception:  # pragma: no cover - при сбое Redis вернём пустой список
        return []

    rows: List[Tuple[int, Optional[str], int, int, int, int, int]] = []
    for raw_id in user_ids:
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        record = _load_user_record(user_id)
        if not record:
            continue
        rows.append(
            (
                user_id,
                record.get("username") or None,
                int(record.get("total_requests", 0)),
                int(record.get("text_requests", 0)),
                int(record.get("image_generations", 0)),
                int(record.get("doc_generations", 0)),
                int(record.get("last_used_at", 0)),
            )
        )

    rows.sort(key=lambda item: (item[2], item[6]), reverse=True)
    if rows:
        return rows[:limit]

    fallback_records = _load_all_sqlite()
    if not fallback_records:
        return []

    for record in fallback_records:
        _save_user_record(record)

    formatted = [
        (
            int(record["user_id"]),
            record.get("username") or None,
            int(record.get("total_requests", 0)),
            int(record.get("text_requests", 0)),
            int(record.get("image_generations", 0)),
            int(record.get("doc_generations", 0)),
            int(record.get("last_used_at", 0)),
        )
        for record in fallback_records
    ]
    return formatted[:limit]


def get_user_stats(user_id: int) -> Optional[Dict[str, int | str]]:
    init_usage_tracking()
    record = _load_user_record(user_id)
    if record:
        return record

    fallback = _load_user_record_sqlite(user_id)
    if fallback:
        _save_user_record(fallback)
        return fallback
    return None


def _format_last_used(timestamp: int) -> str:
    if not timestamp:
        return "н/д"
    try:
        last_dt = datetime.fromtimestamp(timestamp)
    except Exception:
        return "н/д"
    return last_dt.strftime("%d.%m.%Y %H:%M")


def format_user_stats(user_id: int, display_hint: Optional[str] = None) -> str:
    data = get_user_stats(user_id)
    if not data:
        hint = html.escape(display_hint or "")
        tail = f"\nИмя/ник: {hint}" if hint else ""
        return f"Данных по пользователю <code>{user_id}</code> пока нет.{tail}"

    name = data.get("username") or display_hint or ""
    name = html.escape(name)
    lines = [
        "<b>Статистика пользователя</b>",
        f"ID: <code>{data['user_id']}</code>",
        f"Имя/ник: {name or 'н/д'}",
        f"Всего запросов: {data['total_requests']}",
        f"Текстовые ответы: {data['text_requests']}",
        f"Генерация изображений: {data['image_generations']}",
        f"Файлы и документы: {data['doc_generations']}",
        f"Последняя активность: {_format_last_used(int(data.get('last_used_at') or 0))}",
    ]
    return "\n".join(lines)


__all__ = [
    "compose_display_name",
    "format_usage_report",
    "format_user_stats",
    "get_top_users",
    "get_user_stats",
    "init_usage_tracking",
    "record_user_activity",
]


# --- Админские команды для владельца бота ---
from settings import bot, OWNER_ID
from telebot import types


def _owner_only(user_id: Optional[int]) -> bool:
    return user_id == OWNER_ID


def format_usage_report(limit: int = 20) -> str:
    """Сводка по активности пользователей."""
    try:
        ids = list(map(int, r.smembers(_USAGE_USER_SET_KEY)))
        records = []
        for uid in ids:
            data = _load_user_record(uid)
            if data:
                records.append(data)
        records.sort(key=lambda d: d.get("total_requests", 0), reverse=True)
    except Exception as e:
        return f"⚠️ Ошибка чтения статистики: {e}"

    if not records:
        return "📊 Пока нет данных об активности пользователей."

    lines = ["<b>📊 Топ активных пользователей</b>\n"]
    for d in records[:limit]:
        lines.append(
            f"<b>{d.get('username') or '—'}</b> "
            f"(ID: <code>{d['user_id']}</code>)\n"
            f"Всего: {d['total_requests']}, "
            f"Текст: {d['text_requests']}, "
            f"Фото: {d['image_generations']}, "
            f"Документы: {d['doc_generations']}"
        )
    return "\n\n".join(lines)


@bot.message_handler(commands=["top_users"])
def cmd_top_users(message):
    """Команда доступна только владельцу: показывает топ пользователей."""
    if not _owner_only(getattr(message.from_user, "id", None)):
        bot.reply_to(message, "⛔ Команда доступна только владельцу бота.")
        return

    try:
        report = format_usage_report()
    except Exception as e:  # pragma: no cover - запасная защита
        bot.send_message(message.chat.id, f"⚠️ Ошибка статистики: {e}")
        return

    bot.send_message(message.chat.id, report, parse_mode="HTML")


@bot.message_handler(commands=["user_stats"])
def cmd_user_stats(message):
    """Показывает статистику по конкретному ID, только для владельца."""
    if not _owner_only(getattr(message.from_user, "id", None)):
        bot.reply_to(message, "⛔ Команда доступна только владельцу бота.")
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "📎 Использование: /user_stats <user_id>")
        return

    try:
        uid = int(parts[1])
    except ValueError:
        bot.reply_to(message, "⚠️ Некорректный ID.")
        return

    data = _load_user_record(uid)
    if not data:
        bot.reply_to(message, "❌ Данных по пользователю нет.")
        return

    text = (
        f"<b>👤 Пользователь:</b> {data.get('username') or '—'}\n"
        f"<b>ID:</b> <code>{uid}</code>\n\n"
        f"Всего запросов: {data.get('total_requests', 0)}\n"
        f"Текстовых: {data.get('text_requests', 0)}\n"
        f"Изображений: {data.get('image_generations', 0)}\n"
        f"Документов: {data.get('doc_generations', 0)}\n\n"
        f"<b>Последняя активность:</b> "
        f"{datetime.fromtimestamp(data.get('last_used_at', 0)).strftime('%d.%m.%Y %H:%M:%S')}"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML")
