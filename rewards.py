# rewards.py
import random

# --- Смайлы (коллекция эмоций) ---
SMILES = [
    "😊", "😟", "😴", "😡",
    "🥰", "🤔", "😭", "😎",
    "😅", "🤯", "😇", "🤗",
]

# --- Аватарки (файлы-образы) ---
AVATARS = [
    "Волна.png", "Замок.png", "Росток.png", "Феникс.png",
    "Сова.png", "Маска.png", "Дракон.png", "Город масок.png",
    "Кролик.png", "Шар.png", "Хрустальный шар.png", "Солнце.png",
]

# --- Карточки с историями (строго по порядку) ---
STORY_CARDS = [
    {"id": 1, "title": "Искра во тьме", "file": None},
    {"id": 2, "title": "Башня ветров", "file": "Башня ветров.png"},
    {"id": 3, "title": "Мир песков", "file": "Мир песков.png"},
    {"id": 4, "title": "Храм времени", "file": "Храм времени.png"},
    {"id": 5, "title": "Остров тайн", "file": "Остро тайн.png"},
    {"id": 6, "title": "Лес теней", "file": "Лес теней.png"},
    {"id": 7, "title": "Мост забытых", "file": "Мост забытых.png"},
    {"id": 8, "title": "Врата начала", "file": "Врата начала.png"},
    {"id": 9, "title": "Лунный лес", "file": "Лунный лес.png"},
    {"id": 10, "title": "Огненный закат", "file": "Огненый закат.png"},
]

# --- Фоны (редкие награды) ---
BACKGROUNDS = [
    {"id": 1, "title": "Звёздная ночь 🌌", "file": None},
    {"id": 2, "title": "Кристалический рассвет ✨", "file": "Кристалический рассвет.png"},
    {"id": 3, "title": "Лесное свечение", "file": "Лесное свечение.png"},
    {"id": 4, "title": "Огненный закат", "file": "Огненый закат.png"},
]

# --- Хранилище наград пользователей ---
user_rewards = {}  # {chat_id: {"smiles": [], "avatars": [], "cards": [], "backgrounds": []}}

def init_user(chat_id):
    if chat_id not in user_rewards:
        user_rewards[chat_id] = {"smiles": [], "avatars": [], "cards": [], "backgrounds": []}

def give_smile(chat_id):
    init_user(chat_id)
    available = [s for s in SMILES if s not in user_rewards[chat_id]["smiles"]]
    if available:
        smile = random.choice(available)
        user_rewards[chat_id]["smiles"].append(smile)
        return smile
    return None

def give_avatar(chat_id):
    init_user(chat_id)
    available = [a for a in AVATARS if a not in user_rewards[chat_id]["avatars"]]
    if available:
        avatar = random.choice(available)
        user_rewards[chat_id]["avatars"].append(avatar)
        return avatar
    return None

def give_next_card(chat_id):
    init_user(chat_id)
    owned = user_rewards[chat_id]["cards"]
    next_index = len(owned)
    if next_index < len(STORY_CARDS):
        card = STORY_CARDS[next_index]
        user_rewards[chat_id]["cards"].append(card)
        return card
    return None

def give_background(chat_id, bg_id):
    init_user(chat_id)
    bg = next((b for b in BACKGROUNDS if b["id"] == bg_id), None)
    if bg and bg not in user_rewards[chat_id]["backgrounds"]:
        user_rewards[chat_id]["backgrounds"].append(bg)
        return bg
    return None
