# bot_utils.py
from settings import bot


def show_typing(chat_id: int) -> None:
    """Показывает пользователю статус «печатает…» в чате Telegram."""
    try:
        bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass
