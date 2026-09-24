"""Run `python -m services.rag.evaluate [--semantic]` against reviewed fixtures."""
import argparse
import json
import time
from pathlib import Path
from .repository import load_records
from .retriever import embedding_model, retrieve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic", action="store_true")
    args = parser.parse_args()
    if args.semantic:
        # A semantic benchmark must fail if the model is absent, not silently
        # report lexical results as embedding quality.
        embedding_model()
    cases = json.loads((Path(__file__).resolve().parents[2] / "tests/fixtures/rag_eval.json").read_text(encoding="utf-8"))
    records = load_records()
    exact, recalled, relevant, negatives, abstained = 0, 0, 0, 0, 0
    started = time.perf_counter()
    for case in cases:
        expected = set(case["expected"])
        actual = {r["scheme_id"] for r in retrieve(case["query"], records, args.semantic)}
        exact += actual == expected
        recalled += len(actual & expected)
        relevant += len(expected)
        if not expected:
            negatives += 1
            abstained += not actual
    print(json.dumps({"mode": "semantic+lexical" if args.semantic else "lexical",
        "cases": len(cases), "exact_match": exact / len(cases), "recall_at_4": recalled / max(1, relevant),
        "negative_abstention": abstained / max(1, negatives),
        "mean_retrieval_ms": (time.perf_counter() - started) * 1000 / len(cases)}, indent=2))


if __name__ == "__main__":
    main()
