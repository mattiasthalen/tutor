#!/usr/bin/env python3
"""tutor availability — the Collection's free pool under a Brief (issue #54).

The Deck draws only from the Collection, and copies in existing Decks are
committed by default: an Export row with Binder Type ``deck`` belongs to the
Deck named by its Binder Name, and the Brief's ``donor:`` lines free those
copies (``donor: all`` frees everything). One Deck is freed without any
``donor:`` line: the Deck being built itself — rows committed to the ManaBox
deck carrying the Brief's ``name:`` (or the Deck Block's title) are the
rebuilt Deck's own copies, freed automatically so an Upgrade — an ordinary
Build re-run against a fresh Export — never contends with itself (issue
#56). This script does the judgment-free arithmetic of those rules while
Build chooses cards: how many copies of a name are free, and — when a want
cannot be met — the honest declined-contention sentence Build must report:

    wanted Rhystic Study; all copies committed to Tatyova

The Suite's ``availability.in_collection`` Check (the fixed runner) is the
gate; this script is the builder's lens on the same arithmetic, consulted
before a card is picked so contention is declined out loud, never silently.
The ship script (``ship_deck.py``, same skill) imports the row-level helpers
below so printing pins are drawn from the same free pool, never re-derived.

At a Table (issue #59) the Seats build sequentially in seat order, and an
earlier Seat's finished Deck Block counts as committed copies: ``--table-mate
DECK_BLOCK`` (repeatable) reads such a Block — its ``// <name>`` title is the
Deck the copies are committed to, its Maybeboard stays wishlist — and no
``donor:`` line ever frees those copies, because table-mates are never Donor
Decks; reallocation is a human re-brief loop.

Usage:
    availability.py --collection EXPORT_CSV
                    [--brief BRIEF | --donor NAME ...]
                    [--table-mate DECK_BLOCK ...]
                    (--want "Card Name" [--want ...] | --deck DECK_BLOCK)

``--brief`` reads the Brief Block's ``donor:`` lines and its ``name:`` line
(the Deck being built — freed automatically); ``--donor`` names one
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


def row_deck(row):
    """The Deck one Export row's copies are committed to, or None: a row
    whose Binder Type is ``deck`` belongs to the Deck named by its Binder
    Name — the committed-by-default rule (issue #54)."""
    if (row.get("Binder Type") or "").strip() == "deck":
        return (row.get("Binder Name") or "").strip() or None
    return None


def deck_is_freed(deck, donors):
    """True when the donor lines free this Deck's copies: a donor: line
    naming the Deck, or ``donor: all`` freeing everything."""
    return deck in donors or any(d.lower() == "all" for d in donors)


def load_pool(path):
    """Read the Export: (owned counts, committed counts per Deck) by name.

    Header-keyed, UTF-8 with BOM tolerance, malformed rows skipped — the
    ingestion posture of spec #46. Returns (owned, committed) where owned is
    {name: total copies} and committed is {name: {deck name: copies}}.

    The fixed runner's ``load_commitments`` (check_deck.py, suite-runner
    skill) is a deliberate mirror of the committed side of this reading —
    kept in lockstep by hand, never imported, because skill assets stay
    self-contained. Edit the two together.
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
            deck = row_deck(row)
            if deck:
                decks = committed.setdefault(name, {})
                decks[deck] = decks.get(deck, 0) + quantity
    return owned, committed


def brief_values(path, wanted_key):
    """Values of the Brief Block's ``<wanted_key>:`` lines, in file order —
    the one keyed line-scan behind donors_from_brief and name_from_brief."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Brief: {exc}")
    values = []
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() == wanted_key and value.strip():
            values.append(value.strip())
    return values


def donors_from_brief(path):
    """The Brief Block's donor: lines, in file order."""
    return brief_values(path, "donor")


def name_from_brief(path):
    """The Brief's name: line — the Deck this Build builds — or None.

    Export rows committed to a ManaBox deck carrying this name are the
    rebuilt Deck's own copies: an Upgrade re-run frees them automatically,
    no donor: line needed (issue #56). A Deck renamed on one side — its
    ManaBox name matching neither this line nor the Deck Block's title —
    is freed only by a donor: line, the connection only the human can
    make."""
    names = brief_values(path, "name")
    return names[0] if names else None


BOARD_HEADERS = ("Commander", "Mainboard", "Sideboard", "Maybeboard")
# Deck-line grammar: the same PIN/LUMP regexes and raw-first reading order as
# the fixed runner's (check_deck.py) — a printing pin is "(SET) number" at the
# end of the line, matched on the raw line first so multi-faced names carrying
# " // " re-anchor, then comment-stripping happens from the right. One honest
# divergence from the runner: a BARE line holding " // " resolves here through
# the owned names — the whole remainder wins when the Collection owns it —
# where the runner truncates it to the front face.
PIN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]{2,5})\)\s+(\S+)$")
LUMP = re.compile(r"^(\d+)\s+([^(]+)$")


