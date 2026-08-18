#!/usr/bin/env python3
"""tutor ship — the Deck Block in its ManaBox-importable shape (issue #54).

Build iterates on a working Deck Block; this script does the judgment-free
finishing so the shipped artifact is text ManaBox actually imports, per the
Block-formats decision (owner-verified: ManaBox accepts ``//`` comments and
reserves the four Board headers):

- first line ``// <name>``, Board headers only for the Boards present, in
  canonical order (Commander, Mainboard, Sideboard, Maybeboard),
- each nonbasic pinned to the exact owned printing — set code and collector
  number from the Export — with the fancier owned print chosen when several
  exist (Scryfall's finishes ladder: etched over foil over normal; ties break
  on set code then collector number), spilling across printings when one
  printing has too few copies so physical assembly matches card for card,
- optional inline ``// category`` comments preserved,
- basics lumped per name, last in each Board after a blank line,
- the Maybeboard as the wishlist Board: entries stay unpinned and may be
  unowned — the one place the collection-only rule bends,
- the short-form Fan Content footer line, exactly once (re-shipping a shipped
  Block is byte-identical: the round-trip is the identity).

A nonbasic outside the Maybeboard that the Collection does not own cannot be
pinned and refuses the run naming the card — the Deck draws only from the
Collection. A card missing from the Oracle is no failure here: the Oracle
only sharpens basic-land detection and multi-faced-name reading.

Usage:
    ship_deck.py --deck DECK_BLOCK --collection EXPORT_CSV
                 [--oracle ORACLE] [--out FILE]

Exit status: 0 shipped, 1 refused (the message names why), 2 unusable input.
Stdlib only, offline.
"""

import argparse
import csv
import json
import re
import sys

BOARD_ORDER = ("Commander", "Mainboard", "Sideboard", "Maybeboard")

# The five basic land names plus Wastes; the Oracle's type line is the
# authority when present, this set the fallback.
BASIC_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}

# Scryfall lists print finishes as nonfoil, foil, etched — read as the
# fancier-print ladder, later is fancier. ManaBox's Foil column uses
# "normal" for nonfoil.
FINISH_RANK = {"normal": 0, "": 0, "foil": 1, "etched": 2}

# Deck-line grammar, mirroring the fixed runner's (check_deck.py).
PIN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]{2,5})\)\s+(\S+)$")
LUMP = re.compile(r"^(\d+)\s+([^(]+)$")

# The WotC Fan Content Policy short form (NOTICE, spec #46), carried as a
# ManaBox-safe comment line on every generated deck artifact.
FOOTER = ("// tutor is unofficial Fan Content permitted under the Fan Content "
          "Policy. Not approved/endorsed by Wizards. Portions of the materials "
          "used are property of Wizards of the Coast. ©Wizards of the Coast LLC.")


