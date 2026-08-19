#!/usr/bin/env python3
"""tutor ship — the Deck Block in its ManaBox-importable shape (issue #54).

Build iterates on a working Deck Block; this script does the judgment-free
finishing so the shipped artifact is text ManaBox actually imports, per the
Block-formats decision (owner-verified: ManaBox accepts ``//`` comments and
reserves the four Board headers):

- first line ``// <name>``, Board headers only for the Boards present, in
  canonical order (Commander, Mainboard, Sideboard, Maybeboard),
- each nonbasic pinned to the exact owned printing — set code and collector
  number from the Export — drawn only from the copies actually free under
  the collection-contention arithmetic (``availability.py``, same skill):
  deck-row copies are committed by default and the Brief's ``donor:`` lines
  free them (``donor: all`` frees everything), while rows committed to the
  ManaBox deck the Block's own title names — the rebuilt Deck itself — are
  freed automatically, no ``donor:`` line needed, so an Upgrade re-ship
  never contends with the Deck it rebuilds (issue #56). Among the free copies
  the fancier print wins (Scryfall's finishes ladder: etched over foil over
  normal; ties break on set code then collector number), spilling across
  printings only as free counts allow, so physical assembly matches the list
  card for card without raiding a committed Deck,
- optional inline ``// category`` comments preserved,
- basics lumped per name, last in each Board after a blank line,
- the Maybeboard as the wishlist Board: entries stay unpinned and may be
  unowned — the one place the collection-only rule bends,
- the short-form Fan Content footer line, exactly once (re-shipping a shipped
  Block under the same donor lines is byte-identical: the round-trip is the
  identity).

A nonbasic outside the Maybeboard that the Collection does not own cannot be
pinned and refuses the run naming the card — the Deck draws only from the
Collection. A nonbasic whose free copies cannot cover its count refuses in
the declined-contention sentence (``wanted <card>; all copies committed to
<deck>``). A card missing from the Oracle is no failure here: the Oracle
only sharpens basic-land detection and multi-faced-name reading.

At a Table (issue #59) an earlier Seat's finished Deck Block counts as
committed copies: ``--table-mate DECK_BLOCK`` (repeatable) subtracts the
mate's pinned takes from the free pool — printing-exact, fancier free copy
first, mirroring the order the mate's own ship drew — so two Seats never pin
the same physical copy. No ``donor:`` line frees a table-mate's copies:
table-mates are never Donor Decks.

Usage:
    ship_deck.py --deck DECK_BLOCK --collection EXPORT_CSV
                 [--brief BRIEF | --donor NAME ...]
                 [--table-mate DECK_BLOCK ...]
                 [--oracle ORACLE] [--out FILE]

Exit status: 0 shipped, 1 refused (the message names why), 2 unusable input.
Stdlib only, offline.
"""

import argparse
import csv
import json
import re
import sys

# The collection-contention arithmetic is availability.py's, one directory
# over in the same skill — imported, never re-derived, so the pin and the
# availability Check can never disagree about which copies are free.
from availability import deck_is_freed, donors_from_brief, report_want, row_deck

BOARD_ORDER = ("Commander", "Mainboard", "Sideboard", "Maybeboard")

# The five basic land names plus Wastes; the Oracle's type line is the
# authority when present, this set the fallback.
BASIC_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}

# Scryfall lists print finishes as nonfoil, foil, etched — read as the
# fancier-print ladder, later is fancier. ManaBox's Foil column uses
# "normal" for nonfoil.
FINISH_RANK = {"normal": 0, "": 0, "foil": 1, "etched": 2}

