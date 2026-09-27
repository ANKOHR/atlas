import re
from pathlib import Path

from atlas.analyze import analyze, detect_contradictions
from atlas.decompose import decompose
from atlas.evidence import extract_claims
from atlas.fetch import FetchedPage
from atlas.report import make_brief, make_report
from atlas.search import ArxivAPI, BingHTML, SearchResult, search_many


def fixture_pages():
    return [FetchedPage(
        url="https://example.org/robotics-study",
        title="Robotics model study",
        date_accessed="2026-09-27T10:00:00+00:00",
        text=(
            "A 2025 study evaluated fine-tuning a vision model for warehouse robotics. "
            "The adapted system improved task success by 12 percent in the tested setting. "
            "Researchers said the result may not generalize to other factories. "
            "Building a large model was expensive and required substantial compute resources. "
            "A separate deployment report found that external APIs were reliable for routine tasks. "
            "However, the report warned that vendor access could become limited without notice."
        ),
    )]


def test_claim_extraction_labels_and_numbers():
    claims = extract_claims(fixture_pages())
    assert len(claims) >= 5
    assert claims[0]["id"] == "E0001"
    numeric = next(c for c in claims if c["numbers"])
    assert numeric["kind"] == "fact"
    assert numeric["numbers"][0] == {"value": 2025, "unit": "count"}
    inference = next(c for c in claims if "may not generalize" in c["text"])
    assert inference["kind"] == "inference"
    assert inference["source_url"] == "https://example.org/robotics-study"


def test_numeric_extraction_keeps_percent_units_and_ignores_identifiers_and_list_markers():
    pages = [FetchedPage(
        url="https://example.org/benchmark",
        title="Robot benchmark results",
        date_accessed="2026-09-27T10:00:00+00:00",
        text=(
            "The controller achieved a 57.4% success rate on RoboCasa365 during the benchmark. "
            "The system supports (1) following instructions and (2) adapting to unseen environments. "
            r"The method produced a 34.2\% higher success rate with a 7-DoF robot."
        ),
    )]

    claims = extract_claims(pages)

    assert claims[0]["numbers"] == [{"value": 57.4, "unit": "%"}]
    assert claims[1]["numbers"] == []
    assert claims[2]["numbers"] == [
        {"value": 34.2, "unit": "%"},
        {"value": 7, "unit": "DoF"},
    ]


def test_contradiction_detection_requires_opposing_language_and_shared_terms():
    claims = [
        {"id": "E0001", "text": "External APIs were reliable for routine robotics tasks and performed effectively.", "source_url": "a"},
        {"id": "E0002", "text": "External APIs were unreliable for routine robotics tasks and performed poorly.", "source_url": "b"},
        {"id": "E0003", "text": "Fine-tuning improved warehouse task success.", "source_url": "c"},
    ]
    found = detect_contradictions(claims)
    assert len(found) == 1
    assert found[0]["claim_ids"] == ["E0001", "E0002"]


def test_decomposition_output_shape_and_alternatives():
    result = decompose("Should a European robotics startup build its own VLA model, fine-tune an existing model, or rely on external models over the next three years?")
    assert result["question"].startswith("Should")
    assert result["geography"] == "Europe"
    assert result["time_horizon"] == "next three years"
    assert len(result["options"]) == 3
    assert result["search_queries"] and all({"subquestion", "query"} <= item.keys() for item in result["search_queries"])


def test_reports_and_citation_integrity_on_fixtures():
    question = "Should a startup fine-tune or use external robotics models?"
    decomposition = decompose(question)
    claims = extract_claims(fixture_pages())
    analysis = analyze(question, decomposition, claims)
    payload = {"decomposition": decomposition, "analysis": analysis, "claims": claims, "pages": [p.to_dict() for p in fixture_pages()], "run_date": "2026-09-27T10:00:00+00:00", "chart": None}
    brief = make_brief(payload)
    report = make_report(payload)
    assert "## Findings" in brief
    assert "## Bibliography" in report
    assert "https://example.org/robotics-study" in report
    referenced = set(re.findall(r"\[(E\d{4})\]", brief + report))
    available = {claim["id"] for claim in claims}
    assert referenced <= available
    assert referenced
    empty_analysis = analyze(question, decomposition, [])
    assert "no source claims were retrieved" in empty_analysis["scenarios"][0]["narrative"]


def test_bing_html_result_fixture_parses_real_links_and_snippets():
    fixture = Path(__file__).parent / "fixtures" / "bing_results.html"
    results = BingHTML.parse_results(fixture.read_text(encoding="utf-8"))

    assert results == [
        SearchResult(
            "https://robotics.example.org/research/vla-adaptation",
            "Adapting vision-language models for robotics",
            "A study of adaptation approaches for embodied robotics tasks.",
        ),
        SearchResult(
            "https://lab.example.edu/reports/robot-foundation-models",
            "Robot foundation models: deployment lessons",
            "Deployment report covering reliability, access, and cost tradeoffs.",
        ),
    ]


def test_search_many_uses_fallback_when_primary_returns_no_results():
    class EmptyProvider:
        blocked = False

        def search(self, query, limit=8):
            return []

    class FixtureProvider:
        blocked = False

        def search(self, query, limit=8):
            return [("https://example.org/fallback", "Fallback", "Found by fallback")]

    fallback = FixtureProvider()
    results = search_many(
        EmptyProvider(),
        [{"query": "robotics foundation models"}],
        fallback_providers=[fallback],
    )

    assert results[0].url == "https://example.org/fallback"
    assert fallback.used is True


def test_arxiv_atom_parser_returns_abstract_pages_as_search_results():
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Robot policy adaptation study</title>
        <summary>Researchers evaluated a pretrained robot policy on new tasks.</summary>
        <link href="http://arxiv.org/abs/2601.00001v1" rel="alternate" type="text/html" />
      </entry>
    </feed>"""

    results = ArxivAPI.parse_results(xml)

    assert results == [SearchResult(
        "https://arxiv.org/abs/2601.00001v1",
        "Robot policy adaptation study",
        "Researchers evaluated a pretrained robot policy on new tasks.",
    )]
