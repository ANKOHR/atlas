"""Command-line entry point for Atlas."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

from .analyze import analyze
from .charts import create_numeric_chart
from .decompose import decompose
from .evidence import extract_claims
from .fetch import PageFetcher
from .report import make_brief, make_report
from .search import DuckDuckGoHTML, search_many
from .store import save_store


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:48] or "research-question"


def build_run(question: str, output_dir: Path, max_searches: int = 6, max_pages: int = 10) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    decomposition = decompose(question)
    search_plan = decomposition["search_queries"][:max_searches]
    provider = DuckDuckGoHTML()
    search_results = search_many(provider, search_plan, per_query=6, max_total=max(12, max_pages * 3))
    fetcher = PageFetcher()
    pages = fetcher.fetch_many(search_results, limit=max_pages)
    claims = extract_claims(pages)
    analysis = analyze(question, decomposition, claims)
    chart_path = create_numeric_chart(analysis["quantification"], output_dir, page_count=len(pages), claim_count=len(claims), query_count=provider.queries_attempted)
    payload = {
        "atlas_version": "0.1.0",
        "run_id": now.strftime("%Y%m%dT%H%M%SZ") + "-" + _slug(question),
        "run_date": now.isoformat(),
        "decomposition": decomposition,
        "search_results": [r.to_dict() for r in search_results],
        "search_status": {"provider": "DuckDuckGo HTML", "blocked": provider.blocked, "queries_attempted": provider.queries_attempted, "message": provider.last_error},
        "pages": [page.to_dict() for page in pages],
        "claims": claims,
        "analysis": analysis,
        "chart": chart_path.name,
        "chart_kind": "quantified_evidence" if analysis["quantification"] else "run_coverage",
    }
    save_run(output_dir, payload)
    return payload


def save_run(output_dir: Path, payload: dict) -> None:
    save_store(output_dir / "evidence.json", payload)
    save_store(output_dir / "decomposition.json", payload["decomposition"])
    (output_dir / "brief.md").write_text(make_brief(payload), encoding="utf-8")
    (output_dir / "report.md").write_text(make_report(payload), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an auditable research brief from public web sources.")
    parser.add_argument("question", help="Research question to investigate")
    parser.add_argument("--output-dir", type=Path, help="Write artifacts to this directory instead of a timestamped runs directory")
    parser.add_argument("--max-searches", type=int, default=6, help="Maximum targeted DuckDuckGo queries (default: 6)")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum source pages to fetch (default: 10)")
    args = parser.parse_args(argv)
    if args.max_searches < 1 or args.max_pages < 1:
        parser.error("--max-searches and --max-pages must be at least 1")
    if args.output_dir:
        output_dir = args.output_dir.resolve()
    else:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = Path("runs") / f"{stamp}-{_slug(args.question)}"
    payload = build_run(args.question, output_dir, args.max_searches, args.max_pages)
    print(f"Atlas run complete: {output_dir.resolve()}")
    print(f"Fetched pages: {len(payload['pages'])}; extracted claims: {len(payload['claims'])}")
    print(f"Outputs: brief.md, report.md, evidence.json, decomposition.json, {payload['chart']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