def deck_wants(path, owned):
    """({name: count} the Deck Block asks for, the Block's title or None) —
    the Maybeboard excluded from the counts.

    The title is the ManaBox deck name an import of this Block creates —
    the rebuilt Deck's own name, read the same way as the fixed runner's
    parse_deck: the first ``//`` comment that is not a Board header.

    A bare line holding " // " is ambiguous — a multi-faced name or an inline
    comment. The Collection settles it: the whole remainder wins when it names
    an owned card, otherwise the comment reading applies.
    """
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        unusable(f"cannot read the Deck Block: {exc}")
    wants, board, title = {}, None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            head = line[2:].strip()
            if head in BOARD_HEADERS:
                board = head
            elif title is None:
                title = head
            continue
        if board == "Maybeboard":  # the wishlist Board: may be unowned
            continue
        stripped = line.rsplit(" // ", 1)[0].strip() if " // " in line else line
        m = PIN.match(line) or PIN.match(stripped)
        if m:
            qty, name = int(m.group(1)), m.group(2).strip()
        else:
            full = LUMP.match(line)
            if full and full.group(2).strip() in owned:
                qty, name = int(full.group(1)), full.group(2).strip()
            else:
                m = LUMP.match(stripped)
                if not m:
                    continue
                qty, name = int(m.group(1)), m.group(2).strip()
        wants[name] = wants.get(name, 0) + qty
    return wants, title


def read_table_mate(path, owned):
    """(deck name, {card name: copies}) from an earlier Seat's finished Deck
    Block: the ``// <name>`` title is the Deck the copies are committed to;
    every non-Maybeboard card line is a physical take (the Maybeboard is the
    wishlist Board). The line grammar is deck_wants' — same regexes, same
    owned-name lookaside for bare multi-faced lines."""
    try:
        first = open(path, encoding="utf-8").readline().strip()
    except OSError as exc:
        unusable(f"cannot read the table-mate Deck Block: {exc}")
    if not first.startswith("//") or not first[2:].strip():
        unusable(f"table-mate {path} has no '// <name>' title line — "
                 "a finished Deck Block names its Deck first")
    takes, _title = deck_wants(path, owned)
    return first[2:].strip(), takes


def commit_table_mates(committed, mate_paths, owned):
    """Fold each table-mate Deck Block's takes into the committed counts;
    returns the set of table-mate Deck names — the Decks no donor: line
    frees (table-mates are never Donor Decks)."""
    mates = set()
    for path in mate_paths:
        deck, takes = read_table_mate(path, owned)
        mates.add(deck)
        for name, qty in takes.items():
            decks = committed.setdefault(name, {})
            decks[deck] = decks.get(deck, 0) + qty
    return mates


def free_copies(name, owned, committed, donors, table_mates=frozenset()):
    """(free, held) for a name: free copies under the donor lines, and the
    {deck: copies} still holding the rest. donor: all frees everything —
    except a table-mate's copies, which no donor: line ever frees."""
    total = owned.get(name, 0)
    held = {deck: qty for deck, qty in committed.get(name, {}).items()
            if deck in table_mates or not deck_is_freed(deck, donors)}
    return total - sum(held.values()), held


def report_want(name, need, owned, committed, donors, table_mates=frozenset()):
    """(ok, sentence) for one wanted name at its needed count."""
    total = owned.get(name, 0)
    free, held = free_copies(name, owned, committed, donors, table_mates)
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
    ap.add_argument("--table-mate", action="append", default=[], metavar="DECK_BLOCK",
                    help="an earlier Seat's finished Deck Block; its copies count "
                         "as committed and no donor frees them (repeatable)")
    ap.add_argument("--want", action="append", default=[], metavar="NAME",
                    help="card name to check for a free copy (repeat to want more)")
    ap.add_argument("--deck", help="Deck Block file; check every card at its count")
    args = ap.parse_args()

    if not args.want and not args.deck:
        ap.error("nothing to check: pass --want NAME (repeatable) or --deck FILE")

    owned, committed = load_pool(args.collection)
    # The freed Decks: the Brief's donor: lines (and --donor), plus — issue
    # #56, no line needed — the Deck being built itself, named by the Brief's
    # name: line or the Deck Block's title. An Upgrade is an ordinary Build
    # re-run: the rebuilt Deck's own copies are freed automatically, so it
    # never contends with itself. The fixed runner's availability Check
    # mirrors this self-freeing as its deck != deck_name filter
    # (check_deck.py, suite-runner skill) — kept in lockstep by hand, never
    # imported. Edit the two together.
    table_mates = commit_table_mates(committed, args.table_mate, owned)
    freed = list(args.donor)
    if args.brief:
        freed += donors_from_brief(args.brief)
        rebuilt = name_from_brief(args.brief)
        if rebuilt:
            freed.append(rebuilt)

    need = {}
    for name in args.want:
        need[name] = need.get(name, 0) + 1
    if args.deck:
        wants, title = deck_wants(args.deck, owned)
        if title:
            freed.append(title)
        for name, count in wants.items():
            need[name] = need.get(name, 0) + count

    declined = 0
    for name, count in need.items():
        ok, sentence = report_want(name, count, owned, committed, freed,
                                   table_mates)
        declined += 0 if ok else 1
        print(sentence)

    sys.exit(1 if declined else 0)


if __name__ == "__main__":
    main()