def refuse(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def unusable(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def load_printings(path):
    """Owned printings by name from the Export: {name: [(set, number, foil,
    quantity), ...]}, header-keyed, BOM-tolerant, malformed rows skipped."""
    printings = {}
    try:
        handle = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        unusable(f"cannot read the Export: {exc}")
    with handle:
        for row in csv.DictReader(handle):
            name = (row.get("Name") or "").strip()
            set_code = (row.get("Set code") or "").strip()
            number = (row.get("Collector number") or "").strip()
            try:
                quantity = int(row.get("Quantity", 1))
            except (TypeError, ValueError):
                continue
            if not name or not set_code or not number:
                continue
            foil = (row.get("Foil") or "").strip().lower()
            printings.setdefault(name, []).append((set_code, number, foil, quantity))
    return printings


def load_oracle_names(path):
    """(names, basics) from the Oracle: every card name, and the names whose
    type line starts Basic Land. Either Oracle form (ADR 0007)."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        unusable(f"cannot read the Oracle: {exc}")
    records = (json.loads(text) if text.lstrip().startswith("[")
               else [json.loads(line) for line in text.splitlines() if line.strip()])
    names, basics = set(), set()
    for record in records:
        if "name" not in record:
            continue
        names.add(record["name"])
        if str(record.get("type_line", "")).startswith("Basic Land"):
            basics.add(record["name"])
    return names, basics


def parse_deck(text, known_names):
    """(title, boards) from a working Deck Block. boards maps Board name to
    entry lists of (qty, name, comment); cards before any header land in
    Mainboard. A bare line holding " // " is a multi-faced name when the
    whole remainder is a known card name (Oracle or Export), an inline
    comment otherwise — the pin anchors pinned lines either way. A previously
    appended Fan Content footer is recognized and dropped (re-adding it is
    the shipper's job, exactly once)."""
    title, boards = None, {}
    board = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == FOOTER:
            continue
        if line.startswith("//"):
            head = line[2:].strip()
            if head in BOARD_ORDER:
                board = head
                boards.setdefault(board, [])
            elif title is None:
                title = head
            continue
        stripped, comment = line, None
        if " // " in line:
            head, _, tail = line.rpartition(" // ")
            stripped, comment = head.strip(), tail.strip()
        m = PIN.match(line)
        if m:
            qty, name, comment = int(m.group(1)), m.group(2).strip(), None
        else:
            m = PIN.match(stripped)
            if m:
                qty, name = int(m.group(1)), m.group(2).strip()
            else:
                bare = LUMP.match(line)
                if bare and bare.group(2).strip() in known_names:
                    qty, name, comment = int(bare.group(1)), bare.group(2).strip(), None
                else:
                    bare = LUMP.match(stripped)
                    if not bare:
                        refuse(f"unreadable Deck line: {raw.strip()!r} — a card line is "
                               "'<qty> <name>' with an optional '(SET) number' pin and "
                               "one optional trailing '// comment'")
                    qty, name = int(bare.group(1)), bare.group(2).strip()
        boards.setdefault(board or "Mainboard", []).append((qty, name, comment))
    if title is None:
        refuse("the Deck Block has no '// <name>' title line — nothing to ship")
    return title, boards


def pin_lines(name, quantity, comment, printings):
    """The pinned line(s) for one nonbasic: fancier owned print first
    (etched over foil over normal, then set code and collector number),
    spilling to the next printing when one has too few copies."""
    owned = printings.get(name)
    if not owned:
        refuse(f"{name} is not in the Collection — the Deck draws only from the "
               "Collection; unowned candidates belong on the Maybeboard")
    merged = {}
    for set_code, number, foil, qty in owned:
        key = (set_code, number, foil)
        merged[key] = merged.get(key, 0) + qty
    ranked = sorted(
        merged.items(),
        key=lambda item: (-FINISH_RANK.get(item[0][2], 0), item[0][0], item[0][1]),
    )
    lines, remaining = [], quantity
    for (set_code, number, _foil), qty in ranked:
        if remaining <= 0:
            break
        take = min(remaining, qty)
        suffix = f" // {comment}" if comment else ""
        lines.append(f"{take} {name} ({set_code}) {number}{suffix}")
        remaining -= take
    if remaining > 0:
        refuse(f"{name}: the Deck wants {quantity}, the Collection holds "
               f"{quantity - remaining} — the Deck draws only from the Collection")
    return lines


def merge_entries(entries):
    """Sum quantities per (name, comment), keeping first-seen comments."""
    order, counts, comments = [], {}, {}
    for qty, name, comment in entries:
        if name not in counts:
            order.append(name)
            counts[name] = 0
            comments[name] = comment
        counts[name] += qty
        if comments[name] is None:
            comments[name] = comment
    return [(counts[name], name, comments[name]) for name in order]


def ship(text, printings, oracle_names, oracle_basics):
    known = set(printings) | oracle_names
    title, boards = parse_deck(text, known)

    def is_basic(name):
        if name in oracle_names:
            return name in oracle_basics
        return name in BASIC_NAMES

    out = [f"// {title}"]
    for board in BOARD_ORDER:
        if board not in boards:
            continue
        out.append("")
        out.append(f"// {board}")
        entries = merge_entries(boards[board])
        if board == "Maybeboard":
            # The wishlist Board: unpinned, possibly unowned, comments kept.
            for qty, name, comment in sorted(entries, key=lambda e: e[1].casefold()):
                suffix = f" // {comment}" if comment else ""
                out.append(f"{qty} {name}{suffix}")
            continue
        spells = [e for e in entries if not is_basic(e[1])]
        basics = [e for e in entries if is_basic(e[1])]
        for qty, name, comment in sorted(spells, key=lambda e: e[1].casefold()):
            out.extend(pin_lines(name, qty, comment, printings))
        if basics:
            if spells:
                out.append("")
            for qty, name, _comment in sorted(basics, key=lambda e: e[1].casefold()):
                out.append(f"{qty} {name}")
    out.append("")
    out.append(FOOTER)
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="Ship a Deck Block as ManaBox-importable text, pinned to owned printings.")
    ap.add_argument("--deck", required=True, help="working Deck Block file")
    ap.add_argument("--collection", required=True, help="ManaBox Export CSV")
    ap.add_argument("--oracle", help="Oracle card-facts file (sharpens basic-land "
                                     "and multi-faced-name reading)")
    ap.add_argument("--out", help="write the shipped Block here instead of stdout")
    args = ap.parse_args()

    try:
        text = open(args.deck, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Deck Block: {exc}")
    printings = load_printings(args.collection)
    oracle_names, oracle_basics = (load_oracle_names(args.oracle)
                                   if args.oracle else (set(), set()))

    shipped = ship(text, printings, oracle_names, oracle_basics)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(shipped)
        print(f"Deck Block shipped to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(shipped)


if __name__ == "__main__":
    main()
