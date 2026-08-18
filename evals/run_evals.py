#!/usr/bin/env python3
"""tutor's offline eval harness (issue #48).

Runs the eval cases in ``evals/evals.json`` — authored in the skill-creator
eval workflow format — and grades their mechanical expectations against the
committed fixtures. Everything here is deterministic and offline: fixtures on
disk are the only input, fixed predicates are the only graders, and the live
Scryfall API is never called (the deliberate snapshot refresh script is the
one place network exists, and this harness never runs it).

Usage:
    python3 evals/run_evals.py [--case NAME_OR_ID] [--fixture-root DIR] [--out DIR]

Exit status: 0 when every graded mechanical expectation passes, 1 otherwise.

Two grader tiers (from the spec's testing decisions): hard mechanical
invariants are graded here by fixed predicates registered per expectation
text; expectations without a registered predicate are soft LLM judgment,
reported as such and left to the dev-time skill-creator workflow.

Results land in ``evals/results/<case-name>/`` as ``eval_metadata.json`` and
``grading.json`` in the skill-creator grading schema, so the same artifacts
slot into the skill-creator viewer and, later, the gated ``claude plugin
eval`` flow (see docs/spikes/plugin-eval-enablement.md).
"""

import argparse
import csv
import io
import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EVALS_DIR = pathlib.Path(__file__).resolve().parent

# Descriptive per-case directory names, keyed by eval id (the skill-creator
# evals.json schema itself carries no name field; the workflow names runs).
CASE_NAMES = {
    1: "harness-smoke",
}


class Context:
    """What every fixed predicate gets to look at: the fixture tree."""

    def __init__(self, fixture_root):
        self.fixture_root = pathlib.Path(fixture_root)

    def path(self, relative):
        return self.fixture_root / relative

    def read_manabox_csv(self, relative):
        """Parse a ManaBox export CSV header-keyed; tolerate a UTF-8 BOM."""
        raw = self.path(relative).read_bytes()
        text = raw.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))


# --- Fixed predicates -------------------------------------------------------
# Each returns (passed: bool, evidence: str).

def check_realism_row_count(ctx):
    rows = ctx.read_manabox_csv("collections/real-collection.csv")
    count = len(rows)
    return (
        count == 577,
        f"collections/real-collection.csv parsed header-keyed: {count} data rows (expected 577)",
    )


MANABOX_HEADER = [
    "Binder Name", "Binder Type", "Name", "Set code", "Set name",
    "Collector number", "Foil", "Rarity", "Quantity", "ManaBox ID",
    "Scryfall ID", "Purchase price", "Misprint", "Altered", "Condition",
    "Language", "Purchase price currency", "Added",
]

SYNTHETIC_COLLECTIONS = [
    "collections/synthetic-edge-cases.csv",
    "collections/synthetic-kitchen20-pool.csv",
    "collections/synthetic-standard-pool.csv",
]


def synthetic_rows(ctx):
    for rel in SYNTHETIC_COLLECTIONS:
        for r in ctx.read_manabox_csv(rel):
            yield rel, r


def check_etched_foil(ctx):
    hits = [f"{rel}: {r['Name']}" for rel, r in synthetic_rows(ctx) if r["Foil"] == "etched"]
    return bool(hits), f"etched Foil rows: {hits or 'none'}"


def check_non_english_languages(ctx):
    langs = {}
    for rel, r in synthetic_rows(ctx):
        if r["Language"] != "en":
            langs.setdefault(r["Language"], f"{rel}: {r['Name']}")
    missing = {"ja", "zhs"} - set(langs)
    return not missing, f"non-English rows: {langs or 'none'}; missing: {sorted(missing) or 'none'}"


def check_promo_collector_numbers(ctx):
    hits = [
        f"{rel}: {r['Name']} ({r['Set code']}) {r['Collector number']}"
        for rel, r in synthetic_rows(ctx)
        if not r["Collector number"].isdigit()
    ]
    return bool(hits), f"promo collector numbers: {hits or 'none'}"


