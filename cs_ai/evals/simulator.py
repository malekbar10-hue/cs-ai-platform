"""
cs_ai/evals/simulator.py — CLI runner for the CS AI eval harness.

Usage:
    python cs_ai/evals/simulator.py [--dataset GLOB] [--baseline FLOAT] [--ci]

Options:
    --dataset   Glob pattern relative to cs_ai/evals/dataset/ (default: *.json)
    --baseline  Minimum passing score 0–1 (default: 0.80)
    --ci        Exit with code 1 if overall score < baseline (for CI gate)
    --verbose   Print per-case scores

The simulator runs each eval case through the real pipeline (no mocks) and
scores it with the four graders in graders.py.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import traceback
from typing import Any

# ---------------------------------------------------------------------------
# Path setup — make engine importable regardless of cwd
# ---------------------------------------------------------------------------

_HERE    = os.path.dirname(os.path.abspath(__file__))
_ENGINE  = os.path.abspath(os.path.join(_HERE, "..", "engine"))
_AGENTS  = os.path.join(_ENGINE, "agents")

for _p in (_HERE, _ENGINE, _AGENTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Pipeline import — best-effort; simulator degrades gracefully if unavailable
# ---------------------------------------------------------------------------

_PIPELINE_AVAILABLE = False
try:
    from pipeline import run_pipeline   # type: ignore[import]
    _PIPELINE_AVAILABLE = True
except ImportError:
    pass

from graders import (   # noqa: E402  (after sys.path setup)
    IntentGrader,
    DecisionGrader,
    ClaimSupportGrader,
    SafetyGrader,
    composite_score,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASELINE  = 0.80
DATASET_DIR       = os.path.join(_HERE, "dataset")

_GRADERS = [
    ("intent",    IntentGrader()),
    ("decision",  DecisionGrader()),
    ("claims",    ClaimSupportGrader()),
    ("safety",    SafetyGrader()),
]


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    """
    Feed a single case through the pipeline and return the resulting ctx dict.

    If the pipeline is unavailable or raises, returns a minimal stub so the
    graders can still run (and will score 0.0 on every dimension).
    """
    inp: dict[str, Any] = case.get("input", {})

    if not _PIPELINE_AVAILABLE:
        return {
            "route":  "unknown",
            "intent": "unknown",
            "draft":  "",
            "_error": "pipeline not importable",
        }

    try:
        ctx = dict(inp)
        ctx = run_pipeline(ctx)
        return ctx
    except Exception as exc:  # noqa: BLE001
        return {
            "route":  "unknown",
            "intent": "unknown",
            "draft":  "",
            "_error": str(exc),
            "_tb":    traceback.format_exc(),
        }


# ---------------------------------------------------------------------------
# Dataset loader
# ---------------------------------------------------------------------------

def _load_dataset(pattern: str) -> list[dict[str, Any]]:
    full_pattern = os.path.join(DATASET_DIR, pattern)
    files        = sorted(glob.glob(full_pattern))
    if not files:
        print(f"[WARN] No dataset files matched: {full_pattern}", file=sys.stderr)
        return []

    cases: list[dict[str, Any]] = []
    for fpath in files:
        with open(fpath, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            for item in data:
                item["_source_file"] = os.path.basename(fpath)
            cases.extend(data)
        else:
            print(f"[WARN] {fpath}: expected a JSON array, skipping.", file=sys.stderr)

    return cases


# ---------------------------------------------------------------------------
# Core eval loop
# ---------------------------------------------------------------------------

def run_eval(
    dataset_pattern: str = "*.json",
    baseline: float       = DEFAULT_BASELINE,
    verbose: bool         = False,
) -> tuple[float, list[dict[str, Any]]]:
    """
    Run all cases and return (overall_score, results_list).

    Each entry in results_list is:
        { id, source_file, composite, per_grader: {name: score}, error? }
    """
    cases   = _load_dataset(dataset_pattern)
    results: list[dict[str, Any]] = []

    if not cases:
        return 0.0, results

    for case in cases:
        cid    = case.get("id", "?")
        source = case.get("_source_file", "?")

        output = _run_case(case)

        per_grader = {name: grader.score(case, output) for name, grader in _GRADERS}
        comp       = composite_score(case, output)

        result: dict[str, Any] = {
            "id":          cid,
            "source_file": source,
            "composite":   comp,
            "per_grader":  per_grader,
        }
        if "_error" in output:
            result["error"] = output["_error"]

        results.append(result)

        if verbose:
            status = "PASS" if comp >= baseline else "FAIL"
            grader_str = "  ".join(f"{n}={s:.2f}" for n, s in per_grader.items())
            print(f"[{status}] {cid:12s}  composite={comp:.3f}  {grader_str}")
            if "_error" in output:
                print(f"        ERROR: {output['_error']}")

    overall = sum(r["composite"] for r in results) / len(results)
    return overall, results


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(
    overall: float,
    results: list[dict[str, Any]],
    baseline: float,
) -> None:
    n_total = len(results)
    n_pass  = sum(1 for r in results if r["composite"] >= baseline)
    n_fail  = n_total - n_pass

    print()
    print("=" * 60)
    print(f"  EVAL SUMMARY")
    print("=" * 60)
    print(f"  Cases run    : {n_total}")
    print(f"  Passed (≥{baseline:.0%}): {n_pass}")
    print(f"  Failed       : {n_fail}")
    print(f"  Overall score: {overall:.4f}")
    print(f"  Baseline     : {baseline:.4f}")
    status_str = "PASS ✓" if overall >= baseline else "FAIL ✗"
    print(f"  Gate result  : {status_str}")
    print("=" * 60)
    print()

    if n_fail:
        print("  Failed cases:")
        for r in results:
            if r["composite"] < baseline:
                err = f"  [{r.get('error', '')}]" if "error" in r else ""
                print(f"    - {r['id']:12s}  score={r['composite']:.3f}{err}")
        print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CS AI eval harness — run pipeline against labelled test cases."
    )
    parser.add_argument(
        "--dataset",
        default="*.json",
        help="Glob pattern relative to cs_ai/evals/dataset/ (default: *.json)",
    )
    parser.add_argument(
        "--baseline",
        type=float,
        default=DEFAULT_BASELINE,
        help=f"Minimum passing score 0–1 (default: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Exit with code 1 if overall score < baseline",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-case scores",
    )
    args = parser.parse_args()

    if not _PIPELINE_AVAILABLE:
        print(
            "[WARN] pipeline.py could not be imported — all pipeline outputs "
            "will be stubs. Graders will score 0 on route/intent/draft checks.",
            file=sys.stderr,
        )

    overall, results = run_eval(
        dataset_pattern=args.dataset,
        baseline=args.baseline,
        verbose=args.verbose,
    )

    _print_summary(overall, results, args.baseline)

    # Write JSON results for CI artifact upload
    _results_dir = os.path.join(_HERE, "results")
    os.makedirs(_results_dir, exist_ok=True)
    _results_path = os.path.join(_results_dir, "eval_results.json")
    with open(_results_path, "w", encoding="utf-8") as _fh:
        json.dump(
            {"overall": overall, "baseline": args.baseline, "cases": results},
            _fh,
            indent=2,
        )

    if args.ci and overall < args.baseline:
        sys.exit(1)


if __name__ == "__main__":
    main()
