"""Deterministic evidence synthesis: coverage, contradictions, and scenarios."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

WORD_RE = re.compile(r"[a-zA-Z0-9-]+")
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those", "are", "was", "were", "will", "would", "could", "should", "may", "might", "can", "has", "have", "had", "not", "but", "than", "into", "over", "under", "their", "they", "them", "its", "our", "your", "which", "when", "where", "what", "who", "how", "about", "also", "more", "most", "some", "many", "such", "other", "been", "being", "using", "used", "use", "based", "model", "models", "robot", "robots", "robotics", "system", "systems", "according", "research", "study", "report", "company", "companies", "new", "one", "two", "first", "second", "third",
}
POSITIVE = {"increase", "increased", "improve", "improved", "improvement", "higher", "stronger", "success", "successful", "effective", "benefit", "benefits", "growth", "gain", "gains", "faster", "reliable", "reliability", "reduce", "reduced", "lower", "advantage", "advantages", "outperform", "outperformed", "profitable"}
NEGATIVE = {"decrease", "decreased", "decline", "declined", "worse", "weak", "failure", "failed", "ineffective", "risk", "risks", "costly", "expensive", "slower", "unreliable", "harm", "loss", "losses", "disadvantage", "disadvantages", "underperform", "underperformed", "shortage", "limited", "difficult"}
NEGATORS = {"not", "no", "never", "without", "cannot", "isn't", "aren't", "doesn't", "didn't"}


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in WORD_RE.findall(text) if len(w) > 2 and w.lower() not in STOP and not w.isdigit()}


def _stance(text: str) -> str:
    words = [w.lower() for w in WORD_RE.findall(text)]
    pos = neg = 0
    for i, word in enumerate(words):
        inverted = any(w in NEGATORS for w in words[max(0, i - 3):i])
        if word in POSITIVE:
            if inverted: neg += 1
            else: pos += 1
        if word in NEGATIVE:
            if inverted: pos += 1
            else: neg += 1
    if pos > neg: return "positive"
    if neg > pos: return "negative"
    return "neutral"


def _match_claims(topic: str, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = _tokens(topic)
    if not keys:
        return []
    matched = []
    for claim in claims:
        words = _tokens(claim["text"])
        overlap = keys & words
        if len(overlap) >= min(2, len(keys)) or (len(keys) == 1 and overlap):
            matched.append(claim)
    return matched


def detect_contradictions(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contradictions = []
    for i, left in enumerate(claims):
        left_tokens = _tokens(left["text"])
        left_stance = _stance(left["text"])
        if left_stance == "neutral":
            continue
        for right in claims[i + 1:]:
            right_stance = _stance(right["text"])
            if right_stance == "neutral" or right_stance == left_stance:
                continue
            common = left_tokens & _tokens(right["text"])
            if len(common) < 2:
                continue
            # Require a reasonably shared subject, then keep the detector's uncertainty explicit.
            smaller = min(len(left_tokens), len(_tokens(right["text"])))
            if smaller and len(common) / smaller >= 0.25:
                contradictions.append({
                    "claim_ids": [left["id"], right["id"]],
                    "shared_terms": sorted(common),
                    "stances": [left_stance, right_stance],
                    "reason": "Keyword overlap and opposing evaluative language suggest a possible conflict; human review is required.",
                })
    return contradictions


def quantify(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for claim in claims:
        for number in claim["numbers"]:
            rows.append({
                "claim_id": claim["id"], "value": number["value"], "unit": number["unit"],
                "claim": claim["text"], "source_title": claim["source_title"], "source_url": claim["source_url"],
            })
    return rows


def analyze(question: str, decomposition: dict[str, Any], claims: list[dict[str, Any]]) -> dict[str, Any]:
    contradictions = detect_contradictions(claims)
    options = decomposition.get("options", []) or [question]
    option_coverage = []
    for option in options:
        matched = _match_claims(option, claims)
        ids = [c["id"] for c in matched]
        coverage_count = len(matched)
        if coverage_count >= 8: level = "low"
        elif coverage_count >= 3: level = "medium"
        else: level = "high"
        reason = f"{coverage_count} extracted claims matched this option by keyword; rule-based matching may miss relevant evidence or include false matches."
        if not matched:
            reason = "No fetched claim matched this option, so its evidence base in this run is insufficient."
        option_coverage.append({"option": option, "evidence_ids": ids, "claim_count": coverage_count, "uncertainty": {"rating": level, "reason": reason}})
    all_ids = [c["id"] for c in claims]
    scenarios = []
    default_ids = all_ids[: min(5, len(all_ids))]
    scenario_defs = [
        ("Base case", "Analysis: no source claims were retrieved, so this run cannot support a base view of model cost, performance, or reliability." if not claims else "Analysis: the retrieved claims do not settle the choice, so an incremental decision with measured pilots is a reasonable base case."),
        ("Capability upside", "Analysis: in this scenario, relevant model capability and adaptation tooling improve enough to make a more ambitious in-house or fine-tuning path practical."),
        ("Constraint downside", "Analysis: in this scenario, cost, talent, reliability, access, or policy constraints make dependence on a single approach harder to sustain."),
    ]
    for idx, (name, narrative) in enumerate(scenario_defs):
        selected = option_coverage[min(idx, len(option_coverage) - 1)]["evidence_ids"] if option_coverage else []
        if not selected:
            selected = default_ids
        scenarios.append({"name": name, "narrative": narrative, "supporting_evidence_ids": selected[:8]})
    conclusions = []
    for item in option_coverage:
        n = item["claim_count"]
        if item["evidence_ids"]:
            text = f"Analysis: this run found {n} claims that matched '{item['option']}' by keyword. This measures evidence coverage, not the option's overall merit."
        else:
            text = f"Analysis: this run did not retrieve directly matched claims for '{item['option']}', so the available evidence does not support a comparative judgment."
        conclusions.append({"text": text, "evidence_ids": item["evidence_ids"][:8], "uncertainty": item["uncertainty"]})
    return {
        "contradictions": contradictions,
        "quantification": quantify(claims),
        "scenarios": scenarios,
        "option_coverage": option_coverage,
        "conclusions": conclusions,
    }
