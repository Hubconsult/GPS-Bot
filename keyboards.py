from telebot import types

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        "Договор", "Блокировка", "Претензия", "ФАС", "Досудебка",
        "Налоги", "Выгорание", "Мини-опрос", "Помощь"
    ]
    markup.add(*buttons)
    return markup
