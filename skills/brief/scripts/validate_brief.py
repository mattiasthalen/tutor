#!/usr/bin/env python3
"""Validate a Brief Block or a Table Brief Block (issues #52, #59).

The one authority on whether a Brief-shaped Block is valid — the brief skill
runs it before writing to the Collection home, and the offline eval harness
wraps it rather than re-implementing the grammar. Blocks are recognized by
shape alone — no sentinels, no version markers — so anything that is not a
canonical line is invalid.

A Brief Block is flat ``key: value`` lines (CONTEXT.md, spec #46): canonical
keys ``name``, ``format``, ``centerpiece``, ``identity``, ``play variant``,
``power``, ``constraint`` (repeatable), ``donor`` (repeatable; ``donor: all``
frees the whole Collection), ``notes``. Only ``format`` is required. No
``budget:`` key exists, and Kitchen 20 carries no Power — the Format pins it,
so ``power:`` beside ``format: kitchen 20`` is invalid.

A Table Brief Block shares the flat grammar and is recognized by its
``table:`` anchor plus ``seat:`` lines (spec #46, Tables): canonical keys
``table``, ``format`` (one Format per Table), ``play variant``, ``power``,
``constraint`` (repeatable), ``donor`` (repeatable), ``notes``, ``seat``
(repeatable, two Seats minimum). Seat grammar ``seat: [role —] <deck
name>[, power N]`` — only a trailing ``, power N`` is the override; other
commas belong to the deck name. The Table Brief is an index that never
embeds the per-Deck Briefs, so per-Deck keys (``name``, ``centerpiece``,
``identity``) are invalid in it, and a ``donor:`` value naming a Seat's deck
is invalid — table-mates are never Donor Decks.

Usage:
    validate_brief.py BRIEF_FILE [--collection EXPORT_CSV]
                      [--seat-brief BRIEF_FILE ...]

With ``--collection``, every ``donor:`` value must name a Deck recognized
from the Export's deck rows (Binder Type ``deck`` -> Binder Name), or be the
literal ``all``.

With ``--seat-brief`` (repeatable; the validated file must be a Table
Brief), the cross-Brief table checks run: every ``seat:`` deck name joins
exactly one provided Brief's ``name:``, every provided Brief is seated,
table-level power, constraints, play variant, and donors are copied into
each Seat's Brief, one Format holds across the Table — and the mechanical
declared-Power match: every Seat's effective Power (its seat-line override,
else the table's, else the shared default 2) equals its Brief's declared
Power.

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

# The Table Brief Block: same flat grammar, recognized by its table: anchor
# plus seat: lines. An index over per-Deck Briefs — per-Deck keys (name,
# centerpiece, identity) are embedding and invalid here.
TABLE_CANONICAL_KEYS = [
    "table", "format", "play variant", "power",
    "constraint", "donor", "notes", "seat",
]
TABLE_REPEATABLE_KEYS = {"constraint", "donor", "seat"}
PER_DECK_ONLY_KEYS = {"name", "centerpiece", "identity"}

# Recognized-but-banned keys, each refused with the sentence that explains
# itself: the Brief grammar has no budget: key, and the Table Brief is an
# index that embeds no per-Deck keys.
BRIEF_BANNED_KEYS = {
    "budget": "no budget: key exists in the Brief grammar — tutor builds "
              "only from the Collection; the Maybeboard is the valve",
}
TABLE_BANNED_KEYS = {
    key: f"{key!r} is a per-Deck Brief key — the Table Brief is an index "
         "that never embeds the per-Deck Briefs; it lives in the Seat's "
         "own Brief"
    for key in PER_DECK_ONLY_KEYS
}

# Power is the shared 1-5 ladder; free text may trail the number ("3,
# battlecruiser feel") but the number is canonical. Absent defaults to 2
# downstream, so an omitted power: line is valid.
POWER_VALUE = re.compile(r"^[1-5](?:[\s,].*)?$")

# A seat line's power override: exactly ", power N" trailing the deck name —
# any other comma belongs to the deck name ("Nicol Bolas, God-Pharaoh").
SEAT_POWER_SUFFIX = re.compile(r"^(.*?),\s*power\s+(\d+)\s*$")


def is_table_brief(text):
    """Shape-alone recognition: a flat line keyed ``table`` makes the Block a
    Table Brief."""
    return any(
        line.partition(":")[1] and line.partition(":")[0] == "table"
        for line in text.splitlines()
    )


def parse_seat(value):
    """Parse one seat: value — ``[role —] <deck name>[, power N]``.

    Returns (role, deck_name, power, problems): role and power are None when
    absent; problems are human-readable strings. The first " — " splits role
    from deck name (a deck name carrying " — " needs its role spelled so the
    split lands right); only a trailing ", power N" is the override.
    """
    problems = []
    role, rest = None, value
    if " — " in value:
        head, _, tail = value.partition(" — ")
        role, rest = head.strip(), tail.strip()
        if not role:
            problems.append("an empty role before ' — '")
    power = None
    m = SEAT_POWER_SUFFIX.match(rest)
    if m:
        rest = m.group(1).strip()
        if re.fullmatch(r"[1-5]", m.group(2)):
            power = int(m.group(2))
        else:
            problems.append(
                f"power {m.group(2)} is off the ladder — a seat override is "
                "', power N' with N a 1-5 number"
            )
    deck = rest.strip()
    if not deck:
        problems.append("no deck name — a seat is '[role —] <deck name>[, power N]'")
    return role, deck, power, problems


def parse_flat_lines(text, canonical, block, banned):
    """The flat-line walk both Brief shapes share (parse_brief and
    parse_table_brief): skip blank lines, demand ``key: value``, refuse the
    recognized-but-banned keys with their own sentences, hold keys to the
    canonical set, refuse empty values. Returns (numbered, problems) where
    numbered is (line number, key, stripped value) in file order."""
    numbered, problems = [], []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            problems.append(f"line {number}: not a 'key: value' line: {line!r}")
            continue
        if key in banned:
            problems.append(f"line {number}: {banned[key]}")
            continue
        if key not in canonical:
            problems.append(
                f"line {number}: {key!r} is not a canonical {block} key "
                f"(canonical: {', '.join(canonical)})"
            )
            continue
        if not value.strip():
            problems.append(f"line {number}: {key!r} has an empty value")
            continue
        numbered.append((number, key, value.strip()))
    return numbered, problems


def is_kitchen20(entries):
    """Kitchen 20 by the format: line — the Format that carries no Power
    because the Format pins it (spec #46). Values are already stripped;
    formats compare case-insensitively, as elsewhere."""
    return any(k == "format" and v.lower() == "kitchen 20" for k, v in entries)


def shared_entry_problems(entries, repeatable, format_reason):
    """The entry checks both Brief shapes share: the required format: line,
    non-repeatable keys appearing once, power: on the 1-5 ladder, and the
    Kitchen-20 ban on power: lines. Table-only checks — the seat minimum,
    duplicate Seats, seat overrides, donors naming Seats — stay in
    parse_table_brief."""
    problems = []
    keys = [k for k, _ in entries]
    if "format" not in keys:
        problems.append(f"missing the required 'format:' line — {format_reason}")
    for key in dict.fromkeys(keys):
        if key not in repeatable and keys.count(key) > 1:
            problems.append(
                f"{key!r} repeats {keys.count(key)} times — only "
                f"{sorted(repeatable)} are repeatable"
            )
    for key, value in entries:
        if key == "power" and not POWER_VALUE.match(value):
            problems.append(
                f"power: {value!r} — Power is a 1-5 number (Commander reads it "
                "as the official Bracket); free text may trail the number"
            )
    if is_kitchen20(entries):
        for key, value in entries:
            if key == "power":
                problems.append(
                    f"power: {value!r} — Kitchen 20 carries no Power (the "
                    "Format pins it); drop the power: line"
                )
    return problems


def parse_table_brief(text):
    """Parse Table Brief Block text; return (entries, seats, problems).

    entries are (key, value) in file order; seats are (role, deck name,
    power override) in seat order — seat order is build order and contention
    priority; problems are human-readable strings, empty when the Block is
    grammatically valid.
    """
    numbered, problems = parse_flat_lines(
        text, TABLE_CANONICAL_KEYS, "Table Brief", TABLE_BANNED_KEYS)
    entries = [(key, value) for _number, key, value in numbered]
    seats = []
    for number, key, value in numbered:
        if key == "seat":
            role, deck, power, seat_problems = parse_seat(value)
            problems += [f"line {number}: seat: {p}" for p in seat_problems]
            seats.append((role, deck, power))

    problems += shared_entry_problems(entries, TABLE_REPEATABLE_KEYS,
                                      "one Format per Table")
    if len(seats) < 2:
        problems.append(
            f"{len(seats)} seat: line{'s' if len(seats) != 1 else ''} — a "
            "Table seats two Seats minimum"
        )
    seen = set()
    for _role, deck, _power in seats:
        if deck and deck in seen:
            problems.append(
                f"seat: {deck!r} fills two Seats — one physical Deck cannot "
                "sit twice at the same sitting"
            )
        seen.add(deck)
    # Kitchen 20 carries no Power on seat overrides either — the shared
    # checks above already refused the table-level power: lines.
    if is_kitchen20(entries):
        for _role, deck, power in seats:
            if power is not None:
                problems.append(
                    f"seat: {deck!r} overrides power {power} — Kitchen 20 "
                    "Seats carry no Power (the Format pins it)"
                )
    seat_decks = {deck for _role, deck, _power in seats}
    for key, value in entries:
        if key == "donor" and value in seat_decks:
            problems.append(
                f"donor: {value!r} names a Seat's deck — table-mates are "
                "never Donor Decks; reallocation is a human re-brief loop"
            )
    return entries, seats, problems


def parse_brief(text):
    """Parse Brief Block text; return (entries, problems).

    entries are (key, value) in file order; problems are human-readable
    strings, empty when the Block is grammatically valid.
    """
    numbered, problems = parse_flat_lines(
        text, CANONICAL_KEYS, "Brief", BRIEF_BANNED_KEYS)
    entries = [(key, value) for _number, key, value in numbered]
    problems += shared_entry_problems(entries, REPEATABLE_KEYS,
                                      "the only required key")
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


def first_value(entries, wanted):
    for key, value in entries:
        if key == wanted:
            return value
    return None


def all_values(entries, wanted):
    return [value for key, value in entries if key == wanted]


def power_number(value):
    """The canonical 1-5 number of a power: value, or None. Absent Power
    reads as the shared default 2 downstream."""
    if value is None:
        return 2
    if POWER_VALUE.match(value):
        return int(value[0])
    return None


def check_table_seats(table_entries, seats, seat_briefs, collection=None):
    """The cross-Brief table checks over (file name, per-Deck Brief text)
    pairs: the seat join, the copy-down of table-level power/constraints/
    play variant/donors, one Format per Table, table-mates never Donor
    Decks — and the mechanical declared-Power match. Returns problems."""
    problems = []
    table_format = first_value(table_entries, "format") or ""
    table_variant = first_value(table_entries, "play variant")
    table_power = power_number(first_value(table_entries, "power"))
    table_constraints = all_values(table_entries, "constraint")
    table_donors = all_values(table_entries, "donor")
    kitchen = table_format.lower() == "kitchen 20"
    seat_decks = {deck for _role, deck, _power in seats}

    by_name = {}
    for file_name, text in seat_briefs:
        if is_table_brief(text):
            problems.append(
                f"{file_name}: is itself a Table Brief — a seat: deck name "
                "joins a per-Deck Brief's name: line, and the Table Brief "
                "never embeds or nests another"
            )
            continue
        entries, brief_problems = parse_brief(text)
        problems += [f"{file_name}: {p}" for p in brief_problems]
        if collection:
            problems += [f"{file_name}: {p}" for p in check_donors(entries, collection)]
        name = first_value(entries, "name")
        if name is None:
            problems.append(
                f"{file_name}: carries no name: line — the seat join needs one"
            )
        elif name in by_name:
            problems.append(
                f"{file_name}: name: {name!r} repeats {by_name[name][0]}'s — "
                "each Seat joins its own Brief"
            )
        else:
            by_name[name] = (file_name, entries)

    for role, deck, override in seats:
        if deck not in by_name:
            problems.append(
                f"seat: {deck!r} joins no provided Brief — the deck name "
                "joins that Brief's name: line"
            )
            continue
        file_name, entries = by_name.pop(deck)
        seat_format = first_value(entries, "format") or ""
        if seat_format.lower() != table_format.lower():
            problems.append(
                f"{file_name}: format: {seat_format!r} differs from the "
                f"table's {table_format!r} — one Format per Table"
            )
        if table_variant is not None:
            seat_variant = first_value(entries, "play variant")
            if (seat_variant or "").lower() != table_variant.lower():
                problems.append(
                    f"{file_name}: the table's play variant: {table_variant!r} "
                    "is not copied into the Seat's Brief — every build session "
                    "reads only its own Brief"
                )
        seat_constraints = all_values(entries, "constraint")
        for constraint in table_constraints:
            if constraint not in seat_constraints:
                problems.append(
                    f"{file_name}: the table's constraint: {constraint!r} is "
                    "not copied into the Seat's Brief — every build session "
                    "reads only its own Brief"
                )
        seat_donors = all_values(entries, "donor")
        for donor in table_donors:
            if donor not in seat_donors:
                problems.append(
                    f"{file_name}: the table's donor: {donor!r} is not copied "
                    "into the Seat's Brief — every build session reads only "
                    "its own Brief"
                )
        for donor in seat_donors:
            # A Seat's Brief may free its own Deck's rows (the ordinary
            # Upgrade pattern) — never a table-mate's.
            if donor in seat_decks - {deck}:
                problems.append(
                    f"{file_name}: donor: {donor!r} names a table-mate — "
                    "table-mates are never Donor Decks; reallocation is a "
                    "human re-brief loop"
                )
        if not kitchen:
            effective = override if override is not None else table_power
            declared_value = first_value(entries, "power")
            declared = power_number(declared_value)
            if declared is None or effective is None:
                continue  # the per-file grammar problem already reported
            if declared != effective:
                source = (
                    f"its seat line's override {override}" if override is not None
                    else f"the table's {table_power}"
                )
                problems.append(
                    f"seat: {deck!r} ({file_name}) declares Power {declared} "
                    f"but its effective Power is {effective} ({source}) — "
                    "the declared-Power match"
                )

    for name, (file_name, _entries) in by_name.items():
        problems.append(
            f"{file_name}: name: {name!r} fills no seat: line of the Table "
            "Brief"
        )
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("brief", help="Brief or Table Brief Block file to validate")
    parser.add_argument(
        "--collection",
        help="ManaBox Export CSV; donor: values must name its Deck rows",
    )
    parser.add_argument(
        "--seat-brief", action="append", default=[], metavar="BRIEF",
        help="a Seat's per-Deck Brief file (repeatable; the validated file "
             "must be a Table Brief) — runs the seat join, the copy-down, "
             "and the declared-Power match",
    )
    args = parser.parse_args(argv)

    brief_path = pathlib.Path(args.brief)
    try:
        text = brief_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"unusable — cannot read {brief_path}: {exc}")
        return 2

    table = is_table_brief(text)
    if table:
        entries, seats, problems = parse_table_brief(text)
    else:
        if args.seat_brief:
            print(
                f"unusable — --seat-brief given but {brief_path} carries no "
                "table: anchor; the seat checks run over a Table Brief"
            )
            return 2
        entries, problems = parse_brief(text)

    if args.seat_brief:
        seat_briefs = []
        for seat_path in args.seat_brief:
            path = pathlib.Path(seat_path)
            try:
                seat_briefs.append((path.name, path.read_text(encoding="utf-8-sig")))
            except OSError as exc:
                print(f"unusable — cannot read {path}: {exc}")
                return 2
        try:
            problems += check_table_seats(
                entries, seats, seat_briefs, collection=args.collection
            )
        except OSError as exc:
            print(f"unusable — cannot read {args.collection}: {exc}")
            return 2

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
    canonical = TABLE_CANONICAL_KEYS if table else CANONICAL_KEYS
    summary = ", ".join(
        f"{keys.count(key)} {key}" if keys.count(key) > 1 else key
        for key in canonical
        if key in keys
    )
    block = "Table Brief" if table else "Brief"
    print(f"valid — {block} Block: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