def check_per_format_pools(ctx):
    problems, evidence = [], []
    for rel, want in [
        ("collections/synthetic-kitchen20-pool.csv", "Uncharted Haven"),
        ("collections/synthetic-standard-pool.csv", None),
    ]:
        raw = ctx.path(rel).read_bytes().decode("utf-8-sig")
        header = next(csv.reader(io.StringIO(raw)))
        if header != MANABOX_HEADER:
            problems.append(f"{rel}: header differs from the ManaBox 18-column header")
            continue
        rows = list(csv.DictReader(io.StringIO(raw)))
        if len(rows) < 13:
            problems.append(f"{rel}: only {len(rows)} rows — not a shaped pool")
        if want and not any(r["Name"] == want for r in rows):
            problems.append(f"{rel}: missing {want}")
        if want is None and not any(r["Quantity"] == "4" for r in rows):
            problems.append(f"{rel}: no playset (Quantity 4) rows")
        evidence.append(f"{rel}: {len(rows)} rows, exact ManaBox header")
    return not problems, "; ".join(problems or evidence)


# --- Registry: exact expectation text -> fixed predicate --------------------
# Keys are pinned verbatim to the strings in evals.json; editing a wording
# means editing both, deliberately. Unregistered expectations are soft.

EXPECTATION_CHECKS = {
    "The realism fixture collections/real-collection.csv parses header-keyed as CSV with exactly 577 data rows.":
        check_realism_row_count,
    "A synthetic Collection row carries the etched Foil value the real Export lacks.":
        check_etched_foil,
    "Synthetic Collection rows carry non-English Language codes the real Export lacks, including the disputed zhs.":
        check_non_english_languages,
    "A synthetic Collection row carries a promo collector number (letter-suffixed or starred) the real Export lacks.":
        check_promo_collector_numbers,
    "Per-Format shaped pool Collections cover Kitchen 20 (Uncharted Haven beside mono-white candidates) and Standard (playset quantities), parsing with the full ManaBox header.":
        check_per_format_pools,
}


# --- Runner -----------------------------------------------------------------

def load_cases():
    data = json.loads((EVALS_DIR / "evals.json").read_text(encoding="utf-8"))
    return data["skill_name"], data["evals"]


def case_name(case):
    return CASE_NAMES.get(case["id"], f"eval-{case['id']}")


def grade_case(case, ctx, out_dir):
    """Grade one case's mechanical expectations; return (all_passed, lines)."""
    name = case_name(case)
    graded, soft, lines = [], [], [f"## {name} (eval id {case['id']})"]
    for text in case["expectations"]:
        checker = EXPECTATION_CHECKS.get(text)
        if checker is None:
            soft.append(text)
            lines.append(f"soft   — {text}")
            continue
        try:
            passed, evidence = checker(ctx)
        except Exception as exc:  # a crashed predicate is a red, with evidence
            passed, evidence = False, f"predicate raised {type(exc).__name__}: {exc}"
        graded.append({"text": text, "passed": passed, "evidence": evidence})
        lines.append(f"{'green' if passed else 'RED  '}  — {text}")
        if not passed:
            lines.append(f"         evidence: {evidence}")

    passed_n = sum(1 for e in graded if e["passed"])
    failed_n = len(graded) - passed_n
    case_dir = out_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "eval_metadata.json").write_text(
        json.dumps(
            {
                "eval_id": case["id"],
                "eval_name": name,
                "prompt": case["prompt"],
                "assertions": list(case["expectations"]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (case_dir / "grading.json").write_text(
        json.dumps(
            {
                "expectations": graded,
                "summary": {
                    "passed": passed_n,
                    "failed": failed_n,
                    "total": len(graded),
                    "pass_rate": round(passed_n / len(graded), 4) if graded else 0.0,
                },
                "soft_expectations": soft,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines.append(
        f"{passed_n}/{len(graded)} mechanical expectations green"
        + (f"; {len(soft)} soft (dev-time judgment)" if soft else "")
    )
    return failed_n == 0, lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", help="run only the case with this name or id")
    parser.add_argument(
        "--fixture-root",
        default=str(EVALS_DIR / "fixtures"),
        help="fixture tree to grade (default: evals/fixtures)",
    )
    parser.add_argument(
        "--out",
        default=str(EVALS_DIR / "results"),
        help="where per-case results land (default: evals/results)",
    )
    args = parser.parse_args(argv)

    skill_name, cases = load_cases()
    if args.case:
        cases = [
            c for c in cases
            if args.case in (str(c["id"]), case_name(c))
        ]
        if not cases:
            print(f"no eval case named {args.case!r}", file=sys.stderr)
            return 2

    ctx = Context(args.fixture_root)
    out_dir = pathlib.Path(args.out)
    print(f"# {skill_name} offline eval run")
    all_green = True
    for case in cases:
        ok, lines = grade_case(case, ctx, out_dir)
        all_green = all_green and ok
        print()
        print("\n".join(lines))

    print()
    print("GREEN — offline eval run passed" if all_green else "RED — offline eval run failed")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
