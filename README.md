# Atlas

Atlas is a CLI research-intelligence system that turns an open-ended question into a source-linked evidence store, an executive brief, and a deeper Markdown report. It does not call a language model. Decomposition, claim labeling, keyword matching, contradiction checks, and scenario framing use deterministic Python rules.

## Architecture

```text
Question
   |
   v
decompose.py -> targeted query plan
   |
   v
search.py -> DuckDuckGo HTML results
   |
   v
fetch.py -> robots.txt check -> readable source pages
   |
   v
evidence.py -> sentence claims + numbers + source metadata
   |
   v
analyze.py -> coverage, possible contradictions, scenarios, uncertainty
   |                                      |
   v                                      v
charts.py -> PNG                     report.py -> brief + report
   \                                      /
    +------------- store.py -> evidence.json
```

## Install and run

Use Python 3.12:

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -m atlas "Should a European robotics startup build its own vision-language-action model, fine-tune an existing model, or rely on external models over the next three years?"
```

Normal runs are written to `runs/<UTC timestamp>-<question slug>/`. Use `--output-dir path` to choose an explicit output directory, `--max-searches 6` to bound searches, and `--max-pages 10` to bound page fetches. Each run writes `brief.md`, `report.md`, `evidence.json`, and `decomposition.json`. A numeric evidence chart is written when recognized numbers exist.

The worked example and its live-run artifacts are under `examples/vla-robotics/`. During this build DuckDuckGo returned a human verification challenge on the first query, so the saved sample is explicitly inconclusive and contains no source citations. Rerun the CLI when the search endpoint permits requests to populate evidence.

## Pipeline stages

1. `decompose.py` identifies explicit alternatives, time horizon, geography, uncertainties, and focused query text.
2. `search.py` uses the DuckDuckGo HTML endpoint over HTTPS with a desktop browser User-Agent, a minimum one second between requests, and URL deduplication.
3. `fetch.py` checks each host's `robots.txt` before fetching. It extracts article/main text and drops failed or too-short pages. If robots.txt is unavailable due to a transient error, the fetch is skipped.
4. `evidence.py` extracts substantive sentence candidates, keeps an exact sentence snippet and source metadata, classifies each claim as fact, inference, or opinion, and extracts numbers with nearby units.
5. `analyze.py` matches claims to options by shared keywords, detects possible contradictions from topic overlap plus opposing evaluative words, lists numeric evidence, creates three conditional scenarios, and assigns a rule-based uncertainty rating.
6. `charts.py` plots extracted numeric values and labels each with its source title and claim ID. Units can differ, so the figure cautions against direct comparison across unlike units. When no quantitative source claims were extracted, it writes a clearly labeled run-coverage chart instead.
7. `report.py` creates a concise executive brief and a deeper report. Conclusions cite claim IDs; bibliography entries link to pages that were fetched successfully.
8. `store.py` writes the complete JSON payload, including decomposition, search results, fetched page text, claims, and analysis.

## Add a search provider

Implement a provider with a `search(query, limit)` method that returns `SearchResult` records containing `url`, `title`, and `snippet`, then use it in `cli.py` in place of `DuckDuckGoHTML`. Keep rate limiting, deduplication, and provider-specific error handling in the provider. Do not place API keys in source code or committed configuration.

## Limitations

There is no LLM at runtime. Question parsing only recognizes common explicit wording and may miss implicit choices or scope. Sentence extraction is not full linguistic claim detection. Fact, inference, and opinion labels rely on simple lexical rules; a source sentence labeled fact has not been independently verified. Contradiction detection is only a heuristic and can miss paraphrases or flag unrelated claims. Search result quality, inaccessible sources, robots exclusions, and request failures limit coverage. Scenario text is conditional analysis, not a forecast. Human review of primary sources remains necessary before making a consequential decision.

## Tests

Run the fixture suite with:

```powershell
py -3.12 -m pytest
```
