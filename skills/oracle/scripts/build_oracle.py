#!/usr/bin/env python3
"""Build the Oracle from a ManaBox Export (issue #51).

The Oracle is the Scryfall-derived card-facts file Checks run against (see
CONTEXT.md). This script reads the Export tolerantly, resolves every unique
card, and writes ``oracle.jsonl`` beside the Export — one JSON line per
unique card name, first line a metadata record.

    python3 build_oracle.py --collection collection.csv            # live Scryfall API
    python3 build_oracle.py --collection collection.csv \
        --snapshot snapshot.jsonl                                  # offline, no network

Export parsing is tolerant: header-keyed (never positional), RFC-4180
quoting-aware, UTF-8 with BOM tolerance. Malformed rows — rows naming no
identity (no Scryfall ID and no Name + Set code) — are skipped and reported
with a count and examples. The only hard failure is a header missing the
identity columns: neither a Scryfall ID column nor Name + Set code columns.

Resolution goes Scryfall ID first, Name + Set code fallback for migrated or
deleted IDs. Live resolution uses Scryfall's ``POST /cards/collection``
endpoint — 75 identifiers per call, throttled under 2 calls/second, with the
User-Agent and Accept headers Scryfall requires. With ``--snapshot`` the same
resolution runs offline against a pinned snapshot file instead; evals always
run this way and never call the live API.

Oracle shape (from the spec's Oracle decisions, extended for the Kitchen 20
packet Checks in issue #57 — the Oracle stays trimmed to what Checks need):
prints deduped, token rows excluded, basic lands included, multi-faced cards
flattened with ``//``. Fields exactly: name, mana_value, colors,
color_identity, type_line, oracle_text, legalities trimmed to
standard/pioneer/modern/commander, the game_changer boolean, the deduped
printing's rarity, and the keywords list. No UUIDs — small enough to load
whole. Line one records
``generated_at`` plus the source Export's newest ``Added`` watermark — the
two staleness signals the brief's freshness question reads.

Card data is provided by Scryfall; this tool is not produced by, endorsed by,
or affiliated with Scryfall. Legality data is informational only, never a
guarantee. Stdlib only; no third-party dependencies.

Exit status: 0 with the Oracle written (skipped rows and unresolved cards are
reported, not fatal); 2 on a hard failure (missing identity columns,
unreadable input, network failure).
"""

import argparse
import csv
import io
import json
import pathlib
import sys
import time

API_URL = "https://api.scryfall.com/cards/collection"
BATCH = 75
SECONDS_BETWEEN_CALLS = 0.6  # comfortably under Scryfall's 2 calls/second
EXAMPLE_LIMIT = 5

# Layouts that are game pieces, not playable cards: excluded from the Oracle.
TOKEN_LAYOUTS = {"token", "double_faced_token", "emblem", "art_series"}
LEGALITY_FORMATS = ["standard", "pioneer", "modern", "commander"]


class HardFailure(Exception):
    """The one class of error that stops the build (exit 2)."""


# --- Tolerant Export parsing -------------------------------------------------

