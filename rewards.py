# -*- coding: utf-8 -*-
"""Reward catalog and helper for delivering starter gifts."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from settings import bot

ASSETS_DIR = Path(__file__).resolve().parent


# === СОЗВУЧИЕ (иконки) ===
ICON_REWARDS = [
    {"id": 1, "title": "Солнце", "file": "Солнце.png"},
    {"id": 2, "title": "Замок", "file": "Замок.png"},
    {"id": 3, "title": "Дракон", "file": "Дракон.png"},
    {"id": 4, "title": "Росток", "file": "Росток.png"},
    {"id": 5, "title": "Шар", "file": "Шар.png"},
    {"id": 6, "title": "Сова", "file": "Сова.png"},
    {"id": 7, "title": "Маска", "file": "Маска.png"},
    {"id": 8, "title": "Феникс", "file": "Феникс.png"},
    {"id": 9, "title": "Кролик", "file": "Кролик.png"},
]


# === ОТРАЖЕНИЕ (аватарки) ===
AVATAR_REWARDS = [
    {"id": 10, "title": "Волна", "file": "Волна (avatar).png"},
    {"id": 11, "title": "Кролик", "file": "Кролик (avatar).png"},
    {"id": 12, "title": "Росток", "file": "Росток (avatar).png"},
    {"id": 13, "title": "Шар", "file": "Шар (avatar).png"},
    {"id": 14, "title": "Сова", "file": "Сова (avatar).png"},
    {"id": 15, "title": "Замок", "file": "Замок (avatar).png"},
    {"id": 16, "title": "Маска", "file": "Маска (avatar).png"},
    {"id": 17, "title": "Феникс", "file": "Феникс (avatar).png"},
    {"id": 18, "title": "Солнце", "file": "Солнце (avatar).png"},
]


# === ПУТЕШЕСТВИЕ (карточки историй) ===
CARD_REWARDS = [
    {"id": 19, "title": "Искра во тьме", "file": "Искра во тьме.png"},
    {"id": 20, "title": "Башня ветров", "file": "Башня ветров.png"},
    {"id": 21, "title": "Мир песков", "file": "Мир песков.png"},
    {"id": 22, "title": "Храм времени", "file": "Храм времени.png"},
    {"id": 23, "title": "Остров тайн", "file": "Остров тайн.png"},
    {"id": 24, "title": "Лес теней", "file": "Лес теней.png"},
    {"id": 25, "title": "Мост забытых", "file": "Мост забытых.png"},
    {"id": 26, "title": "Врата начала", "file": "Врата начала.png"},
    {"id": 27, "title": "Лунный лес", "file": "Лунный лес.png"},
    {"id": 28, "title": "Город масок", "file": "Город масок.png"},
    {"id": 29, "title": "Озеро зеркал", "file": "Озеро зеркал.png"},
]


# === ПУТЕШЕСТВИЕ (фоны) ===
BACKGROUND_REWARDS = [
    {"id": 30, "title": "Кристаллический рассвет", "file": "Кристаллический рассвет.png"},
    {"id": 31, "title": "Лесное свечение", "file": "Лесное свечение.png"},
    {"id": 32, "title": "Огненный закат", "file": "Огненный закат.png"},
]


def _resolve_path(file_name: str | None) -> Path | None:
    if not file_name:
        return None
    candidate = ASSETS_DIR / file_name
    if candidate.exists():
        return candidate
    return None


def send_reward(chat_id: int, reward: Dict) -> Dict:
    """Send the reward to the user and return metadata."""

    title = reward.get("title", "Награда")
    file_name = reward.get("file")
    file_path = _resolve_path(file_name)

    if file_path is not None:
        with file_path.open("rb") as fh:
            bot.send_photo(chat_id, fh, caption=f"🏅 {title}")
    else:
        bot.send_message(chat_id, f"🏅 {title}")

    return reward


__all__ = [
    "ICON_REWARDS",
    "AVATAR_REWARDS",
    "CARD_REWARDS",
    "BACKGROUND_REWARDS",
    "send_reward",
]

