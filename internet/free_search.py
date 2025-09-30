import requests, html, re
from urllib.parse import quote_plus

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MyBot/1.0; +https://example.bot)"
}
TIMEOUT = 6

def clean_wiki_query(query: str) -> str:
    """Удаляет вводные слова и знаки препинания из вопроса, чтобы получить название статьи."""
    q = query.strip()
    # удаляем русские варианты «кто/что/какая/какой/какие ...»
    patterns = [
        r'^\s*(кто|что)\s+так(ой|ая|ое|ие)\s+',  # «кто такой», «что такое»
        r'^\s*какая\s+', r'^\s*какой\s+', r'^\s*какие\s+',
        r'^\s*когда\s+', r'^\s*где\s+', r'^\s*сколько\s+'
    ]
    for pat in patterns:
        q = re.sub(pat, '', q, flags=re.IGNORECASE)
    # убираем знаки препинания
    q = re.sub(r'[?!.,]+', '', q).strip()
    # Wikipedia использует подчёркивания вместо пробелов
    return q.replace(' ', '_')

def duck_instant(query: str) -> dict | None:
    """Поиск быстрых ответов в DuckDuckGo Instant Answer API."""
    url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        # DuckDuckGo может отдавать HTTP/202 при асинхронной обработке – это не ошибка
        if resp.status_code not in (200, 202):
            return None
        data = resp.json()
        abstract = data.get("Abstract")
        related = data.get("RelatedTopics") or []
        if abstract or related:
            return {
                "title": data.get("Heading") or query,
                "snippet": abstract or "",
                "url": data.get("AbstractURL") or ""
            }
    except Exception:
        pass
    return None

def wiki_summary(title: str, lang: str = "ru") -> dict | None:
    """Получает краткое описание статьи из Википедии."""
    safe_title = title.replace(' ', '_')
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{safe_title}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        j = r.json()
        return {
            "title": j.get("title"),
            "snippet": j.get("extract"),
            "url": j.get("content_urls", {}).get("desktop", {}).get("page")
        }
    except Exception:
        return None

def web_search_aggregate(query: str) -> list[dict]:
    """Агрегатор: ищет сначала в DuckDuckGo, потом в Википедии (очищенный запрос)."""
    results: list[dict] = []
    ddg = duck_instant(query)
    if ddg:
        results.append(ddg)
    if not results:
        # очищаем запрос для поиска статьи
        cleaned = clean_wiki_query(query)
        wiki = wiki_summary(cleaned)
        if wiki:
            results.append(wiki)
    return results

def format_sources(sources: list[dict]) -> str:
    """Формирует нумерованный список источников для Telegram (HTML)."""
    lines = []
    for i, s in enumerate(sources, 1):
        title = html.escape(s.get("title") or f"Источник {i}")
        url = s.get("url")
        if url:
            lines.append(f"{i}. <a href=\"{html.escape(url)}\">{title}</a>")
        else:
            lines.append(f"{i}. {title}")
    return "\n".join(lines)