def parse_export(path):
    """Parse a ManaBox Export tolerantly.

    Returns (rows, skipped): identity-bearing rows as dicts, and skipped
    malformed-row report strings. Raises HardFailure when the header is
    missing the identity columns.
    """
    try:
        raw = pathlib.Path(path).read_bytes()
    except OSError as exc:
        raise HardFailure(f"cannot read the Export {path}: {exc}") from exc
    text = raw.decode("utf-8-sig", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    has_id = "Scryfall ID" in header
    has_name_set = "Name" in header and "Set code" in header
    if not has_id and not has_name_set:
        raise HardFailure(
            "the Export header is missing the identity columns: it carries "
            "neither a 'Scryfall ID' column nor both 'Name' and 'Set code' "
            f"columns (header: {header})"
        )

    def value(row, column):
        return (row.get(column) or "").strip()

    rows, skipped = [], []
    for line_number, row in enumerate(reader, start=2):
        scryfall_id = value(row, "Scryfall ID")
        name, set_code = value(row, "Name"), value(row, "Set code")
        if scryfall_id or (name and set_code):
            rows.append({
                "scryfall_id": scryfall_id,
                "name": name,
                "set": set_code.lower(),
                "added": value(row, "Added"),
            })
        else:
            fields = [v for v in row.values() if v]
            skipped.append(f"row {line_number}: no identity ({', '.join(fields)[:80] or 'empty row'})")
    return rows, skipped


def identifier_key(ident):
    """The one canonical key for a collection identifier dict — used for
    dedup in gather_identifiers and for matching Scryfall's not_found echoes
    in resolve_live, so identity is keyed a single way everywhere."""
    if "id" in ident:
        return ("id", ident["id"])
    return ("name", ident.get("name", "").casefold(), ident.get("set", ""))


def gather_identifiers(rows):
    """Unique Scryfall collection identifiers for the Export's cards.

    Scryfall ID first; rows without one contribute a Name + Set code
    identifier directly. Each identifier remembers the rows behind it so an
    unresolved ID can fall back to their Name + Set code.
    """
    identifiers, seen = [], {}
    for row in rows:
        if row["scryfall_id"]:
            ident = {"id": row["scryfall_id"]}
        else:
            ident = {"name": row["name"], "set": row["set"]}
        key = identifier_key(ident)
        if key not in seen:
            seen[key] = {"identifier": ident, "rows": []}
            identifiers.append(seen[key])
        seen[key]["rows"].append(row)
    return identifiers


# --- Resolution: pinned snapshot (offline) -----------------------------------

def load_snapshot(path):
    try:
        lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        meta = json.loads(lines[0])["snapshot_meta"]
        cards = [json.loads(line) for line in lines[1:]]
    except (OSError, ValueError, KeyError, IndexError) as exc:
        raise HardFailure(f"cannot read the snapshot {path}: {exc}") from exc
    return meta, cards


def resolve_offline(identifiers, snapshot_cards):
    """Resolve identifiers against the pinned snapshot — same ID-first,
    Name + Set code fallback contract as the live endpoint, no network."""
    by_id = {c["id"]: c for c in snapshot_cards}
    by_name_set = {}
    for card in sorted(
        snapshot_cards,
        key=lambda c: (c["name"], c["set"], c["collector_number"], c["lang"]),
    ):
        names = [card["name"]] + [f["name"] for f in card.get("card_faces", [])]
        for name in names:
            by_name_set.setdefault((name.casefold(), card["set"]), card)

    resolved, fallbacks, unresolved = [], 0, []
    for entry in identifiers:
        ident = entry["identifier"]
        card = by_id.get(ident["id"]) if "id" in ident else None
        if card is None and "name" in ident:
            card = by_name_set.get((ident["name"].casefold(), ident["set"]))
        if card is None and "id" in ident:
            row = entry["rows"][0]
            if row["name"] and row["set"]:
                card = by_name_set.get((row["name"].casefold(), row["set"]))
                if card is not None:
                    fallbacks += 1
        if card is not None:
            resolved.append(card)
        else:
            row = entry["rows"][0]
            unresolved.append(f"{row['name'] or ident.get('id', '?')} ({row['set'].upper() or '?'})")
    return resolved, fallbacks, unresolved


# --- Resolution: the live Scryfall collection endpoint -----------------------

def plugin_version():
    """The pinned plugin version, for an honest User-Agent."""
    manifest = pathlib.Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown")
    except (OSError, ValueError):
        return "unknown"


class Throttle:
    """At most one call per SECONDS_BETWEEN_CALLS — under 2 calls/second."""

    def __init__(self):
        self.last = None

    def wait(self):
        if self.last is not None:
            remaining = SECONDS_BETWEEN_CALLS - (time.monotonic() - self.last)
            if remaining > 0:
                time.sleep(remaining)
        self.last = time.monotonic()


def fetch_batches(idents, api_url, throttle):
    """POST identifiers to the collection endpoint, 75 per call, throttled,
    with the mandatory User-Agent and Accept headers. Returns (data,
    not_found); raises HardFailure on any HTTP or network error."""
    import urllib.error
    import urllib.request

    headers = {
        "User-Agent": f"tutor-oracle/{plugin_version()} (https://github.com/mattiasthalen/tutor)",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    data, not_found = [], []
    for start in range(0, len(idents), BATCH):
        throttle.wait()
        body = json.dumps({"identifiers": idents[start:start + BATCH]}).encode("utf-8")
        request = urllib.request.Request(api_url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise HardFailure(
                f"Scryfall answered HTTP {exc.code} on batch {start // BATCH + 1} — "
                "the Oracle was not written; try again later"
            ) from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise HardFailure(
                f"could not reach the collection endpoint ({exc}) — "
                "the Oracle was not written; check network and try again"
            ) from exc
        data += payload.get("data", [])
        not_found += payload.get("not_found", [])
    return data, not_found


def resolve_live(identifiers, api_url):
    """Resolve identifiers against the live collection endpoint: every unique
    Scryfall ID (or direct Name + Set code) in a first pass, then one
    fallback pass of Name + Set code identifiers for the IDs Scryfall no
    longer knows — migrated or deleted."""
    throttle = Throttle()
    idents = [entry["identifier"] for entry in identifiers]
    data, not_found = fetch_batches(idents, api_url, throttle)

    entries_by_key = {identifier_key(e["identifier"]): e for e in identifiers}
    fallback_idents, fallback_keys, unresolved = [], set(), []
    for miss in not_found:
        entry = entries_by_key.get(identifier_key(miss))
        row = entry["rows"][0] if entry else {"name": "", "set": ""}
        if "id" in miss and row["name"] and row["set"]:
            ident = {"name": row["name"], "set": row["set"]}
            key = identifier_key(ident)
            if key not in fallback_keys:
                fallback_keys.add(key)
                fallback_idents.append(ident)
        else:
            unresolved.append(f"{row['name'] or miss.get('id', '?')} ({row['set'].upper() or '?'})")

    fallbacks = 0
    if fallback_idents:
        second_data, second_missing = fetch_batches(fallback_idents, api_url, throttle)
        data += second_data
        fallbacks = len(fallback_idents) - len(second_missing)
        unresolved += [
            f"{miss.get('name', '?')} ({miss.get('set', '?').upper()})"
            for miss in second_missing
        ]
    return data, fallbacks, unresolved


# --- The Oracle shape --------------------------------------------------------

def flatten(card):
    """One Oracle record for one resolved card. Kept semantically in lockstep
    with the fixture derivation (evals/fixtures/scryfall/derive_oracle.py) so
    a skill-built Oracle and the fixture Oracle agree byte for byte on shared
    cards."""
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

    return {
        "name": card["name"],
        "mana_value": card.get("cmc"),
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


def build_records(resolved):
    """Token rows out, prints deduped to one record per unique card name."""
    playable = [c for c in resolved if c.get("layout") not in TOKEN_LAYOUTS]
    by_name = {}
    for card in sorted(
        playable, key=lambda c: (c["name"], c["set"], c["collector_number"], c["lang"])
    ):
        by_name.setdefault(card["name"], card)  # prints dedupe to the first in sort
    return [flatten(by_name[name]) for name in sorted(by_name)]


def render_oracle(records, generated_at, newest_added, source):
    meta = {
        "oracle_meta": {
            "generated_at": generated_at,
            "source_export_newest_added": newest_added,
            "source": source,
            "card_count": len(records),
        }
    }
    out = [json.dumps(meta, ensure_ascii=False)]
    out += [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    return "\n".join(out) + "\n"


# --- CLI ---------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--collection", default="collection.csv",
        help="the ManaBox Export to read (default: collection.csv)",
    )
    parser.add_argument(
        "--snapshot",
        help="resolve offline against this pinned Scryfall snapshot instead "
             "of the live API (evals always run this way)",
    )
    parser.add_argument(
        "--api-url", default=API_URL,
        help="the collection endpoint to call in live mode "
             "(override to test against a local stub)",
    )
    args = parser.parse_args(argv)

    try:
        rows, skipped = parse_export(args.collection)
        identifiers = gather_identifiers(rows)

        collection_path = pathlib.Path(args.collection)
        print(f"oracle: read {len(rows) + len(skipped)} rows from {collection_path.name}"
              f" ({len(skipped)} malformed rows skipped)")
        for example in skipped[:EXAMPLE_LIMIT]:
            print(f"oracle:   skipped {example}")
        if len(skipped) > EXAMPLE_LIMIT:
            print(f"oracle:   ... and {len(skipped) - EXAMPLE_LIMIT} more")
        print(f"oracle: {len(identifiers)} unique cards to resolve")

        if args.snapshot:
            snap_meta, snapshot_cards = load_snapshot(args.snapshot)
            resolved, fallbacks, unresolved = resolve_offline(identifiers, snapshot_cards)
            generated_at = snap_meta.get("captured_at", "")
            source = f"pinned snapshot {pathlib.Path(args.snapshot).name} (offline)"
            print(f"oracle: resolved {len(resolved)} offline against the pinned snapshot"
                  f" ({fallbacks} by Name + Set code fallback)")
        else:
            resolved, fallbacks, unresolved = resolve_live(identifiers, args.api_url)
            generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            source = "Scryfall API POST /cards/collection"
            print(f"oracle: resolved {len(resolved)} via the collection endpoint"
                  f" ({fallbacks} by Name + Set code fallback)")

        for miss in unresolved[:EXAMPLE_LIMIT]:
            print(f"oracle:   unresolved {miss}")
        if len(unresolved) > EXAMPLE_LIMIT:
            print(f"oracle:   ... and {len(unresolved) - EXAMPLE_LIMIT} more")
        if unresolved:
            print(f"oracle: {len(unresolved)} cards left out of the Oracle — "
                  "they degrade to flagged model knowledge at Build")

        records = build_records(resolved)
        newest_added = max((row["added"] for row in rows), default="")
        oracle_path = collection_path.parent / "oracle.jsonl"
        oracle_path.write_text(
            render_oracle(records, generated_at, newest_added, source),
            encoding="utf-8",
        )
        print(f"oracle: wrote {oracle_path} — {len(records)} cards, "
              f"generated_at {generated_at}, source Export watermark {newest_added or 'none'}")
        print("oracle: card data provided by Scryfall (not endorsed); "
              "legality data is informational only, never a guarantee")
        return 0
    except HardFailure as exc:
        print(f"oracle: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
