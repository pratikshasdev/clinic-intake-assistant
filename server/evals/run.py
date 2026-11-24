"""Score an extractor against hand-labelled synthetic intakes.

    python -m evals.run                      # offline rules baseline
    python -m evals.run --extractor claude   # needs ANTHROPIC_API_KEY; costs a few cents

Scores precision, recall and F1 per category. Medications are scored on
(concept, status), so marking a stopped medicine as active counts as a miss.
Items outside the terminology allowlist are labelled "other:<name>" and match
any uncoded prediction whose name contains that word.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.extract import get_extractor  # noqa: E402
from app.models import Extraction, IntakeText  # noqa: E402

CASES = Path(__file__).with_name("cases.json")
RESULTS = Path(__file__).with_name("results")


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    misses: list[str] = field(default_factory=list)

    def add(self, predicted: list[str], gold: list[str], case_id: str) -> None:
        remaining = list(gold)
        for p in predicted:
            match = next((g for g in remaining if _matches(p, g)), None)
            if match is None:
                self.fp += 1
                self.misses.append(f"{case_id}: extra {p}")
            else:
                self.tp += 1
                remaining.remove(match)
        self.fn += len(remaining)
        self.misses.extend(f"{case_id}: missed {g}" for g in remaining)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def _matches(predicted: str, gold: str) -> bool:
    if gold.startswith("other:") and predicted.startswith("other:"):
        g_key, _, g_status = gold[6:].partition("|")
        p_key, _, p_status = predicted[6:].partition("|")
        return (g_key in p_key or p_key in g_key) and g_status == p_status
    return predicted == gold


def _keys(extraction: Extraction) -> dict[str, list[str]]:
    def key(term_key: str, name: str) -> str:
        return f"other:{name.strip().lower()}" if term_key == "other" else term_key

    return {
        "conditions": [key(c.term_key, c.name) for c in extraction.conditions],
        "allergies": [key(a.term_key, a.substance) for a in extraction.allergies],
        "medications": [f"{key(m.term_key, m.name)}|{m.status}" for m in extraction.medications],
    }


def _gold_keys(gold: dict) -> dict[str, list[str]]:
    return {
        "conditions": gold["conditions"],
        "allergies": gold["allergies"],
        "medications": [f"{k}|{s}" for k, s in gold["medications"]],
    }


async def run(extractor_name: str, only: str | None) -> dict:
    settings = Settings(extractor=extractor_name)
    extractor = get_extractor(settings)
    cases = json.loads(CASES.read_text())
    if only:
        cases = [c for c in cases if c["id"] == only]

    scores = {k: Score() for k in ("conditions", "allergies", "medications")}
    nka_correct = 0
    quote_total = quote_found = 0
    latencies: list[float] = []

    for case in cases:
        text = IntakeText(**case["answers"])
        started = time.perf_counter()
        extraction = await extractor.extract(text)
        latencies.append(time.perf_counter() - started)
        predicted = _keys(extraction)
        gold = _gold_keys(case["gold"])
        for category, score in scores.items():
            score.add(predicted[category], gold[category], case["id"])
        nka_correct += extraction.no_known_allergies == case["gold"]["no_known_allergies"]
        source = text.all_text().lower()
        for item in [*extraction.conditions, *extraction.allergies, *extraction.medications]:
            quote_total += 1
            quote_found += " ".join(item.source_quote.lower().split()) in " ".join(source.split())

    report = {
        "extractor": extractor.name,
        "cases": len(cases),
        "categories": {
            k: {"precision": round(s.precision, 3), "recall": round(s.recall, 3), "f1": round(s.f1, 3), "errors": s.misses}
            for k, s in scores.items()
        },
        "no_known_allergies_accuracy": round(nka_correct / len(cases), 3) if cases else None,
        "source_quotes_found": f"{quote_found}/{quote_total}",
        "median_latency_s": round(sorted(latencies)[len(latencies) // 2], 3) if latencies else None,
    }
    return report


def print_report(report: dict) -> None:
    print(f"\nExtractor: {report['extractor']}   cases: {report['cases']}\n")
    print(f"{'category':<14}{'precision':>10}{'recall':>9}{'F1':>7}")
    for name, s in report["categories"].items():
        print(f"{name:<14}{s['precision']:>10.2f}{s['recall']:>9.2f}{s['f1']:>7.2f}")
    print(f"\nNo-known-allergies accuracy: {report['no_known_allergies_accuracy']:.2f}")
    print(f"Source quotes found verbatim: {report['source_quotes_found']}")
    print(f"Median latency: {report['median_latency_s']} s")
    errors = [e for s in report["categories"].values() for e in s["errors"]]
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  - {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extractor", default="rules", choices=["rules", "claude"])
    parser.add_argument("--case", help="Run a single case by id")
    parser.add_argument("--save", action="store_true", help="Write the report to evals/results/")
    args = parser.parse_args()
    report = asyncio.run(run(args.extractor, args.case))
    print_report(report)
    if args.save:
        RESULTS.mkdir(exist_ok=True)
        out = RESULTS / f"{report['extractor'].replace(':', '_')}.json"
        out.write_text(json.dumps(report, indent=2))
        print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
