from telebot import types
from guides import guides
from config import CONSULT_LINK

user_answers = {}

def ask_question_1(bot, message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Проблемы с маркетплейсом", "Вопросы по налогам", "Личные трудности", "Другое")
    msg = bot.send_message(message.chat.id, "С чем у вас сейчас самая большая проблема?", reply_markup=markup)
    bot.register_next_step_handler(msg, ask_question_2)

def ask_question_2(message):
    bot = message.bot
    answer = message.text
    user_answers[message.chat.id] = {"q1": answer}
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add("Очень остро", "Средне", "Почти нет")
    msg = bot.send_message(message.chat.id, "Насколько сильно вас это беспокоит?", reply_markup=markup)
    bot.register_next_step_handler(msg, finish_survey)

def finish_survey(message):
    bot = message.bot
    answer = message.text
    user_answers[message.chat.id]["q2"] = answer

    q1 = user_answers[message.chat.id]["q1"].lower()

    if "маркетплейс" in q1:
        guide_key = "претензия"
    elif "налог" in q1:
        guide_key = "налоги"
    elif "личн" in q1:
        guide_key = "выгорание"
    else:
        guide_key = None

    if guide_key and guide_key in guides:
        response = guides[guide_key]
    else:
        response = "Спасибо за ответы! Если хотите, напишите подробно, и я помогу."

    response += f"\n\nЕсли хочешь, помогу разобраться глубже — пиши мне в личку 👉 {CONSULT_LINK}. Консультация бесплатная!"

    bot.send_message(message.chat.id, response, reply_markup=None)
    user_answers.pop(message.chat.id, None)
