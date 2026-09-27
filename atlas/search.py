"""DuckDuckGo HTML search provider with polite request pacing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .net import after_request, before_request

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class DuckDuckGoHTML:
    """A small HTML endpoint provider. Requests are spaced by at least one second."""

    endpoint = "https://html.duckduckgo.com/html/"

    def __init__(self, timeout: float = 20.0, min_interval: float = 1.0, session: requests.Session | None = None):
        self.timeout = timeout
        self.min_interval = max(1.0, min_interval)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        self.blocked = False
        self.last_error: str | None = None
        self.queries_attempted = 0

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        self.queries_attempted += 1
        before_request(self.min_interval)
        try:
            response = self.session.get(self.endpoint, params={"q": query}, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            after_request()
            self.last_error = "DuckDuckGo request failed"
            return []
        after_request()
        soup = BeautifulSoup(response.text, "html.parser")
        if "Unfortunately, bots use DuckDuckGo too" in response.text or "complete the following challenge" in response.text.lower():
            self.blocked = True
            self.last_error = "DuckDuckGo returned a human verification challenge; search stopped"
            return []
        if response.status_code >= 400:
            self.last_error = f"DuckDuckGo returned HTTP {response.status_code}"
            return []
        results: list[SearchResult] = []
        seen: set[str] = set()
        for result in soup.select(".result"):
            anchor = result.select_one("a.result__a")
            if not anchor:
                continue
            href = anchor.get("href", "").strip()
            parsed = urlparse(href)
            if "duckduckgo.com" in (parsed.hostname or "") and parsed.path.startswith("/l/"):
                href = parse_qs(parsed.query).get("uddg", [""])[0]
                href = unquote(href)
            if urlparse(href).scheme not in {"http", "https"}:
                continue
            normalized = href.split("#", 1)[0]
            if normalized in seen:
                continue
            snippet_node = result.select_one(".result__snippet")
            results.append(SearchResult(normalized, anchor.get_text(" ", strip=True), snippet_node.get_text(" ", strip=True) if snippet_node else ""))
            seen.add(normalized)
            if len(results) >= limit:
                break
        return results


def search_many(provider: DuckDuckGoHTML, queries: list[dict[str, str]], per_query: int = 6, max_total: int = 24) -> list[SearchResult]:
    results: list[SearchResult] = []
    seen: set[str] = set()
    for item in queries:
        for result in provider.search(item["query"], limit=per_query):
            if result.url not in seen:
                results.append(result)
                seen.add(result.url)
                if len(results) >= max_total:
                    return results
        if provider.blocked:
            break
    return results
