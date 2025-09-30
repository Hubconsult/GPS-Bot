import requests
import html
from urllib.parse import quote_plus

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GPT-Bot/1.0)"}
TIMEOUT = 6


def duck_instant(query: str) -> dict | None:
    """DuckDuckGo Instant Answer API (бесплатно, без ключа)."""
    url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        if j.get("Abstract") or j.get("RelatedTopics"):
            return {
                "title": j.get("Heading") or query,
                "snippet": j.get("Abstract") or "",
                "url": j.get("AbstractURL") or "",
            }
    except Exception:
        return None
    return None


def wiki_summary(title: str, lang="ru") -> dict | None:
    """Wikipedia summary API (бесплатно, без ключа)."""
    safe = title.replace(" ", "_")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{safe}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        j = r.json()
        return {
            "title": j.get("title"),
            "snippet": j.get("extract"),
            "url": j.get("content_urls", {}).get("desktop", {}).get("page"),
        }
    except Exception:
        return None


def web_search_aggregate(query: str) -> list[dict]:
    """Агрегация: сначала DuckDuckGo, потом Wikipedia."""
    res = []
    d = duck_instant(query)
    if d:
        res.append(d)
    if not res:  # если DDG пусто
        w = wiki_summary(query)
        if w:
            res.append(w)
    return res


def format_sources(sources: list[dict]) -> str:
    """Форматируем список источников в текст для Telegram."""
    lines = []
    for i, s in enumerate(sources, 1):
        title = html.escape(s.get("title") or f"Источник {i}")
        url = s.get("url") or ""
        if url:
            lines.append(f"{i}. <a href='{html.escape(url)}'>{title}</a>")
        else:
            lines.append(f"{i}. {title}")
    return "\n".join(lines)
