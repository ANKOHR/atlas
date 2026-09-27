"""Deterministic decomposition of a research question."""

from __future__ import annotations

import re
from typing import Any


OPTION_MARKERS = ("build", "buy", "make", "fine-tune", "finetune", "use", "adopt", "rely", "invest", "enter", "launch")
GEO_TERMS = {
    "europe": "Europe", "european": "Europe", "eu": "European Union",
    "united states": "United States", "us ": "United States", "china": "China",
    "global": "Global", "worldwide": "Global", "uk": "United Kingdom",
}
STOP = {"should", "would", "could", "does", "do", "the", "a", "an", "over", "next", "for", "to", "of", "in", "on", "or", "and", "its", "it", "this", "that", "with"}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n?.!,;:")


def _options(question: str) -> list[str]:
    body = re.sub(r"^\s*(should|would|could)\s+", "", question.strip(), flags=re.I)
    body = _clean(body)
    # Prefer explicit alternatives introduced by an option verb.
    matches = list(re.finditer(r"\b(?:build|buy|make|fine[- ]?tune|use|adopt|rely on|invest in|enter|launch)\b", body, re.I))
    if len(matches) >= 2:
        start = matches[0].start()
        segment = body[start:]
        duration = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a)"
        segment = re.split(rf"\b(?:over|within|during|by)\s+(?:the\s+)?(?:next|coming|following)\s+{duration}\s+(?:years?|months?|quarters?)\b", segment, flags=re.I)[0]
        pieces = re.split(r",|\bor\b|\bversus\b|\bvs\.?\b", segment, flags=re.I)
        options = [_clean(p) for p in pieces if _clean(p)]
        if len(options) >= 2:
            return options
    return []


def decompose(question: str) -> dict[str, Any]:
    """Return a JSON-serializable decision frame and targeted search queries."""
    question = re.sub(r"\s+", " ", question).strip()
    opts = _options(question)
    duration = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a)"
    horizon_match = re.search(rf"\b(?:over|within|during|in)\s+(?:the\s+)?(next\s+{duration}\s+(?:years?|months?|quarters?))\b", question, re.I)
    if not horizon_match:
        horizon_match = re.search(r"\b(?:by|through)\s+(20\d{2})\b", question, re.I)
    horizon = _clean(horizon_match.group(1)) if horizon_match else "Not specified"
    lower = question.lower()
    geography = next((label for term, label in GEO_TERMS.items() if term in lower), "Not specified")
    topic_words = [w for w in re.findall(r"[a-zA-Z0-9-]+", question.lower()) if w not in STOP and len(w) > 2 and not w.isdigit()]
    topic = " ".join(topic_words[:8]) or question
    decision = question.rstrip("?.")
    uncertainties = [
        "Total cost, talent, compute, and time required for each option",
        "Task performance, reliability, and safety in the intended deployment setting",
        "Availability and durability of external model access, licensing, and vendor support",
        "How quickly relevant models and hardware capabilities will change",
    ]
    queries: list[dict[str, str]] = []
    for option in opts or [topic]:
        queries.append({"subquestion": f"Evidence on {option}", "query": f"{option} {topic} cost performance robotics model"})
        queries.append({"subquestion": f"Risks and constraints for {option}", "query": f"{option} risks licensing deployment robotics AI model"})
    queries.extend([
        {"subquestion": "Comparative economics and model-building tradeoffs", "query": f"robotics foundation model build vs fine tune cost research"},
        {"subquestion": "European policy and deployment context", "query": f"Europe robotics AI model regulation industry adoption {horizon}"},
    ])
    # Keep the search plan bounded and remove duplicate query text.
    seen: set[str] = set()
    unique_queries = []
    for item in queries:
        key = item["query"].lower()
        if key not in seen:
            unique_queries.append(item)
            seen.add(key)
    return {
        "question": question,
        "decision": decision,
        "options": opts,
        "time_horizon": horizon,
        "geography": geography,
        "key_uncertainties": uncertainties,
        "subquestions": [q["subquestion"] for q in unique_queries],
        "search_queries": unique_queries,
    }
