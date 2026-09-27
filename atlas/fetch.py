"""Robots-aware page fetching and main-text extraction."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict, dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from .search import USER_AGENT, SearchResult
from .net import after_request, before_request


@dataclass
class FetchedPage:
    url: str
    title: str
    date_accessed: str
    text: str
    status: str = "fetched"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class PageFetcher:
    def __init__(self, timeout: float = 15.0, min_interval: float = 1.0, session: requests.Session | None = None):
        self.timeout = timeout
        self.min_interval = max(1.0, min_interval)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        self._robots: dict[str, tuple[RobotFileParser, bool]] = {}

    def _request(self, url: str, check_redirect_robots: bool = False) -> requests.Response | None:
        current = url
        for _ in range(6):
            before_request(self.min_interval)
            try:
                response = self.session.get(current, timeout=self.timeout, allow_redirects=False)
            finally:
                after_request()
            location = response.headers.get("Location")
            if response.status_code not in {301, 302, 303, 307, 308} or not location:
                return response
            destination = urljoin(current, location)
            if check_redirect_robots and not self._allowed(destination):
                return None
            current = destination
        return None

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            robots_url = urljoin(origin, "/robots.txt")
            parser = RobotFileParser(robots_url)
            try:
                response = self._request(robots_url)
                if response is None:
                    self._robots[origin] = (parser, False)
                elif response.status_code == 404:
                    parser.parse([])
                    self._robots[origin] = (parser, True)
                elif response.ok:
                    parser.parse(response.text.splitlines())
                    self._robots[origin] = (parser, True)
                else:
                    # Fail closed when a site's robots policy cannot be read.
                    self._robots[origin] = (parser, False)
            except requests.RequestException:
                self._robots[origin] = (parser, False)
        parser, readable = self._robots[origin]
        return readable and parser.can_fetch(USER_AGENT, url)

    @staticmethod
    def extract_text(html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        for node in soup.select("script, style, noscript, svg, nav, footer, header, aside, form, iframe, template"):
            node.decompose()
        title = ""
        title_node = soup.select_one("meta[property='og:title']") or soup.select_one("title") or soup.select_one("h1")
        if title_node:
            title = title_node.get("content", "") if title_node.name == "meta" else title_node.get_text(" ", strip=True)
        root = soup.find("article") or soup.find("main") or soup.body or soup
        abstract_node = soup.select_one("blockquote.abstract")
        if abstract_node:
            abstract_text = abstract_node.get_text(" ", strip=True)
            abstract_text = re.sub(r"^Abstract:\s*", "", abstract_text, flags=re.IGNORECASE)
            paragraphs = [abstract_text]
        else:
            paragraphs = [p.get_text(" ", strip=True) for p in root.select("p")]
        paragraphs = [re.sub(r"\s+", " ", p) for p in paragraphs if len(p.strip()) >= 35]
        if len(" ".join(paragraphs)) < 200:
            paragraphs = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in root.select("h1, h2, h3, li")]
            paragraphs = [p for p in paragraphs if len(p) >= 35]
        return title.strip(), "\n".join(paragraphs).strip()

    def fetch(self, result: SearchResult) -> FetchedPage | None:
        if not self._allowed(result.url):
            return None
        try:
            response = self._request(result.url, check_redirect_robots=True)
            if response is None:
                return None
            response.raise_for_status()
        except requests.RequestException:
            return None
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type and not response.text.lstrip().startswith(("<!doctype html", "<html")):
            return None
        title, text = self.extract_text(response.text)
        if len(text) < 120:
            return None
        return FetchedPage(
            url=response.url,
            title=title or result.title or response.url,
            date_accessed=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            text=text,
        )

    def fetch_many(self, results: list[SearchResult], limit: int = 12) -> list[FetchedPage]:
        pages: list[FetchedPage] = []
        seen: set[str] = set()
        for result in results:
            page = self.fetch(result)
            if page and page.url not in seen:
                pages.append(page)
                seen.add(page.url)
            if len(pages) >= limit:
                break
        return pages
