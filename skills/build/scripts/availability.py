#!/usr/bin/env python3
"""tutor availability — the Collection's free pool under a Brief (issue #54).

The Deck draws only from the Collection, and copies in existing Decks are
committed by default: an Export row with Binder Type ``deck`` belongs to the
Deck named by its Binder Name, and only the Brief's ``donor:`` lines free
those copies (``donor: all`` frees everything). This script does the
judgment-free arithmetic of that rule while Build chooses cards: how many
copies of a name are free, and — when a want cannot be met — the honest
declined-contention sentence Build must report:

    wanted Rhystic Study; all copies committed to Tatyova

The Suite's ``availability.in_collection`` Check (the fixed runner) is the
gate; this script is the builder's lens on the same arithmetic, consulted
before a card is picked so contention is declined out loud, never silently.

Usage:
    availability.py --collection EXPORT_CSV
                    [--brief BRIEF | --donor NAME ...]
                    (--want "Card Name" [--want ...] | --deck DECK_BLOCK)

``--brief`` reads the Brief Block's ``donor:`` lines; ``--donor`` names one
directly (repeatable; ``--donor all`` frees the whole Collection). With
``--want``, each name is checked for one free copy (repeat a name to want
more). With ``--deck``, every card the Deck Block asks for is checked at its
count — the Maybeboard is the wishlist Board and is never counted.

Exit status: 0 every want free, 1 contention or shortage declined (the
sentences say which), 2 unusable input. Stdlib only, offline.
"""

import argparse
import csv
import re
import sys


def unusable(message):
    print(message, file=sys.stderr)
    sys.exit(2)


def load_pool(path):
    """Read the Export: (owned counts, committed counts per Deck) by name.

    Header-keyed, UTF-8 with BOM tolerance, malformed rows skipped — the
    ingestion posture of spec #46. Returns (owned, committed) where owned is
    {name: total copies} and committed is {name: {deck name: copies}}.
    """
    owned, committed = {}, {}
    try:
        handle = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        unusable(f"cannot read the Export: {exc}")
    with handle:
        for row in csv.DictReader(handle):
            name = (row.get("Name") or "").strip()
            try:
                quantity = int(row.get("Quantity", 1))
            except (TypeError, ValueError):
                continue
            if not name:
                continue
            owned[name] = owned.get(name, 0) + quantity
            if (row.get("Binder Type") or "").strip() == "deck":
                deck = (row.get("Binder Name") or "").strip()
                if deck:
                    decks = committed.setdefault(name, {})
                    decks[deck] = decks.get(deck, 0) + quantity
    return owned, committed


def donors_from_brief(path):
    """The Brief Block's donor: lines, in file order."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Brief: {exc}")
    donors = []
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == "donor" and value.strip():
            donors.append(value.strip())
    return donors


BOARD_HEADERS = ("Commander", "Mainboard", "Sideboard", "Maybeboard")
# Deck-line grammar, mirroring the fixed runner's: a printing pin is
# "(SET) number" at the end of the line, an inline " // category" comment may
# trail it. Multi-faced names carry " // " inside the name itself, so the pin
# is matched on the raw line first and comment-stripping happens from the
# right — the same reading order as check_deck.py.
PIN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]{2,5})\)\s+(\S+)$")
LUMP = re.compile(r"^(\d+)\s+([^(]+)$")


def deck_wants(path, owned):
    """{name: count} the Deck Block asks for, Maybeboard excluded.

    A bare line holding " // " is ambiguous — a multi-faced name or an inline
    comment. The Collection settles it: the whole remainder wins when it names
    an owned card, otherwise the comment reading applies.
    """
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Deck Block: {exc}")
    wants, board = {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            head = line[2:].strip()
            if head in BOARD_HEADERS:
                board = head
            continue
        if board == "Maybeboard":  # the wishlist Board: may be unowned
            continue
        stripped = line.rsplit(" // ", 1)[0].strip() if " // " in line else line
        m = PIN.match(line) or PIN.match(stripped)
        if m:
            qty, name = int(m.group(1)), m.group(2).strip()
        else:
            m = LUMP.match(line) or LUMP.match(stripped)
            if not m:
                continue
            qty, name = int(m.group(1)), m.group(2).strip()
            if " // " in line and LUMP.match(line):
                full = LUMP.match(line).group(2).strip()
                if full in owned:
                    name = full
        wants[name] = wants.get(name, 0) + qty
    return wants


def free_copies(name, owned, committed, donors):
    """(free, held) for a name: free copies under the donor lines, and the
    {deck: copies} still holding the rest. donor: all frees everything."""
    total = owned.get(name, 0)
    if any(d.lower() == "all" for d in donors):
        return total, {}
    held = {deck: qty for deck, qty in committed.get(name, {}).items()
            if deck not in donors}
    return total - sum(held.values()), held


def report_want(name, need, owned, committed, donors):
    """(ok, sentence) for one wanted name at its needed count."""
    total = owned.get(name, 0)
    free, held = free_copies(name, owned, committed, donors)
    holders = ", ".join(sorted(held))
    if total == 0:
        return False, f"wanted {name}; not in the Collection"
    if free <= 0:
        return False, f"wanted {name}; all copies committed to {holders}"
    if free < need:
        return False, (f"wanted {name} (need {need}); {free} free, "
                       f"{sum(held.values())} committed to {holders}")
    committed_note = (f", {sum(held.values())} committed to {holders}"
                      if held else "")
    return True, f"{name}: {free} free of {total} owned{committed_note}"


def main():
    ap = argparse.ArgumentParser(
        description="Report the Collection's free copies under a Brief's donor: lines.")
    ap.add_argument("--collection", required=True, help="ManaBox Export CSV")
    ap.add_argument("--brief", help="Brief Block file; its donor: lines free Decks")
    ap.add_argument("--donor", action="append", default=[],
                    help="free this Deck's copies (repeatable; 'all' frees everything)")
    ap.add_argument("--want", action="append", default=[], metavar="NAME",
                    help="card name to check for a free copy (repeat to want more)")
    ap.add_argument("--deck", help="Deck Block file; check every card at its count")
    args = ap.parse_args()

    if not args.want and not args.deck:
        ap.error("nothing to check: pass --want NAME (repeatable) or --deck FILE")

    owned, committed = load_pool(args.collection)
    donors = list(args.donor)
    if args.brief:
        donors += donors_from_brief(args.brief)

    need = {}
    for name in args.want:
        need[name] = need.get(name, 0) + 1
    if args.deck:
        for name, count in deck_wants(args.deck, owned).items():
            need[name] = need.get(name, 0) + count

    declined = 0
    for name, count in need.items():
        ok, sentence = report_want(name, count, owned, committed, donors)
        declined += 0 if ok else 1
        print(sentence)

    sys.exit(1 if declined else 0)


if __name__ == "__main__":
    main()
