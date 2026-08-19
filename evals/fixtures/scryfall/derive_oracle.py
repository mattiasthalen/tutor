#!/usr/bin/env python3
"""Derive the fixture Oracle from the pinned Scryfall snapshot — offline.

The Oracle is the card-facts file Checks run against (see CONTEXT.md). This
script derives the fixture Oracle deterministically from ``snapshot.jsonl``
alone — no network — so the committed ``oracle.jsonl`` is always
byte-reproducible from the committed snapshot. The eval harness re-derives
and byte-compares on every run; a hand-edited Oracle turns the smoke eval
red.

    python3 evals/fixtures/scryfall/derive_oracle.py            # rewrite oracle.jsonl
    python3 evals/fixtures/scryfall/derive_oracle.py --stdout   # print instead

Shape (from the spec's Oracle decisions, extended for the Kitchen 20 packet
Checks in issue #57 — the Oracle stays trimmed to what Checks need): one
JSON line per unique card name — prints deduped, token rows excluded, basic
lands included, multi-faced cards flattened with ``//``. Fields: name,
mana_value, colors, color_identity, type_line, oracle_text, legalities
trimmed to standard/pioneer/modern/commander, the game_changer boolean, the
deduped printing's rarity, and the keywords list. No UUIDs.

Line one records ``generated_at`` plus the source Export's newest ``Added``
watermark. ``generated_at`` is pinned to the snapshot's ``captured_at`` —
the Oracle's facts are exactly as fresh as the snapshot they come from, and
re-derivation stays byte-identical.

Stdlib only; no third-party dependencies.
"""

import csv
import io
import json
import pathlib
import sys

SCRYFALL_DIR = pathlib.Path(__file__).resolve().parent
FIXTURES = SCRYFALL_DIR.parent
SNAPSHOT = SCRYFALL_DIR / "snapshot.jsonl"
ORACLE = SCRYFALL_DIR / "oracle.jsonl"

# Layouts that are game pieces, not playable cards: excluded from the Oracle.
TOKEN_LAYOUTS = {"token", "double_faced_token", "emblem", "art_series"}
LEGALITY_FORMATS = ["standard", "pioneer", "modern", "commander"]


def newest_added():
    """The newest Added timestamp across every fixture Collection CSV."""
    newest = ""
    for csv_path in sorted((FIXTURES / "collections").glob("*.csv")):
        text = csv_path.read_bytes().decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(text)):
            added = row.get("Added", "").strip()
            if added > newest:
                newest = added
    return newest


def flatten(card):
    """One Oracle record for one snapshot card."""
    faces = card.get("card_faces", [])

    def joined(field):
        parts = [face.get(field, "") for face in faces if face.get(field)]
        return " // ".join(parts)

    colors = card.get("colors")
    if colors is None:
        colors = sorted({c for face in faces for c in face.get("colors", [])})
    oracle_text = card.get("oracle_text")
    if oracle_text is None:
        oracle_text = joined("oracle_text")
    mana_value = card.get("cmc")

    return {
        "name": card["name"],
        "mana_value": mana_value,
        "colors": colors,
        "color_identity": card.get("color_identity", []),
        "type_line": card.get("type_line") or joined("type_line"),
        "oracle_text": oracle_text,
        "legalities": {
            fmt: card.get("legalities", {}).get(fmt, "not_legal")
            for fmt in LEGALITY_FORMATS
        },
        "game_changer": bool(card.get("game_changer", False)),
        # The Kitchen 20 packet Checks (issue #57) read these through the
        # unmodified runner. Rarity is print-dependent: this is the deduped
        # printing's — the first in (name, set, collector number, lang) order
        # — deterministic, and exact wherever one printing is owned.
        "rarity": card.get("rarity", ""),
        "keywords": card.get("keywords", []),
    }


def derive():
    lines = SNAPSHOT.read_text(encoding="utf-8").splitlines()
    snapshot_meta = json.loads(lines[0])["snapshot_meta"]
    cards = [json.loads(line) for line in lines[1:]]

    playable = [c for c in cards if c.get("layout") not in TOKEN_LAYOUTS]
    by_name = {}
    for card in sorted(
        playable, key=lambda c: (c["name"], c["set"], c["collector_number"], c["lang"])
    ):
        by_name.setdefault(card["name"], card)  # prints dedupe to the first in sort

    meta = {
        "oracle_meta": {
            "generated_at": snapshot_meta["captured_at"],
            "source_export_newest_added": newest_added(),
            "source": "derived from scryfall/snapshot.jsonl by derive_oracle.py",
            "card_count": len(by_name),
        }
    }
    out = [json.dumps(meta, ensure_ascii=False)]
    for name in sorted(by_name):
        out.append(json.dumps(flatten(by_name[name]), ensure_ascii=False, sort_keys=True))
    return "\n".join(out) + "\n"


def main(argv):
    text = derive()
    if "--stdout" in argv:
        sys.stdout.write(text)
    else:
        ORACLE.write_text(text, encoding="utf-8")
        print(f"wrote {ORACLE.name}: {text.count(chr(10)) - 1} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
