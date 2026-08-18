#!/usr/bin/env python3
"""tutor Review assembler — the mechanical half of Review (issue #55).

Judgment happens exactly once, at the Finding level, inside the two axis
passes (Standards, Brief). Everything above Findings is arithmetic (ADR
0006), and this script is that arithmetic: it takes each axis's Findings as
data, computes the Verdicts — any blocker makes the axis ``rebuild``, only
notes ``playable``, clean ``ship``, overall is the worst axis — and emits
the Review Block with the axes side by side, Standards first, Brief second,
never merged or reranked. No judgment is added here, so the same Findings
always assemble to the same bytes.

Findings input, one JSON array per axis. Each Finding is an object with
exactly: ``severity`` ("blocker" or "note"), ``cards`` (the card names it
judges, at least one), ``problem`` (the judgment), and at most one
suggestion — ``swap`` (an owned card) or ``maybeboard`` (an unowned
candidate). Anything else is unusable input: re-emit the Findings rather
than let a malformed judgment slip through as prose.

Usage:
    assemble_review.py --deck-name NAME --standards FILE
                       (--brief FILE | --no-brief)
                       [--date YYYY-MM-DD] [--out FILE]

``--no-brief`` is the Standards-only path: the Brief axis reports
"no Brief available" and the overall Verdict is the Standards axis alone.
The Block goes to stdout (or --out); exit 0 assembled, 2 unusable input.
Stdlib only.
"""

import argparse
import json
import sys
from datetime import date

SEVERITIES = ("blocker", "note")
VERDICT_ORDER = ("ship", "playable", "rebuild")


def unusable(message):
    print(message, file=sys.stderr)
    sys.exit(2)


REQUIRED_KEYS = {"severity", "cards", "problem"}
SUGGESTION_KEYS = {"swap", "maybeboard"}


def validate_finding(entry, axis, position):
    """The Finding shape, enforced: severity + named cards + the problem +
    at most one suggestion, nothing else."""
    where = f"{axis} Finding {position}"
    if not isinstance(entry, dict):
        unusable(f"{where} is not an object")
    unknown = sorted(set(entry) - REQUIRED_KEYS - SUGGESTION_KEYS)
    if unknown:
        unusable(f"{where} carries unknown keys {unknown} — a Finding is "
                 "severity, cards, problem, and at most one suggestion "
                 "(swap or maybeboard)")
    missing = sorted(REQUIRED_KEYS - set(entry))
    if missing:
        unusable(f"{where} lacks {missing}")
    if entry["severity"] not in SEVERITIES:
        unusable(f"{where} severity {entry['severity']!r} is not one of "
                 f"{'/'.join(SEVERITIES)}")
    cards = entry["cards"]
    if (not isinstance(cards, list) or not cards
            or not all(isinstance(c, str) and c.strip() for c in cards)):
        unusable(f"{where} must name at least one card in cards")
    if not isinstance(entry["problem"], str) or not entry["problem"].strip():
        unusable(f"{where} states no problem")
    suggestions = sorted(SUGGESTION_KEYS & set(entry))
    if len(suggestions) > 1:
        unusable(f"{where} carries {suggestions} — at most one suggestion, "
                 "an owned swap or an unowned Maybeboard candidate")
    for key in suggestions:
        if not isinstance(entry[key], str) or not entry[key].strip():
            unusable(f"{where} {key} suggestion names no card")


def load_findings(path, axis):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        unusable(f"cannot read the {axis} Findings: {exc}")
    except json.JSONDecodeError as exc:
        unusable(f"the {axis} Findings are not JSON: {exc}")
    if not isinstance(data, list):
        unusable(f"the {axis} Findings must be a JSON array of Findings")
    for position, entry in enumerate(data, start=1):
        validate_finding(entry, axis, position)
    return data


def axis_verdict(findings):
    """The arithmetic: any blocker -> rebuild, only notes -> playable,
    clean -> ship. Counts every Finding, including any past the display cap."""
    if any(f["severity"] == "blocker" for f in findings):
        return "rebuild"
    if findings:
        return "playable"
    return "ship"


def render_finding(entry):
    line = (f"{entry['severity']} — {'; '.join(entry['cards'])} — "
            f"{entry['problem']}")
    if "swap" in entry:
        line += f" — swap: {entry['swap']}"
    if "maybeboard" in entry:
        line += f" — maybeboard: {entry['maybeboard']}"
    return line


DISPLAY_CAP = 5


def rest_summary(rest):
    """The one-line mechanical summary of the Findings past the cap: counts
    by severity plus the cards they name — no fresh judgment, only what the
    trimmed Findings already say."""
    counts = []
    for severity in SEVERITIES:
        n = sum(1 for f in rest if f["severity"] == severity)
        if n:
            counts.append(f"{n} more {severity}{'s' if n > 1 else ''}")
    cards = []
    for entry in rest:
        cards += [c for c in entry["cards"] if c not in cards]
    return f"rest: {', '.join(counts)} — {'; '.join(cards)}"


def render_axis(name, findings):
    """One axis section: its own verdict line, then its Findings — at most
    five, worst first (blockers before notes, stable within a severity) —
    and a one-line summary of the rest when the cap trims any."""
    ordered = sorted(findings, key=lambda f: f["severity"] != "blocker")
    lines = [f"{name}: {axis_verdict(findings)}"]
    lines += [render_finding(entry) for entry in ordered[:DISPLAY_CAP]]
    if len(ordered) > DISPLAY_CAP:
        lines.append(rest_summary(ordered[DISPLAY_CAP:]))
    return lines


def assemble(deck_name, run_date, standards, brief):
    """The Review Block: deck:/date: reference lines, one overall verdict:
    line, then one section per axis — Standards first, Brief second."""
    verdicts = [axis_verdict(standards)]
    if brief is not None:
        verdicts.append(axis_verdict(brief))
    overall = max(verdicts, key=VERDICT_ORDER.index)

    out = [f"deck: {deck_name}", f"date: {run_date}", f"verdict: {overall}", ""]
    out += render_axis("standards", standards)
    out.append("")
    if brief is None:
        out.append("brief: no Brief available")
    else:
        out += render_axis("brief", brief)
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="Assemble a tutor Review Block from per-axis Findings.")
    ap.add_argument("--deck-name", required=True,
                    help="the reviewed Deck's name, for the deck: line")
    ap.add_argument("--standards", required=True,
                    help="Standards-axis Findings (JSON array)")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--brief", help="Brief-axis Findings (JSON array)")
    group.add_argument("--no-brief", action="store_true",
                       help="no Brief exists: Standards-only review")
    ap.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="date for the date: line (default: today), "
                         "for byte-stable output")
    ap.add_argument("--out", help="write the Review Block here instead of stdout")
    args = ap.parse_args()

    standards = load_findings(args.standards, "standards")
    brief = None if args.no_brief else load_findings(args.brief, "brief")
    run_date = date.fromisoformat(args.date) if args.date else date.today()

    block = assemble(args.deck_name, run_date.isoformat(), standards, brief)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(block)
        print(f"Review Block written to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(block)


if __name__ == "__main__":
    main()
