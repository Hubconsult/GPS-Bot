from __future__ import annotations

import re
from typing import List

from openai_adapter import extract_response_text, prepare_responses_input
from settings import CHAT_MODEL, SYSTEM_PROMPT, client
from text_utils import sanitize_model_output

__all__ = ["ask_gpt_web", "should_prefer_web", "should_escalate_to_web"]


_WEB_SEARCH_PROMPT = (
    f"{SYSTEM_PROMPT}\n\n"
    "Ты работаешь с доступом к интернету. Используй инструмент web_search, когда нужно проверить факты, "
    "найти свежие данные или подтвердить информацию. Сначала кратко сформулируй ответ своими словами, "
    "затем перечисли ключевые факты и закончи разделом 'Источники' со списком ссылок. Отвечай на языке "
    "запроса пользователя.\n"
)


def ask_gpt_web(query: str) -> str:
    """Return an internet-backed answer using the Responses API web_search tool."""

    messages: List[dict] = [
        {"role": "system", "content": _WEB_SEARCH_PROMPT},
        {"role": "user", "content": query},
    ]

    response = client.responses.create(
        model=CHAT_MODEL,
        input=prepare_responses_input(messages),
        tools=[{"type": "web_search"}],
    )
    text = extract_response_text(response)
    return sanitize_model_output(text)


_TIME_SENSITIVE_KEYWORDS = {
    "сейчас",
    "сегодня",
    "завтра",
    "вчера",
    "на днях",
    "прямо сейчас",
    "последние",
    "последних",
    "актуаль",
    "текущ",
    "нынеш",
    "свеже",
    "прямой эфир",
    "breaking",
    "latest",
    "current",
    "today",
    "tonight",
    "now",
    "update",
}

_NEWS_KEYWORDS = {
    "новост",
    "новые данные",
    "что происходит",
    "что случил",
    "что там",
    "сводку",
    "произошло",
    "обнови",
    "обновление",
    "события",
    "итоги",
    "breaking news",
    "headline",
    "news",
}

_DATA_KEYWORDS = {
    "курс",
    "курсы",
    "курс валют",
    "курс доллара",
    "курс евро",
    "биткоин",
    "bitcoin",
    "крипт",
    "цена",
    "стоимость",
    "котиров",
    "погода",
    "прогноз",
    "расписание",
    "рейс",
    "рейсы",
    "трафик",
    "пробк",
    "результаты",
    "матч",
    "счёт",
    "аэропорт",
    "авиарейс",
    "налог",
    "статистик",
    "отчёт",
    "отчет",
    "рейтинг",
    "дивиденды",
    "выборы",
    "санкции",
    "доллар",
    "евро",
    "инфляц",
    "экономик",
    "отпуск",
    "выходные",
}

_WEB_REQUEST_KEYWORDS = {
    "найди",
    "поиск",
    "посмотри",
    "проверь",
    "узнай",
    "google",
    "гугл",
    "ищи",
    "найди в интернете",
    "в интернете",
    "в сети",
    "скажи что в",
}

_MONTHS_PATTERN = re.compile(
    r"\b(?:январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\w*\b",
    re.IGNORECASE,
)

_FUTURE_YEAR_PATTERN = re.compile(r"\b20(2[3-9]|[3-9]\d)\b")

_NEED_WEB_ANSWER_PHRASES = {
    "не могу просматривать интернет",
    "нет доступа к интернету",
    "не имею доступа к интернету",
    "не могу получить актуальную информацию",
    "не обладаю актуальной информацией",
    "не располагаю актуальными данными",
    "как языковая модель",
    "как модель",
    "у меня нет доступа к сети",
    "не могу проверить",
    "не нашёл информации",
    "не нашел информации",
    "i can't browse the internet",
    "i do not have access to the internet",
    "i don't have access to the internet",
    "i cannot access the internet",
    "i do not have up-to-date information",
    "i don't have up-to-date information",
    "i don't have current information",
    "i cannot provide real-time information",
    "i am not able to browse",
    "my knowledge is limited to",
    "my training data",
    "as a language model",
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def should_prefer_web(query: str) -> bool:
    normalized = _normalize(query)
    if not normalized:
        return False

    if any(keyword in normalized for keyword in _WEB_REQUEST_KEYWORDS):
        return True

    if any(keyword in normalized for keyword in _TIME_SENSITIVE_KEYWORDS):
        return True

    if any(keyword in normalized for keyword in _NEWS_KEYWORDS):
        return True

    if any(keyword in normalized for keyword in _DATA_KEYWORDS):
        return True

    if _MONTHS_PATTERN.search(query or "") and any(
        time_word in normalized for time_word in {"этого года", "в этом году", "в следующем году", "в прошлом году"}
    ):
        return True

    if _FUTURE_YEAR_PATTERN.search(normalized):
        return True

    return False


def should_escalate_to_web(query: str, answer: str) -> bool:
    normalized_answer = _normalize(answer)
    if not normalized_answer:
        return True

    if should_prefer_web(query):
        return True

    return any(phrase in normalized_answer for phrase in _NEED_WEB_ANSWER_PHRASES)
