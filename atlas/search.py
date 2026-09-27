"""Pluggable HTML search providers with polite request pacing."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import re
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlparse
import xml.etree.ElementTree as ET

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

    def __iter__(self):
        """Allow providers to expose results as ordinary three-field tuples."""
        yield self.url
        yield self.title
        yield self.snippet


class SearchProvider(Protocol):
    """Shared search contract for an ordered list of HTML search providers."""

    def search(self, query: str, limit: int = 8) -> list[SearchResult | tuple[str, str, str]]: ...


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
            self.last_error = "DuckDuckGo returned a human verification challenge; fallback providers will be tried"
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


class BingHTML:
    """Bing HTML results used when the primary search provider is unavailable."""

    endpoint = "https://www.bing.com/search"

    def __init__(self, timeout: float = 20.0, min_interval: float = 1.0, session: requests.Session | None = None):
        self.timeout = timeout
        self.min_interval = max(1.0, min_interval)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        self.blocked = False
        self.last_error: str | None = None
        self.queries_attempted = 0

    @staticmethod
    def parse_results(html: str, limit: int = 8) -> list[SearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[SearchResult] = []
        seen: set[str] = set()
        for result in soup.select("#b_results li.b_algo"):
            anchor = result.select_one("h2 a")
            if not anchor:
                continue
            href = anchor.get("href", "").strip()
            parsed = urlparse(href)
            if (parsed.hostname or "").lower().endswith("bing.com") and parsed.path.startswith("/ck/a"):
                encoded_target = parse_qs(parsed.query).get("u", [""])[0]
                if encoded_target.startswith("a1"):
                    token = encoded_target[2:]
                    token += "=" * (-len(token) % 4)
                    try:
                        href = base64.urlsafe_b64decode(token).decode("utf-8")
                    except (ValueError, UnicodeDecodeError):
                        continue
                else:
                    continue
                href = unquote(href)
            if urlparse(href).scheme not in {"http", "https"}:
                continue
            normalized = href.split("#", 1)[0]
            if normalized in seen:
                continue
            snippet_node = result.select_one(".b_caption p") or result.select_one("p")
            results.append(SearchResult(
                normalized,
                anchor.get_text(" ", strip=True),
                snippet_node.get_text(" ", strip=True) if snippet_node else "",
            ))
            seen.add(normalized)
            if len(results) >= limit:
                break
        return results

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        self.queries_attempted += 1
        before_request(self.min_interval)
        try:
            response = self.session.get(self.endpoint, params={"q": query}, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            after_request()
            self.last_error = "Bing request failed"
            return []
        after_request()
        lowered = response.text.lower()
        if any(marker in lowered for marker in (
            "unusual traffic",
            "verify you are not a robot",
            "captcha",
            "automated requests",
        )):
            self.blocked = True
            self.last_error = "Bing returned a blocking or verification page"
            return []
        query_terms = {
            term for term in re.findall(r"[a-z0-9]+", query.lower())
            if len(term) >= 4 and term not in {"with", "from", "that", "over", "next", "into", "this", "their", "what", "european", "startup", "existing", "build", "rely"}
        }
        results = [
            result for result in self.parse_results(response.text, limit=limit)
            if len(query_terms & set(re.findall(r"[a-z0-9]+", f"{result.title} {result.snippet}".lower()))) >= 2
        ]
        if not results:
            self.last_error = "Bing returned no relevant parseable search results"
        return results


class ArxivAPI:
    """Keyless research search fallback using arXiv's public Atom API."""

    endpoint = "https://export.arxiv.org/api/query"

    def __init__(self, timeout: float = 25.0, min_interval: float = 3.0, session: requests.Session | None = None):
        self.timeout = timeout
        self.min_interval = max(1.0, min_interval)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/atom+xml,application/xml,text/xml"})
        self.blocked = False
        self.last_error: str | None = None
        self.queries_attempted = 0

    @staticmethod
    def parse_results(xml_text: str, limit: int = 8) -> list[SearchResult]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        atom = "{http://www.w3.org/2005/Atom}"
        results: list[SearchResult] = []
        seen: set[str] = set()
        for entry in root.findall(f"{atom}entry"):
            title_node = entry.find(f"{atom}title")
            summary_node = entry.find(f"{atom}summary")
            alternate = next((link for link in entry.findall(f"{atom}link") if link.get("rel") == "alternate"), None)
            if title_node is None or alternate is None or not alternate.get("href"):
                continue
            url = alternate.get("href", "").replace("http://arxiv.org/", "https://arxiv.org/")
            if url in seen:
                continue
            results.append(SearchResult(
                url,
                re.sub(r"\s+", " ", title_node.text or "").strip(),
                re.sub(r"\s+", " ", summary_node.text or "").strip() if summary_node is not None else "",
            ))
            seen.add(url)
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _api_query(query: str) -> str:
        terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        candidates = ["vision", "language", "action", "vla", "foundation", "manipulation", "learning", "control", "deployment", "data", "model"]
        selected = [term for term in candidates if term in terms][:5]
        if not selected or selected == ["model"]:
            selected = ["vision", "action", "foundation", "manipulation"]
        return "all:robotics AND (" + " OR ".join(f"all:{term}" for term in selected) + ")"

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        self.queries_attempted += 1
        before_request(self.min_interval)
        try:
            response = self.session.get(
                self.endpoint,
                params={
                    "search_query": self._api_query(query),
                    "start": 0,
                    "max_results": limit,
                    "sortBy": "relevance",
                    "sortOrder": "descending",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            after_request()
            self.last_error = "arXiv API request failed"
            return []
        after_request()
        topic_terms = set(re.findall(r"[a-z0-9]+", self._api_query(query).lower())) - {"all", "robotics", "or", "and"}
        results = [
            result for result in self.parse_results(response.text, limit=limit)
            if {"robot", "robotic", "robotics"} & set(re.findall(r"[a-z0-9]+", f"{result.title} {result.snippet}".lower()))
            and topic_terms & set(re.findall(r"[a-z0-9]+", f"{result.title} {result.snippet}".lower()))
        ]
        if not results:
            self.last_error = "arXiv API returned no parseable results"
        return results


def search_many(
    provider: SearchProvider | list[SearchProvider],
    queries: list[dict[str, str]],
    per_query: int = 6,
    max_total: int = 24,
    fallback_providers: list[SearchProvider] | None = None,
) -> list[SearchResult]:
    """Search providers in order, moving on when one is blocked or empty."""
    providers = list(provider) if isinstance(provider, list) else [provider]
    if fallback_providers is None:
        providers.append(BingHTML())
    else:
        providers.extend(fallback_providers)
    results: list[SearchResult] = []
    seen: set[str] = set()
    for item in queries:
        for current_provider in providers:
            if getattr(current_provider, "blocked", False):
                continue
            provider_results = current_provider.search(item["query"], limit=per_query)
            if not provider_results:
                continue
            setattr(current_provider, "used", True)
            for item_result in provider_results:
                result = item_result if isinstance(item_result, SearchResult) else SearchResult(*item_result)
                if result.url not in seen:
                    results.append(result)
                    seen.add(result.url)
                    if len(results) >= max_total:
                        return results
            break
    return results
