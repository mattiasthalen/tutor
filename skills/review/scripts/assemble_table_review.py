#!/usr/bin/env python3
"""tutor Table Review assembler — the mechanical half of Table Review
(issue #59).

The Table Review judges the finished sitting as a whole, once every Seat is
built. Judgment happens exactly once, at the Finding level, inside the three
axis passes — power spread, play patterns, contention fallout — and
everything above Findings is arithmetic (ADR 0006, unchanged): any blocker
makes an axis ``rebuild``, only notes ``playable``, clean ``ship``, and the
overall Verdict is the worst axis. The verdict arithmetic, severity
vocabulary, and display cap are imported from ``assemble_review.py`` (same
skill) — one arithmetic, never re-derived — so a Table Review and a Deck
Review can never disagree about what a blocker means.

Findings input, one JSON array per axis. Each Table Finding is an object
with exactly: ``severity`` ("blocker" or "note"), ``seats`` (the Seat deck
names it judges, at least one), ``cards`` (the card names it judges, at
least one — findings name Seats and cards), ``problem`` (the judgment), and
at most one suggestion — ``swap`` (an owned card) or ``maybeboard`` (an
unowned candidate). Anything else is unusable input: re-emit the Findings
rather than let a malformed judgment slip through as prose.

The emitted Table Review Block: ``table:`` and ``date:`` reference lines,
one overall ``verdict:`` line, then one section per axis — power spread,
play patterns, contention fallout, side by side, never merged or reranked —
each with its own verdict and at most five Findings worst first plus a
one-line summary of the rest. Recognized by shape alone; embeds nothing.

Usage:
    assemble_table_review.py --table-name NAME --power-spread FILE
                             --play-patterns FILE --contention FILE
                             [--date YYYY-MM-DD] [--out FILE]

The Block goes to stdout (or --out); exit 0 assembled, 2 unusable input.
Stdlib only.
"""

import argparse
import json
import sys
from datetime import date

# One arithmetic: the Deck Review assembler's, imported from the same skill
# directory (the ship script imports availability the same way).
from assemble_review import (
    DISPLAY_CAP,
    SEVERITIES,
    VERDICT_ORDER,
    axis_verdict,
    unusable,
)

# The three Table Review axes, in Block order (spec #46, Tables).
AXES = ("power spread", "play patterns", "contention fallout")

# The four helpers below — validate_finding, load_findings, rest_summary,
# render_axis — are deliberate mirrors of assemble_review.py's (same skill),
# kept in lockstep by hand: validate_finding and rest_summary add the seats
# key beside cards; load_findings and render_axis differ only by resolving
# to the table-shaped validator and renderer defined here. They are not
# parameterized and imported like the arithmetic above because the hook
# would have to live in the Deck assembler, whose bytes are pinned. Edit the
# two files together; the frozen side cannot carry its half of this note, so
# this one stands for the pair.

REQUIRED_KEYS = {"severity", "seats", "cards", "problem"}
SUGGESTION_KEYS = {"swap", "maybeboard"}


def name_list_ok(value):
    return (isinstance(value, list) and value
            and all(isinstance(item, str) and item.strip() for item in value))


def validate_finding(entry, axis, position):
    """The Table Finding shape, enforced: severity + named Seats + named
    cards + the problem + at most one suggestion, nothing else."""
    where = f"{axis} Finding {position}"
    if not isinstance(entry, dict):
        unusable(f"{where} is not an object")
    unknown = sorted(set(entry) - REQUIRED_KEYS - SUGGESTION_KEYS)
    if unknown:
        unusable(f"{where} carries unknown keys {unknown} — a Table Finding "
                 "is severity, seats, cards, problem, and at most one "
                 "suggestion (swap or maybeboard)")
    missing = sorted(REQUIRED_KEYS - set(entry))
    if missing:
        unusable(f"{where} lacks {missing}")
    if entry["severity"] not in SEVERITIES:
        unusable(f"{where} severity {entry['severity']!r} is not one of "
                 f"{'/'.join(SEVERITIES)}")
    if not name_list_ok(entry["seats"]):
        unusable(f"{where} must name at least one Seat in seats — findings "
                 "name Seats and cards")
    if not name_list_ok(entry["cards"]):
        unusable(f"{where} must name at least one card in cards — findings "
                 "name Seats and cards")
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


def render_finding(entry):
    line = (f"{entry['severity']} — seats: {'; '.join(entry['seats'])} — "
            f"cards: {'; '.join(entry['cards'])} — {entry['problem']}")
    if "swap" in entry:
        line += f" — swap: {entry['swap']}"
    if "maybeboard" in entry:
        line += f" — maybeboard: {entry['maybeboard']}"
    return line


def rest_summary(rest):
    """The one-line mechanical summary of the Findings past the cap: counts
    by severity plus the Seats and cards they name — no fresh judgment."""
    counts = []
    for severity in SEVERITIES:
        n = sum(1 for f in rest if f["severity"] == severity)
        if n:
            counts.append(f"{n} more {severity}{'s' if n > 1 else ''}")
    seats, cards = [], []
    for entry in rest:
        seats += [s for s in entry["seats"] if s not in seats]
        cards += [c for c in entry["cards"] if c not in cards]
    return (f"rest: {', '.join(counts)} — seats: {'; '.join(seats)} — "
            f"cards: {'; '.join(cards)}")


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


def assemble(table_name, run_date, findings_by_axis):
    """The Table Review Block: table:/date: reference lines, one overall
    verdict: line, then one section per axis in AXES order."""
    verdicts = [axis_verdict(findings_by_axis[axis]) for axis in AXES]
    overall = max(verdicts, key=VERDICT_ORDER.index)

    out = [f"table: {table_name}", f"date: {run_date}", f"verdict: {overall}"]
    for axis in AXES:
        out.append("")
        out += render_axis(axis, findings_by_axis[axis])
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="Assemble a tutor Table Review Block from per-axis Findings.")
    ap.add_argument("--table-name", required=True,
                    help="the reviewed Table's name, for the table: line")
    ap.add_argument("--power-spread", required=True,
                    help="power-spread-axis Findings (JSON array)")
    ap.add_argument("--play-patterns", required=True,
                    help="play-patterns-axis Findings (JSON array)")
    ap.add_argument("--contention", required=True,
                    help="contention-fallout-axis Findings (JSON array)")
    ap.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="date for the date: line (default: today), "
                         "for byte-stable output")
    ap.add_argument("--out", help="write the Table Review Block here instead "
                                  "of stdout")
    args = ap.parse_args()

    findings_by_axis = {
        "power spread": load_findings(args.power_spread, "power spread"),
        "play patterns": load_findings(args.play_patterns, "play patterns"),
        "contention fallout": load_findings(args.contention,
                                            "contention fallout"),
    }
    if args.date:
        try:
            run_date = date.fromisoformat(args.date)
        except ValueError:
            unusable(f"--date {args.date!r} is not a YYYY-MM-DD date")
    else:
        run_date = date.today()

    block = assemble(args.table_name, run_date.isoformat(), findings_by_axis)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(block)
        print(f"Table Review Block written to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(block)


if __name__ == "__main__":
    main()
