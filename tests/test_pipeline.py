import re

from atlas.analyze import analyze, detect_contradictions
from atlas.decompose import decompose
from atlas.evidence import extract_claims
from atlas.fetch import FetchedPage
from atlas.report import make_brief, make_report


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
