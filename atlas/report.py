"""Markdown report generation with evidence ID citations."""

from __future__ import annotations

from typing import Any


def _refs(ids: list[str]) -> str:
    return " ".join(f"[{item}]" for item in ids) if ids else "[Analysis, no fetched claim matched]"


def _sources(payload: dict[str, Any]) -> list[dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for page in payload.get("pages", []):
        unique[page["url"]] = {"title": page.get("title", page["url"]), "url": page["url"], "date_accessed": page.get("date_accessed", "")}
    return list(unique.values())


def make_brief(payload: dict[str, Any]) -> str:
    decomposition = payload["decomposition"]
    analysis = payload["analysis"]
    claims = payload.get("claims", [])
    lines = [
        "# Executive Brief",
        "",
        f"**Research question:** {decomposition['question']}",
        f"**Scope:** {decomposition.get('geography', 'Not specified')}; horizon: {decomposition.get('time_horizon', 'Not specified')}",
        f"**Run date:** {payload.get('run_date', 'unknown')}",
        "",
        "## Decision frame",
        "",
        "Options identified: " + ("; ".join(decomposition.get("options", [])) if decomposition.get("options") else "No explicit alternatives were parsed."),
        "",
        "## Findings",
        "",
    ]
    if analysis["conclusions"]:
        for item in analysis["conclusions"]:
            lines.append(f"- {item['text']} {_refs(item['evidence_ids'])} Uncertainty: **{item['uncertainty']['rating']}**. {item['uncertainty']['reason']}")
    elif claims:
        lines.append(f"- Analysis: extracted {len(claims)} source claims, but no option-level conclusion was produced. {_refs([c['id'] for c in claims[:3]])}")
    else:
        lines.append("- Analysis: no web pages passed fetch and extraction checks in this run. No source-backed conclusion is available.")
    lines.extend(["", "## Decision uncertainties", ""])
    for uncertainty in decomposition.get("key_uncertainties", []):
        lines.append(f"- Analysis: {uncertainty} is unresolved by this rule-based evidence scan.")
    lines.extend(["", "## Scenarios", ""])
    for scenario in analysis.get("scenarios", []):
        lines.append(f"- **{scenario['name']}:** {scenario['narrative']} {_refs(scenario['supporting_evidence_ids'])}")
    lines.extend(["", "## Evidence and limitations", "", f"The run extracted **{len(claims)} claims** from **{len(payload.get('pages', []))} fetched pages**. Keyword matching does not establish causality or source quality. Scenario descriptions are analysis, not forecasts.", ""])
    search_status = payload.get("search_status", {})
    if search_status.get("message"):
        lines.extend([f"Search status: {search_status['message']}.", ""])
    if payload.get("chart"):
        chart_note = "Units may differ across rows." if payload.get("chart_kind") == "quantified_evidence" else "This chart records pipeline output counts, not research findings."
        lines.extend([f"Run chart: `{payload['chart']}`. {chart_note}", ""])
    sources = _sources(payload)
    lines.extend(["## Sources", ""])
    if sources:
        for index, source in enumerate(sources, 1):
            lines.append(f"{index}. [{source['title']}]({source['url']}) (accessed {source['date_accessed']})")
    else:
        lines.append("No pages were successfully fetched.")
    return "\n".join(lines).strip() + "\n"


def make_report(payload: dict[str, Any]) -> str:
    decomposition = payload["decomposition"]
    analysis = payload["analysis"]
    claims = payload.get("claims", [])
    lines = [
        "# Research Report",
        "",
        f"**Question:** {decomposition['question']}",
        f"**Run date:** {payload.get('run_date', 'unknown')}",
        "",
        "## Scope and method",
        "",
        f"Analysis: the rule-based decomposer identified geography as **{decomposition.get('geography', 'Not specified')}** and horizon as **{decomposition.get('time_horizon', 'Not specified')}**. Search used DuckDuckGo HTML; pages were fetched only when the site's robots policy allowed it. No language model was used.",
        "",
        "## Executive assessment",
        "",
    ]
    if analysis["conclusions"]:
        for item in analysis["conclusions"]:
            lines.extend([item["text"] + " " + _refs(item["evidence_ids"]), f"Uncertainty: **{item['uncertainty']['rating']}**. {item['uncertainty']['reason']}", ""])
    else:
        lines.append("Analysis: no source-backed option assessment is possible because this run yielded no extracted claims.")
    lines.extend(["## Options and evidence coverage", ""])
    for item in analysis.get("option_coverage", []):
        lines.append(f"### {item['option']}")
        lines.append( f"Analysis: {item['claim_count']} claims matched this option. Matched evidence: {_refs(item['evidence_ids'])}")
        lines.append(f"Uncertainty: **{item['uncertainty']['rating']}**. {item['uncertainty']['reason']}")
        lines.append("")
    lines.extend(["## Contradictions and tensions", ""])
    if analysis.get("contradictions"):
        for item in analysis["contradictions"]:
            lines.append(f"Possible contradiction between {', '.join(item['claim_ids'])} on terms {', '.join(item['shared_terms'])}. {item['reason']} {_refs(item['claim_ids'])}")
    else:
        lines.append("Analysis: the keyword detector found no opposing evaluative claims with sufficient term overlap. This does not establish that sources agree.")
    lines.extend(["", "## Scenarios", ""])
    for scenario in analysis.get("scenarios", []):
        lines.extend([f"### {scenario['name']}", "", f"{scenario['narrative']} {_refs(scenario['supporting_evidence_ids'])}", ""])
    lines.extend(["## Key uncertainties", ""])
    for uncertainty in decomposition.get("key_uncertainties", []):
        lines.append(f"- Analysis: {uncertainty} remains unresolved by this source set.")
    lines.extend(["", "## Quantification table", ""])
    quant = analysis.get("quantification", [])
    if quant:
        lines.extend(["| Evidence | Value | Source claim | Source URL |", "|---|---:|---|---|"])
        for row in quant:
            claim_short = row["claim"].replace("|", "\\|")[:180]
            lines.append(f"| [{row['claim_id']}] | {row['value']} {row['unit']} | {claim_short} | [{row['source_title']}]({row['source_url']}) |")
    else:
        lines.append("No numbers with recognized units were extracted.")
    lines.extend(["", "## Extracted claims", ""])
    if claims:
        for claim in claims:
            lines.append(f"- **[{claim['id']}] {claim['kind']}:** {claim['text']} Source: [{claim['source_title']}]({claim['source_url']}) (accessed {claim['date_accessed']}).")
    else:
        lines.append("No claims were extracted from fetched pages.")
    lines.extend(["", "## Limitations", "", "Analysis: claims are sentence candidates, not independently verified facts. Automated fact versus inference labeling is lexical and can be wrong. Keyword-based contradiction detection can miss paraphrases and can flag unrelated claims. Search coverage is limited by provider results, robots policies, network failures, and the page cap. Scenario descriptions are conditional analysis, not predictions.", "", "## Bibliography", ""])
    search_status = payload.get("search_status", {})
    if search_status.get("message"):
        lines.insert(lines.index("## Limitations"), f"Search status: {search_status['message']}")
    sources = _sources(payload)
    if sources:
        for index, source in enumerate(sources, 1):
            lines.append(f"{index}. [{source['title']}]({source['url']}) (accessed {source['date_accessed']})")
    else:
        lines.append("No successfully fetched sources.")
    return "\n".join(lines).strip() + "\n"