# Deck-line grammar: the same PIN/LUMP regexes and raw-first reading order as
# the fixed runner's (check_deck.py). One honest divergence from the runner: a
# bare line holding " // " resolves here through the known names (Collection
# or Oracle) — the whole remainder wins when it names a known card — where the
# runner truncates it to the front face.
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
    quantity, deck), ...]} where deck is the Deck the row's copies are
    committed to (availability.py's committed-by-default reading) or None
    for free-standing rows. Header-keyed, BOM-tolerant, malformed rows
    skipped."""
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
            printings.setdefault(name, []).append(
                (set_code, number, foil, quantity, row_deck(row)))
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


def load_table_mates(paths, printings):
    """Subtract each table-mate Deck Block's pinned takes from the free pool
    — an earlier Seat's finished Deck counts as committed copies (issue
    #59). A take matches its printing exactly and draws free rows first,
    fancier finish first, mirroring the order the mate's own ship drew; the
    subtracted copies re-enter the pool committed to the mate's Deck name.
    Returns the set of table-mate Deck names — no donor: line frees them."""
    mates = set()
    for path in paths:
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except OSError as exc:
            unusable(f"cannot read the table-mate Deck Block: {exc}")
        if not lines or not lines[0].startswith("//") or not lines[0][2:].strip():
            unusable(f"table-mate {path} has no '// <name>' title line — "
                     "a finished Deck Block names its Deck first")
        mate = lines[0][2:].strip()
        mates.add(mate)
        board = None
        for raw in lines[1:]:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("//"):
                head = line[2:].strip()
                if head in BOARD_ORDER:
                    board = head
                continue
            if board == "Maybeboard":   # wishlist: never a physical take
                continue
            stripped = line.rsplit(" // ", 1)[0].strip() if " // " in line else line
            m = PIN.match(line) or PIN.match(stripped)
            pin = None
            if m:
                qty, name = int(m.group(1)), m.group(2).strip()
                pin = (m.group(3), m.group(4))
            else:
                # A bare take — a lumped basic, or an unpinned line from a
                # mate mid-build — still holds physical copies: subtract it
                # name-level, the printing left to the fancier-first order.
                bare = LUMP.match(line)
                if bare and bare.group(2).strip() in printings:
                    qty, name = int(bare.group(1)), bare.group(2).strip()
                else:
                    bare = LUMP.match(stripped)
                    if not bare:
                        continue
                    qty, name = int(bare.group(1)), bare.group(2).strip()
            rows = printings.get(name, [])
            order = sorted(
                range(len(rows)),
                key=lambda i: (rows[i][4] is not None,
                               -FINISH_RANK.get(rows[i][2], 0)),
            )
            remaining = qty
            for i in order:
                if remaining <= 0:
                    break
                row_set, row_number, foil, have, deck = rows[i]
                if have <= 0 or (pin and (row_set, row_number) != pin):
                    continue
                take = min(remaining, have)
                rows[i] = (row_set, row_number, foil, have - take, deck)
                rows.append((row_set, row_number, foil, take, mate))
                remaining -= take
            # remaining > 0 means the mate holds copies the Export does not
            # show free — the pin arithmetic below will refuse honestly.
    return mates


def pin_lines(name, quantity, comment, printings, donors, table_mates=frozenset()):
    """The pinned line(s) for one nonbasic, drawn only from the copies free
    under the donor lines (deck-row copies are committed by default —
    availability.py's arithmetic) with every table-mate take already
    subtracted: fancier free print first (etched over foil over normal, then
    set code and collector number), spilling to the next printing only as
    free counts allow. Too few free copies refuses in the
    declined-contention sentence."""
    owned = printings.get(name)
    if not owned:
        refuse(f"{name} is not in the Collection — the Deck draws only from the "
               "Collection; unowned candidates belong on the Maybeboard")
    merged, held = {}, {}
    for set_code, number, foil, qty, deck in owned:
        if deck is not None and (deck in table_mates
                                 or not deck_is_freed(deck, donors)):
            held[deck] = held.get(deck, 0) + qty
            continue
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
        if qty <= 0:
            continue
        take = min(remaining, qty)
        suffix = f" // {comment}" if comment else ""
        lines.append(f"{take} {name} ({set_code}) {number}{suffix}")
        remaining -= take
    if remaining > 0:
        total = sum(qty for _s, _n, _f, qty, _d in owned)
        if held:
            # availability.py's own declined sentence, from the same numbers.
            committed = {}
            for _s, _n, _f, qty, deck in owned:
                if deck is not None:
                    committed[deck] = committed.get(deck, 0) + qty
            _ok, sentence = report_want(
                name, quantity, {name: total}, {name: committed}, donors,
                table_mates)
            if any(deck in table_mates for deck in held):
                refuse(f"{sentence} — a table-mate's finished Deck holds "
                       "them, and table-mates are never Donor Decks; "
                       "reallocation is a human re-brief loop")
            refuse(f"{sentence} — the pin draws only from free copies; a "
                   "donor: line frees a committed Deck")
        refuse(f"{name}: the Deck wants {quantity}, the Collection holds "
               f"{total} — the Deck draws only from the Collection")
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


def ship(text, printings, oracle_names, oracle_basics, donors=(),
         table_mates=frozenset()):
    known = set(printings) | oracle_names
    title, boards = parse_deck(text, known)
    # The rebuilt Deck never contends with itself (issue #56): the Block's
    # title is the ManaBox deck name its import creates, so Export rows
    # committed to that name are the Deck's own copies — freed for pinning
    # automatically, no donor: line needed. An Upgrade re-ship against the
    # fresh Export stays the identity on its own output.
    donors = (*donors, title)

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
            out.extend(pin_lines(name, qty, comment, printings, donors,
                                 table_mates))
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
        description="Ship a Deck Block as ManaBox-importable text, pinned to "
                    "the free owned printings under the Brief's donor: lines.")
    ap.add_argument("--deck", required=True, help="working Deck Block file")
    ap.add_argument("--collection", required=True, help="ManaBox Export CSV")
    ap.add_argument("--brief", help="Brief Block file; its donor: lines free "
                                    "committed Decks' copies for pinning")
    ap.add_argument("--donor", action="append", default=[],
                    help="free this Deck's copies (repeatable; 'all' frees everything)")
    ap.add_argument("--table-mate", action="append", default=[], metavar="DECK_BLOCK",
                    help="an earlier Seat's finished Deck Block; its pinned "
                         "takes leave the free pool and no donor frees them "
                         "(repeatable)")
    ap.add_argument("--oracle", help="Oracle card-facts file (sharpens basic-land "
                                     "and multi-faced-name reading)")
    ap.add_argument("--out", help="write the shipped Block here instead of stdout")
    args = ap.parse_args()

    try:
        text = open(args.deck, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Deck Block: {exc}")
    printings = load_printings(args.collection)
    table_mates = load_table_mates(args.table_mate, printings)
    donors = list(args.donor)
    if args.brief:
        donors += donors_from_brief(args.brief)
    oracle_names, oracle_basics = (load_oracle_names(args.oracle)
                                   if args.oracle else (set(), set()))

    shipped = ship(text, printings, oracle_names, oracle_basics, donors,
                   table_mates)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(shipped)
        print(f"Deck Block shipped to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(shipped)


if __name__ == "__main__":
    main()
