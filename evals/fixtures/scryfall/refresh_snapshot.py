#!/usr/bin/env python3
"""Deliberately refresh the pinned Scryfall snapshot for the eval fixtures.

This is the deliberate refresh path to the live Scryfall API; the only other
live caller in the repo is the oracle skill's ``build_oracle.py`` in live
mode. Evals touch neither live path — they read the committed
``snapshot.jsonl`` beside this script. Run this refresh by hand when the
fixture set changes or a deliberate data refresh is wanted, then commit the
diff:

    python3 evals/fixtures/scryfall/refresh_snapshot.py

What it does:

1. Scans the fixture tree for every card the fixtures reference — Scryfall
   IDs from the Collection CSVs, (set, collector number) pins from the Deck
   Blocks and the real ManaBox deck text, bare names from unpinned lines
   (basics, Maybeboard candidates).
2. Resolves them through Scryfall's ``POST /cards/collection`` endpoint,
   75 identifiers per call, throttled under 2 calls/second, with the
   User-Agent and Accept headers Scryfall requires.
3. Prunes each card object to the fields tutor's Checks, Oracle, and Review
   evals need (no prices, no image URIs, no UUID cruft beyond the print id),
   and writes ``snapshot.jsonl``: one metadata line, then one card per line,
   sorted by (name, set, collector number, lang) for clean diffs.

Any identifier Scryfall cannot resolve fails the refresh loudly — a snapshot
with silent holes would let fixture drift masquerade as green evals. Exits
nonzero on any not-found identifier or HTTP failure.

Stdlib only; no third-party dependencies.
"""

import csv
import io
import json
import pathlib
import re
import sys
import time
import urllib.request

FIXTURES = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT = pathlib.Path(__file__).resolve().parent / "snapshot.jsonl"
API = "https://api.scryfall.com/cards/collection"
HEADERS = {
    "User-Agent": "tutor-fixture-refresh/0.1 (https://github.com/mattiasthalen/tutor)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
BATCH = 75
SECONDS_BETWEEN_CALLS = 0.6  # comfortably under Scryfall's 2 calls/second

COLLECTION_CSVS = sorted((FIXTURES / "collections").glob("*.csv"))
DECK_TEXTS = sorted((FIXTURES / "decks").glob("*.txt")) + [
    FIXTURES / "collections" / "real-deck.txt"
]

# Deck-line grammar — a verbatim copy of run_evals.py's PINNED_LINE/BARE_LINE
# (kept in lockstep by hand, not imported), so the harness's coverage check
# reads the fixtures with the same grammar this refresh used. Edit together.
PINNED_LINE = re.compile(r"^(\d+) (.+) \(([A-Z0-9]{2,6})\) (\S+)(?: // (.+))?$")
BARE_LINE = re.compile(r"^(\d+) (.+?)(?: // (.+))?$")

# The pruned field set: what Checks, the Oracle derivation, and Review evals
# read. Deliberately no prices (informational-only per the Scryfall notice,
# and never pinned), no image/purchase URIs.
CARD_FIELDS = [
    "id", "oracle_id", "name", "lang", "released_at", "layout", "mana_cost",
    "cmc", "type_line", "oracle_text", "power", "toughness", "loyalty",
    "colors", "color_identity", "keywords", "produced_mana", "set",
    "set_name", "collector_number", "rarity", "promo", "finishes",
    "game_changer",
]
FACE_FIELDS = [
    "name", "mana_cost", "type_line", "oracle_text", "colors", "power",
    "toughness", "loyalty",
]
LEGALITY_FORMATS = ["standard", "pioneer", "modern", "commander"]


def gather_identifiers():
    """Every card the fixtures reference, as Scryfall collection identifiers."""
    identifiers, seen = [], set()

    def add(key, ident):
        if key not in seen:
            seen.add(key)
            identifiers.append(ident)

    for csv_path in COLLECTION_CSVS:
        text = csv_path.read_bytes().decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(text)):
            scryfall_id = row.get("Scryfall ID", "").strip()
            if scryfall_id:
                add(("id", scryfall_id), {"id": scryfall_id})

    for deck_path in DECK_TEXTS:
        for line in deck_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("//"):
                continue
            m = PINNED_LINE.match(line)
            if m:
                set_code, number = m.group(3).lower(), m.group(4)
                add(("pin", set_code, number),
                    {"set": set_code, "collector_number": number})
                continue
            m = BARE_LINE.match(line)
            if m:
                add(("name", m.group(2)), {"name": m.group(2)})

    return identifiers


def fetch(identifiers):
    cards, not_found = [], []
    for start in range(0, len(identifiers), BATCH):
        batch = identifiers[start:start + BATCH]
        body = json.dumps({"identifiers": batch}).encode("utf-8")
        request = urllib.request.Request(API, data=body, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        cards += payload.get("data", [])
        not_found += payload.get("not_found", [])
        print(f"  batch {start // BATCH + 1}: "
              f"{len(payload.get('data', []))} cards, "
              f"{len(payload.get('not_found', []))} not found")
        time.sleep(SECONDS_BETWEEN_CALLS)
    return cards, not_found


def prune(card):
    kept = {field: card[field] for field in CARD_FIELDS if field in card}
    kept["legalities"] = {
        fmt: card.get("legalities", {}).get(fmt, "not_legal")
        for fmt in LEGALITY_FORMATS
    }
    if "card_faces" in card:
        kept["card_faces"] = [
            {field: face[field] for field in FACE_FIELDS if field in face}
            for face in card["card_faces"]
        ]
    return kept


def main():
    identifiers = gather_identifiers()
    print(f"{len(identifiers)} unique fixture card identifiers")
    cards, not_found = fetch(identifiers)

    unique = {}
    for card in cards:
        unique[card["id"]] = prune(card)
    ordered = sorted(
        unique.values(),
        key=lambda c: (c["name"], c["set"], c["collector_number"], c["lang"]),
    )

    meta = {
        "snapshot_meta": {
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "Scryfall API POST /cards/collection",
            "api_host": "api.scryfall.com",
            "card_count": len(ordered),
            "legality_formats": LEGALITY_FORMATS,
            "refresh": "python3 evals/fixtures/scryfall/refresh_snapshot.py",
        }
    }
    with SNAPSHOT.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for card in ordered:
            handle.write(json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {SNAPSHOT.name}: {len(ordered)} cards")

    if not_found:
        print("NOT FOUND — refresh failed, fix the fixtures or identifiers:")
        for ident in not_found:
            print(f"  {ident}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
