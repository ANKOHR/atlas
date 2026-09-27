"""Charts for extracted numeric evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def create_numeric_chart(rows: list[dict[str, Any]], output_dir: Path, page_count: int = 0, claim_count: int = 0, query_count: int = 0) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not rows:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        labels = ["Queries attempted", "Pages fetched", "Claims extracted"]
        values = [query_count, page_count, claim_count]
        ax.bar(labels, values, color="#78909c")
        ax.set_title("Research evidence coverage for this run")
        ax.set_ylabel("Count")
        ax.set_ylim(0, max(values, default=0) + 0.5)
        ax.text(0.5, 0.94, "No quantitative source claims were extracted", transform=ax.transAxes, ha="center", color="#444444")
        ax.grid(axis="y", alpha=0.22)
        fig.tight_layout()
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "evidence_coverage.png"
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)
        return path
    data = rows[:18]
    labels = []
    values = []
    for row in data:
        title = row.get("source_title", "Source")
        labels.append(f"{title[:38]} | {row['value']} {row['unit']} | {row['claim_id']}")
        values.append(float(row["value"]))
    height = max(4.5, 0.42 * len(data))
    fig, ax = plt.subplots(figsize=(12, height))
    positions = list(range(len(data)))
    ax.barh(positions, values, color="#2f6f8f")
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_title("Numbers extracted from fetched source sentences (units vary)")
    ax.set_xlabel("Reported numeric value. Compare only values with compatible units.")
    ax.grid(axis="x", alpha=0.22)
    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "quantified_evidence.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path
