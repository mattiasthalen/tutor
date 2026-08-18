#!/usr/bin/env python3
"""Validate a Brief Block (issue #52).

The one authority on whether a Brief Block is valid — the brief skill runs it
before writing a Brief to the Collection home, and the offline eval harness
wraps it rather than re-implementing the grammar.

A Brief Block is flat ``key: value`` lines (CONTEXT.md, spec #46): canonical
keys ``name``, ``format``, ``centerpiece``, ``identity``, ``play variant``,
``power``, ``constraint`` (repeatable), ``donor`` (repeatable; ``donor: all``
frees the whole Collection), ``notes``. Only ``format`` is required. No
``budget:`` key exists, and Kitchen 20 carries no Power — the Format pins it,
so ``power:`` beside ``format: kitchen 20`` is invalid. Blocks are recognized
by shape alone — no sentinels, no version markers — so anything that is not a
canonical line is invalid.

Usage:
    validate_brief.py BRIEF_FILE [--collection EXPORT_CSV]

With ``--collection``, every ``donor:`` value must name a Deck recognized
from the Export's deck rows (Binder Type ``deck`` -> Binder Name), or be the
literal ``all``.

Exit status: 0 valid, 1 invalid (problems listed on stdout), 2 unusable input.
Stdlib only.
"""

import argparse
import csv
import io
import pathlib
import re
import sys

CANONICAL_KEYS = [
    "name", "format", "centerpiece", "identity", "play variant",
    "power", "constraint", "donor", "notes",
]
REPEATABLE_KEYS = {"constraint", "donor"}

# Power is the shared 1-5 ladder; free text may trail the number ("3,
# battlecruiser feel") but the number is canonical. Absent defaults to 2
# downstream, so an omitted power: line is valid.
POWER_VALUE = re.compile(r"^[1-5](?:[\s,].*)?$")


def parse_brief(text):
    """Parse Brief Block text; return (entries, problems).

    entries are (key, value) in file order; problems are human-readable
    strings, empty when the Block is grammatically valid.
    """
    entries, problems = [], []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            problems.append(f"line {number}: not a 'key: value' line: {line!r}")
            continue
        if key == "budget":
            problems.append(
                f"line {number}: no budget: key exists in the Brief grammar — "
                "tutor builds only from the Collection; the Maybeboard is the valve"
            )
            continue
        if key not in CANONICAL_KEYS:
            problems.append(
                f"line {number}: {key!r} is not a canonical Brief key "
                f"(canonical: {', '.join(CANONICAL_KEYS)})"
            )
            continue
        if not value.strip():
            problems.append(f"line {number}: {key!r} has an empty value")
            continue
        entries.append((key, value.strip()))

    keys = [k for k, _ in entries]
    if "format" not in keys:
        problems.append("missing the required 'format:' line — the only required key")
    for key in dict.fromkeys(keys):
        if key not in REPEATABLE_KEYS and keys.count(key) > 1:
            problems.append(
                f"{key!r} repeats {keys.count(key)} times — only "
                f"{sorted(REPEATABLE_KEYS)} are repeatable"
            )
    for key, value in entries:
        if key == "power" and not POWER_VALUE.match(value):
            problems.append(
                f"power: {value!r} — Power is a 1-5 number (Commander reads it "
                "as the official Bracket); free text may trail the number"
            )
    # Kitchen 20 carries no Power — the Format pins it (spec #46). Values are
    # already stripped; formats compare case-insensitively, as elsewhere.
    if any(k == "format" and v.lower() == "kitchen 20" for k, v in entries):
        for key, value in entries:
            if key == "power":
                problems.append(
                    f"power: {value!r} — Kitchen 20 carries no Power (the "
                    "Format pins it); drop the power: line"
                )
    return entries, problems


def recognized_decks(collection_path):
    """The Deck names the Export's deck rows carry: Binder Type ``deck`` ->
    Binder Name. Header-keyed, BOM-tolerant, malformed rows skipped."""
    raw = pathlib.Path(collection_path).read_bytes()
    decks = set()
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if (row.get("Binder Type") or "").strip() == "deck":
            name = (row.get("Binder Name") or "").strip()
            if name:
                decks.add(name)
    return decks


def check_donors(entries, collection_path):
    """Every donor: value must be the literal ``all`` or name a recognized
    Deck; returns problems."""
    decks = recognized_decks(collection_path)
    problems = []
    for key, value in entries:
        if key != "donor" or value == "all":
            continue
        if value not in decks:
            problems.append(
                f"donor: {value!r} names no Deck recognized from the Export's "
                f"deck rows (recognized: {', '.join(sorted(decks)) or 'none'}; "
                "or 'donor: all' to free the whole Collection)"
            )
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("brief", help="Brief Block file to validate")
    parser.add_argument(
        "--collection",
        help="ManaBox Export CSV; donor: values must name its Deck rows",
    )
    args = parser.parse_args(argv)

    brief_path = pathlib.Path(args.brief)
    try:
        text = brief_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"unusable — cannot read {brief_path}: {exc}")
        return 2

    entries, problems = parse_brief(text)

    if args.collection:
        try:
            problems += check_donors(entries, args.collection)
        except OSError as exc:
            print(f"unusable — cannot read {args.collection}: {exc}")
            return 2

    if problems:
        for problem in problems:
            print(f"invalid — {problem}")
        return 1

    keys = [k for k, _ in entries]
    summary = ", ".join(
        f"{keys.count(key)} {key}" if keys.count(key) > 1 else key
        for key in CANONICAL_KEYS
        if key in keys
    )
    print(f"valid — Brief Block: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
