"""Rule-based extraction of auditable sentence-level claims."""

from __future__ import annotations

import re
from typing import Any

from .fetch import FetchedPage

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?P<currency>[$€£])?\s*(?P<value>-?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>\\?%|percent(?:age points?)?|years?|months?|weeks?|days?|hours?|minutes?|seconds?|billion|million|thousand|kWh|MW|GW|USD|EUR|GBP|robots?|parameters?|datasets?|companies|workers|employees|models|tokens|degrees?|-?DoF)?(?![A-Za-z0-9_])",
    re.I,
)
INFERENCE_CUES = ("may", "might", "could", "likely", "unlikely", "suggests", "indicates", "implies", "appears", "expected", "projected", "forecast", "we believe", "we expect")
OPINION_CUES = ("should", "must", "best", "worst", "excellent", "terrible", "in our view", "we recommend", "we argue")


def _kind(sentence: str, quoted: bool) -> str:
    lower = sentence.lower()
    if NUMBER_RE.search(sentence) or quoted:
        return "fact"
    if any(cue in lower for cue in OPINION_CUES):
        return "opinion"
    if any(cue in lower for cue in INFERENCE_CUES):
        return "inference"
    return "fact"


def _numbers(sentence: str) -> list[dict[str, Any]]:
    found = []
    numeric_text = re.sub(r"\(\s*\d+\s*\)", " ", sentence)
    for match in NUMBER_RE.finditer(numeric_text):
        raw_value = match.group("value").replace(",", "")
        try:
            value: int | float = float(raw_value)
            if value.is_integer():
                value = int(value)
        except ValueError:
            continue
        unit = match.group("unit") or "count"
        unit = unit.replace("\\", "")
        if unit.lower().lstrip("-") == "dof":
            unit = "DoF"
        currency = match.group("currency")
        if currency:
            unit = {"$": "USD", "€": "EUR", "£": "GBP"}[currency]
        found.append({"value": value, "unit": unit})
    return found


def extract_claims(pages: list[FetchedPage]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for page in pages:
        for raw_sentence in SENTENCE_RE.split(page.text.replace("\n", " ")):
            sentence = re.sub(r"\s+", " ", raw_sentence).strip()
            if len(sentence) < 45 or len(sentence.split()) < 7:
                continue
            # Ignore likely navigation fragments and headings without sentence content.
            if sentence.count("|") >= 2 or sentence.lower().startswith(("cookie policy", "privacy policy")):
                continue
            claims.append({
                "id": f"E{len(claims) + 1:04d}",
                "text": sentence,
                "source_url": page.url,
                "source_title": page.title,
                "date_accessed": page.date_accessed,
                "quoted_snippet": sentence,
                "kind": _kind(sentence, '"' in sentence or "“" in sentence),
                "numbers": _numbers(sentence),
            })
    return claims
