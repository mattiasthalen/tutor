#!/usr/bin/env python3
"""tutor's offline eval harness (issue #48).

Runs the eval cases in ``evals/evals.json`` — authored in the skill-creator
eval workflow format — and grades their mechanical expectations against the
committed fixtures. Everything here is deterministic and offline: fixtures on
disk are the only input, fixed predicates are the only graders, and the live
Scryfall API is never called (network lives only in the deliberate snapshot
refresh script and the oracle build script's live mode; this harness runs
neither path).

Usage:
    python3 evals/run_evals.py [--case NAME_OR_ID] [--fixture-root DIR] [--out DIR]

Exit status: 0 when every graded mechanical expectation passes, 1 otherwise.

Two grader tiers (from the spec's testing decisions): hard mechanical
invariants are graded here by fixed predicates registered per expectation
text; expectations without a registered predicate are soft LLM judgment,
reported as such and left to the dev-time skill-creator workflow.

Results land in ``evals/results/<case-name>/`` as ``eval_metadata.json`` and
``grading.json`` in the skill-creator grading schema, so the same artifacts
slot into the skill-creator viewer and, later, the gated ``claude plugin
eval`` flow (see docs/spikes/plugin-eval-enablement.md).
"""

import argparse
import csv
import io
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EVALS_DIR = pathlib.Path(__file__).resolve().parent

# Descriptive per-case directory names, keyed by eval id (the skill-creator
# evals.json schema itself carries no name field; the workflow names runs).
CASE_NAMES = {
    1: "harness-smoke",
    2: "oracle-smoke",
    3: "brief-smoke",
}


class Context:
    """What every fixed predicate gets to look at: the fixture tree."""

    def __init__(self, fixture_root):
        self.fixture_root = pathlib.Path(fixture_root)

    def path(self, relative):
        return self.fixture_root / relative

    def read_manabox_csv(self, relative):
        """Parse a ManaBox export CSV header-keyed; tolerate a UTF-8 BOM."""
        raw = self.path(relative).read_bytes()
        text = raw.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))


# --- Fixed predicates -------------------------------------------------------
# Each returns (passed: bool, evidence: str).

def check_realism_row_count(ctx):
    rows = ctx.read_manabox_csv("collections/real-collection.csv")
    count = len(rows)
    return (
        count == 577,
        f"collections/real-collection.csv parsed header-keyed: {count} data rows (expected 577)",
    )


MANABOX_HEADER = [
    "Binder Name", "Binder Type", "Name", "Set code", "Set name",
    "Collector number", "Foil", "Rarity", "Quantity", "ManaBox ID",
    "Scryfall ID", "Purchase price", "Misprint", "Altered", "Condition",
    "Language", "Purchase price currency", "Added",
]

SYNTHETIC_COLLECTIONS = [
    "collections/synthetic-edge-cases.csv",
    "collections/synthetic-kitchen20-pool.csv",
    "collections/synthetic-standard-pool.csv",
]


def synthetic_rows(ctx):
    for rel in SYNTHETIC_COLLECTIONS:
        for r in ctx.read_manabox_csv(rel):
            yield rel, r


def real_rows(ctx):
    return ctx.read_manabox_csv("collections/real-collection.csv")


# The three gap predicates below grade both halves of "cover what the real
# Export lacks": the synthetics carry the value AND the real Export still
# lacks it — if the real Export ever gains one, the synthetic's reason to
# exist is gone and the run goes red instead of silently hollow.

def check_etched_foil(ctx):
    hits = [f"{rel}: {r['Name']}" for rel, r in synthetic_rows(ctx) if r["Foil"] == "etched"]
    gained = sorted({r["Name"] for r in real_rows(ctx) if r["Foil"] == "etched"})
    return bool(hits) and not gained, (
        f"etched Foil rows: {hits or 'none'}; "
        + (f"real Export gained etched ({gained[:3]}) — no longer a gap" if gained
           else "real Export still lacks etched")
    )


def check_non_english_languages(ctx):
    langs = {}
    for rel, r in synthetic_rows(ctx):
        if r["Language"] != "en":
            langs.setdefault(r["Language"], f"{rel}: {r['Name']}")
    missing = {"ja", "zhs"} - set(langs)
    gained = sorted(set(langs) & {r["Language"] for r in real_rows(ctx)})
    return not missing and not gained, (
        f"non-English rows: {langs or 'none'}; missing: {sorted(missing) or 'none'}; "
        + (f"real Export gained {gained} — no longer a gap" if gained
           else "real Export still lacks them")
    )


def check_promo_collector_numbers(ctx):
    hits = [
        f"{rel}: {r['Name']} ({r['Set code']}) {r['Collector number']}"
        for rel, r in synthetic_rows(ctx)
        if not r["Collector number"].isdigit()
    ]
    gained = sorted({
        r["Collector number"] for r in real_rows(ctx)
        if not r["Collector number"].isdigit()
    })
    return bool(hits) and not gained, (
        f"promo collector numbers: {hits or 'none'}; "
        + (f"real Export gained non-digit numbers ({gained[:3]}) — no longer a gap" if gained
           else "real Export still lacks them")
    )


def check_per_format_pools(ctx):
    problems, evidence = [], []
    for rel, want in [
        ("collections/synthetic-kitchen20-pool.csv", "Uncharted Haven"),
        ("collections/synthetic-standard-pool.csv", None),
    ]:
        raw = ctx.path(rel).read_bytes().decode("utf-8-sig")
        header = next(csv.reader(io.StringIO(raw)))
        if header != MANABOX_HEADER:
            problems.append(f"{rel}: header differs from the ManaBox 18-column header")
            continue
        rows = list(csv.DictReader(io.StringIO(raw)))
        if len(rows) < 13:
            problems.append(f"{rel}: only {len(rows)} rows — not a shaped pool")
        if want and not any(r["Name"] == want for r in rows):
            problems.append(f"{rel}: missing {want}")
        if want is None and not any(r["Quantity"] == "4" for r in rows):
            problems.append(f"{rel}: no playset (Quantity 4) rows")
        evidence.append(f"{rel}: {len(rows)} rows, exact ManaBox header")
    return not problems, "; ".join(problems or evidence)


# The nine canonical Brief keys (spec #52), in Brief Block order — the one
# copy in this file. skills/brief/scripts/validate_brief.py carries its own
# on purpose: skill assets stay self-contained across the skill/eval boundary.
BRIEF_CANONICAL_KEYS = (
    "name", "format", "centerpiece", "identity", "play variant",
    "power", "constraint", "donor", "notes",
)


def parse_brief_lines(text):
    """The harness's own flat ``key: value`` read of a fixture Brief —
    deliberately independent of the skill's validator, never imported from it.

    Returns (entries, problems): (key, value) pairs in file order, plus one
    problem per line that is not a canonical non-empty ``key: value`` line.
    """
    entries, problems = [], []
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not value.strip() or key not in BRIEF_CANONICAL_KEYS:
            problems.append(f"not a canonical 'key: value' line: {line!r}")
            continue
        entries.append((key, value.strip()))
    return entries, problems


BOARD_HEADERS = {"// Commander", "// Mainboard", "// Sideboard", "// Maybeboard"}
BASIC_NAMES = {"Plains", "Island", "Swamp", "Forest", "Mountain", "Wastes"}

# Deck-line grammar. fixtures/scryfall/refresh_snapshot.py carries a verbatim
# copy of these two regexes (kept in lockstep by hand, not imported), so the
# snapshot coverage check reads the fixtures with the same grammar the refresh
# used. Edit them together.
PINNED_LINE = re.compile(
    r"^(\d+) (.+) \(([A-Z0-9]{2,6})\) (\S+)(?: // (.+))?$"
)
BARE_LINE = re.compile(r"^(\d+) (.+?)(?: // (.+))?$")


def check_fixture_briefs(ctx):
    briefs = sorted(ctx.path("briefs").glob("*.txt"))
    if len(briefs) < 2:
        return False, f"only {len(briefs)} fixture Briefs under briefs/"
    problems = []
    for brief in briefs:
        entries, brief_problems = parse_brief_lines(brief.read_text(encoding="utf-8"))
        problems += [f"{brief.name}: {p}" for p in brief_problems]
        if "format" not in {key for key, _ in entries}:
            problems.append(f"{brief.name}: missing the required format: line")
    return not problems, "; ".join(problems) or f"{len(briefs)} Briefs, all flat key: value with format:"


def parse_deck_block(text):
    """Parse a Deck Block; return (card_lines, problems). card_lines are
    (qty, name, set_code_or_None, number_or_None) tuples."""
    lines = text.splitlines()
    problems, cards, boards = [], [], []
    if not lines or not lines[0].startswith("// "):
        problems.append("first line is not a '// <name>' title comment")
    for line in lines[1:]:
        if not line.strip():
            continue
        if line in BOARD_HEADERS:
            boards.append(line)
            continue
        if line.startswith("//"):
            problems.append(f"unrecognized comment/header line: {line!r}")
            continue
        m = PINNED_LINE.match(line)
        if m:
            cards.append((int(m.group(1)), m.group(2), m.group(3), m.group(4)))
            continue
        m = BARE_LINE.match(line)
        if m:
            cards.append((int(m.group(1)), m.group(2), None, None))
            continue
        problems.append(f"unparseable card line: {line!r}")
    if not boards:
        problems.append("no Board headers")
    if not cards:
        problems.append("no card lines")
    return cards, problems


def check_fixture_decks(ctx):
    decks = sorted(ctx.path("decks").glob("*.txt"))
    if not decks:
        return False, "no fixture Decks under decks/"
    problems, evidence = [], []
    for deck in decks:
        cards, deck_problems = parse_deck_block(deck.read_text(encoding="utf-8"))
        problems += [f"{deck.name}: {p}" for p in deck_problems]
        unpinned_nonbasics = [
            name for _, name, set_code, _ in cards
            if set_code is None and name not in BASIC_NAMES
        ]
        if unpinned_nonbasics:
            problems.append(f"{deck.name}: nonbasics without a printing pin: {unpinned_nonbasics}")
        evidence.append(f"{deck.name}: {sum(q for q, *_ in cards)} cards")
    return not problems, "; ".join(problems or evidence)


def check_planted_flaws(ctx):
    manifest = json.loads(ctx.path("manifest.json").read_text(encoding="utf-8"))
    flawed = manifest.get("planted_flaws", {})
    if not flawed:
        return False, "manifest registers no planted flaws"
    collection_names = {r["Name"] for rel in SYNTHETIC_COLLECTIONS + ["collections/real-collection.csv"]
                        for r in ctx.read_manabox_csv(rel)}
    problems = []
    for deck_rel, flaws in flawed.items():
        deck_path = ctx.path(deck_rel)
        if not deck_path.is_file():
            problems.append(f"{deck_rel}: registered but missing")
            continue
        deck_text = deck_path.read_text(encoding="utf-8")
        for flaw in flaws:
            for card in flaw["cards"]:
                if card not in deck_text:
                    problems.append(f"{deck_rel}: flaw {flaw['id']} names {card!r} not in the Deck")
                if flaw["class"] == "availability" and card in collection_names:
                    problems.append(
                        f"{deck_rel}: availability flaw {flaw['id']} card {card!r} is owned"
                    )
    for clean_rel in manifest.get("clean_decks", []):
        if not ctx.path(clean_rel).is_file():
            problems.append(f"clean deck {clean_rel} missing")
        if clean_rel in flawed:
            problems.append(f"{clean_rel} listed both clean and flawed")
    flaw_count = sum(len(f) for f in flawed.values())
    return not problems, "; ".join(problems) or (
        f"{flaw_count} planted flaws across {len(flawed)} Decks, "
        f"{len(manifest.get('clean_decks', []))} clean Decks"
    )


def load_snapshot(ctx):
    """Read snapshot.jsonl; return (meta, cards)."""
    lines = ctx.path("scryfall/snapshot.jsonl").read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])["snapshot_meta"]
    return meta, [json.loads(line) for line in lines[1:]]


def fixture_card_references(ctx):
    """Every card reference the fixtures make, re-read from the fixture files.

    Not an independent parse: this walks the same files with the same
    PINNED_LINE/BARE_LINE grammar refresh_snapshot.py copies, so the coverage
    check is a fixture-vs-snapshot drift tripwire — a shared grammar bug
    would blind both sides.

    Returns (ids, pins, names): Scryfall IDs from Collection CSVs,
    (set, collector number) pins and bare names from Deck texts.
    """
    ids, pins, names = set(), set(), set()
    for csv_path in sorted(ctx.path("collections").glob("*.csv")):
        for row in ctx.read_manabox_csv(f"collections/{csv_path.name}"):
            if row.get("Scryfall ID", "").strip():
                ids.add(row["Scryfall ID"].strip())
    deck_paths = sorted(ctx.path("decks").glob("*.txt"))
    deck_paths.append(ctx.path("collections/real-deck.txt"))
    for deck_path in deck_paths:
        for line in deck_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("//"):
                continue
            m = PINNED_LINE.match(line)
            if m:
                pins.add((m.group(3).lower(), m.group(4)))
                continue
            m = BARE_LINE.match(line)
            if m:
                names.add(m.group(2))
    return ids, pins, names


def check_snapshot_coverage(ctx):
    meta, cards = load_snapshot(ctx)
    problems = []
    if "captured_at" not in meta:
        problems.append("snapshot metadata line lacks captured_at")
    if meta.get("card_count") != len(cards):
        problems.append(
            f"metadata card_count {meta.get('card_count')} != {len(cards)} card lines"
        )
    snap_ids = {c["id"] for c in cards}
    snap_pins = {(c["set"], c["collector_number"]) for c in cards}
    snap_names = {c["name"] for c in cards}
    snap_names |= {f["name"] for c in cards for f in c.get("card_faces", [])}

    ids, pins, names = fixture_card_references(ctx)
    missing = [i for i in sorted(ids) if i not in snap_ids]
    missing += [f"{s.upper()} {n}" for s, n in sorted(pins) if (s, n) not in snap_pins]
    missing += [n for n in sorted(names) if n not in snap_names]
    if missing:
        problems.append(f"fixture cards absent from the snapshot: {missing[:10]}")

    orphans = [
        f"{c['name']} ({c['set'].upper()}) {c['collector_number']}"
        for c in cards
        if c["id"] not in ids
        and (c["set"], c["collector_number"]) not in pins
        and c["name"] not in names
        and not any(f["name"] in names for f in c.get("card_faces", []))
    ]
    if orphans:
        problems.append(f"snapshot cards no fixture references: {orphans[:10]}")

    return not problems, "; ".join(problems) or (
        f"{len(cards)} snapshot cards captured {meta['captured_at']} cover "
        f"{len(ids)} Collection printings, {len(pins)} Deck pins, "
        f"{len(names)} bare names — exactly"
    )


ORACLE_FIELDS = {
    "name", "mana_value", "colors", "color_identity", "type_line",
    "oracle_text", "legalities", "game_changer",
}
TOKEN_LAYOUTS = {"token", "double_faced_token", "emblem", "art_series"}


def load_oracle(ctx):
    lines = ctx.path("scryfall/oracle.jsonl").read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])["oracle_meta"]
    return meta, [json.loads(line) for line in lines[1:]]


def check_oracle_rederivation(ctx):
    import subprocess
    derived = subprocess.run(
        [sys.executable, str(ctx.path("scryfall/derive_oracle.py")), "--stdout"],
        capture_output=True, text=True, timeout=120,
    )
    if derived.returncode != 0:
        return False, f"derive_oracle.py failed: {derived.stderr.strip()[:200]}"
    committed = ctx.path("scryfall/oracle.jsonl").read_text(encoding="utf-8")
    if derived.stdout != committed:
        return False, "committed oracle.jsonl differs from a fresh derivation of the snapshot"
    return True, f"oracle.jsonl reproduced byte-identical ({len(committed.splitlines()) - 1} cards)"


def check_oracle_shape(ctx):
    meta, records = load_oracle(ctx)
    _, snapshot_cards = load_snapshot(ctx)
    problems = []
    if meta.get("card_count") != len(records):
        problems.append(f"metadata card_count {meta.get('card_count')} != {len(records)} lines")
    names = [r["name"] for r in records]
    if names != sorted(names) or len(names) != len(set(names)):
        problems.append("Oracle lines are not unique name-sorted")
    for r in records:
        if set(r) != ORACLE_FIELDS:
            problems.append(f"{r.get('name', '?')}: fields {sorted(r)} != the Oracle shape")
            break
        if set(r["legalities"]) != {"standard", "pioneer", "modern", "commander"}:
            problems.append(f"{r['name']}: legalities not trimmed to the four sanctioned Formats")
            break
        if not isinstance(r["game_changer"], bool):
            problems.append(f"{r['name']}: game_changer is not a boolean")
            break
    token_names = {c["name"] for c in snapshot_cards if c.get("layout") in TOKEN_LAYOUTS}
    playable_names = {c["name"] for c in snapshot_cards if c.get("layout") not in TOKEN_LAYOUTS}
    leaked = sorted((token_names - playable_names) & set(names))
    if leaked:
        problems.append(f"token rows leaked into the Oracle: {leaked[:5]}")
    if playable_names - set(names):
        problems.append(f"playable snapshot cards missing: {sorted(playable_names - set(names))[:5]}")
    if not any(" // " in n for n in names):
        problems.append("no multi-faced name flattened with //")
    if not {"Plains", "Island", "Swamp", "Forest"} <= set(names):
        problems.append("basic lands missing from the Oracle")
    return not problems, "; ".join(problems) or (
        f"{len(records)} name-keyed lines, four-Format legalities, "
        f"{sum(1 for n in names if ' // ' in n)} flattened multi-faced names, tokens excluded"
    )


def check_oracle_watermark(ctx):
    meta, _ = load_oracle(ctx)
    snap_meta, _ = load_snapshot(ctx)
    problems = []
    if meta.get("generated_at") != snap_meta.get("captured_at"):
        problems.append(
            f"generated_at {meta.get('generated_at')} != snapshot captured_at {snap_meta.get('captured_at')}"
        )
    newest = ""
    for csv_path in sorted(ctx.path("collections").glob("*.csv")):
        for row in ctx.read_manabox_csv(f"collections/{csv_path.name}"):
            newest = max(newest, row.get("Added", "").strip())
    if meta.get("source_export_newest_added") != newest:
        problems.append(
            f"watermark {meta.get('source_export_newest_added')} != newest fixture Added {newest}"
        )
    return not problems, "; ".join(problems) or (
        f"generated_at {meta['generated_at']}, source Export watermark {newest}"
    )


SCRYFALL_HOST = "api." + "scryfall.com"  # the tripwire literal, split so this file stays out of its own scan
NETWORK_ALLOWED = {
    "fixtures/scryfall/refresh_snapshot.py",  # the one deliberate network path
    "fixtures/scryfall/snapshot.jsonl",       # records api_host as provenance
}


def check_offline_guarantee(_ctx):
    """Tripwire, not proof: scan the eval tree's text files for the literal
    host string. A file that reaches Scryfall without spelling the host out
    (or spelling it in pieces, as this one does) would slip past."""
    offenders = []
    for path in sorted(EVALS_DIR.rglob("*")):
        if not path.is_file() or "results" in path.parts:
            continue
        relative = path.relative_to(EVALS_DIR).as_posix()
        if relative in NETWORK_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SCRYFALL_HOST in text:
            offenders.append(relative)
    return not offenders, (
        f"files carrying the literal Scryfall host string: {offenders}"
        if offenders
        else f"the literal Scryfall host string appears only in {sorted(NETWORK_ALLOWED)}"
    )


# --- Oracle skill predicates (issue #51) ------------------------------------
# The oracle-smoke case runs the skill's deterministic seam — the
# build_oracle.py CLI — offline, resolution pinned to the committed snapshot.
# Never the live API.

ORACLE_SCRIPT = REPO_ROOT / "skills" / "oracle" / "scripts" / "build_oracle.py"


def run_oracle_script(ctx, csv_text=None, expect_failure=False):
    """Run build_oracle.py in a temp Collection home, offline.

    With csv_text, that text is the Export; otherwise the realism Export is
    copied in. Returns (completed_process, oracle_path, home_path).
    """
    import atexit
    import shutil
    import subprocess
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="oracle-smoke-"))
    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    export = tmp / "collection.csv"
    if csv_text is None:
        shutil.copy(ctx.path("collections/real-collection.csv"), export)
    else:
        export.write_text(csv_text, encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable, str(ORACLE_SCRIPT),
            "--collection", str(export),
            "--snapshot", str(ctx.path("scryfall/snapshot.jsonl")),
        ],
        capture_output=True, text=True, timeout=300,
    )
    if completed.returncode != 0 and not expect_failure:
        raise AssertionError(
            f"build_oracle.py failed: {completed.stderr.strip()[:200]}"
        )
    return completed, tmp / "oracle.jsonl", tmp


def first_snapshot_card(ctx):
    _, cards = load_snapshot(ctx)
    return next(c for c in cards if c.get("layout") == "normal")


def check_oracle_skill_output(ctx):
    _, oracle_path, _ = run_oracle_script(ctx)
    if not oracle_path.is_file():
        return False, "no oracle.jsonl written beside the Export"
    lines = oracle_path.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0]).get("oracle_meta", {})
    snap_meta, _ = load_snapshot(ctx)
    problems = []
    if meta.get("generated_at") != snap_meta.get("captured_at"):
        problems.append(
            f"generated_at {meta.get('generated_at')} != snapshot captured_at "
            f"{snap_meta.get('captured_at')} (offline runs pin freshness to the snapshot)"
        )
    newest = max(
        (r.get("Added", "").strip() for r in ctx.read_manabox_csv("collections/real-collection.csv")),
        default="",
    )
    if meta.get("source_export_newest_added") != newest:
        problems.append(
            f"watermark {meta.get('source_export_newest_added')} != the Export's newest Added {newest}"
        )
    names = [json.loads(line)["name"] for line in lines[1:]]
    if not names or names != sorted(names) or len(names) != len(set(names)):
        problems.append("body lines are not one sorted line per unique card name")
    return not problems, "; ".join(problems) or (
        f"oracle.jsonl beside the Export: {len(names)} unique names, "
        f"generated_at {meta['generated_at']}, watermark {newest}"
    )


def check_oracle_skill_agreement(ctx):
    _, oracle_path, _ = run_oracle_script(ctx)
    written = oracle_path.read_text(encoding="utf-8").splitlines()[1:]
    fixture_by_name = {}
    for line in ctx.path("scryfall/oracle.jsonl").read_text(encoding="utf-8").splitlines()[1:]:
        fixture_by_name[json.loads(line)["name"]] = line
    problems = []
    names = []
    uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    for line in written:
        name = json.loads(line)["name"]
        names.append(name)
        if fixture_by_name.get(name) != line:
            problems.append(f"{name}: line differs from the fixture Oracle's")
            break
        if uuid.search(line):
            problems.append(f"{name}: a UUID leaked into the Oracle")
            break
    _, snapshot_cards = load_snapshot(ctx)
    token_only = {c["name"] for c in snapshot_cards if c.get("layout") in TOKEN_LAYOUTS} - {
        c["name"] for c in snapshot_cards if c.get("layout") not in TOKEN_LAYOUTS
    }
    leaked = sorted(token_only & set(names))
    if leaked:
        problems.append(f"token rows leaked: {leaked[:3]}")
    if "Forest" not in names:
        problems.append("basic lands missing")
    if not any(" // " in n for n in names):
        problems.append("no multi-faced name flattened with //")
    return not problems, "; ".join(problems) or (
        f"all {len(written)} written lines byte-identical to the fixture Oracle; "
        "tokens out, basics in, multi-faced names flattened"
    )


def check_oracle_skill_tolerance(ctx):
    card = first_snapshot_card(ctx)
    good = f"\"{card['name']}\",{card['set'].upper()},{card['id']},2026-08-02T09:00:00.000Z\n"
    completed, oracle_path, _ = run_oracle_script(
        ctx,
        csv_text="Name,Set code,Scryfall ID,Added\n" + good + "Orphan,,,\n,,,\n",
    )
    problems = []
    if "2 malformed rows skipped" not in completed.stdout:
        problems.append("malformed rows not reported with a count")
    if "row 3" not in completed.stdout:
        problems.append("skipped-row examples missing from the report")
    if card["name"] not in oracle_path.read_text(encoding="utf-8"):
        problems.append("the well-formed row no longer resolves")

    completed, oracle_path, _ = run_oracle_script(
        ctx, csv_text="Binder Name,Quantity\nB,1\n", expect_failure=True,
    )
    if completed.returncode != 2 or "identity columns" not in completed.stderr:
        problems.append(
            f"a header without identity columns must hard-fail naming them "
            f"(exit {completed.returncode}: {completed.stderr.strip()[:120]})"
        )
    elif oracle_path.exists():
        problems.append("an Oracle was written despite the hard failure")
    return not problems, "; ".join(problems) or (
        "malformed rows skipped and reported with count and examples; "
        "the identity-column header check is the one hard failure"
    )


def check_oracle_skill_fallback(ctx):
    card = first_snapshot_card(ctx)
    completed, oracle_path, _ = run_oracle_script(
        ctx,
        csv_text=(
            "Name,Set code,Scryfall ID,Added\n"
            f"\"{card['name']}\",{card['set'].upper()},"
            "00000000-0000-0000-0000-000000000000,2026-08-02T09:00:00.000Z\n"
        ),
    )
    problems = []
    if "1 by Name + Set code fallback" not in completed.stdout:
        problems.append("the fallback resolution is not reported")
    names = [
        json.loads(line)["name"]
        for line in oracle_path.read_text(encoding="utf-8").splitlines()[1:]
    ]
    if names != [card["name"]]:
        problems.append(f"expected [{card['name']}] via fallback, got {names}")
    return not problems, "; ".join(problems) or (
        f"an unknown Scryfall ID resolved through Name + Set code: {card['name']}"
# --- Brief skill predicates (issue #52) -------------------------------------
# The brief conversation is prompt-ware: its behavioral expectations (fires
# from natural language; scripted answers yield the Brief; a pasted Export
# beats the file) stay soft, dev-time judged. These predicates grade the
# deterministic shadows: wiring, the validator and freshness scripts (wrapped,
# never re-implemented), and the fixture Briefs those scripts must accept —
# where a predicate needs Brief fields rather than a verdict, it reads them
# through parse_brief_lines, the harness's own fixture read.

BRIEF_SKILL_PATH = REPO_ROOT / "skills" / "brief" / "SKILL.md"
BRIEF_COMMAND_PATH = REPO_ROOT / "commands" / "brief.md"
BRIEF_VALIDATOR = REPO_ROOT / "skills" / "brief" / "scripts" / "validate_brief.py"
BRIEF_FRESHNESS = REPO_ROOT / "skills" / "brief" / "scripts" / "freshness.py"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"

PLAY_VARIANTS = {"archenemy", "two-headed giant", "jumpstart 40"}


def run_brief_script(script, *args):
    import subprocess

    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True, text=True, timeout=120,
    )


def check_brief_wiring(_ctx):
    problems = []
    command = BRIEF_COMMAND_PATH.read_text(encoding="utf-8")
    if "skills/brief/SKILL.md" not in command:
        problems.append("commands/brief.md never hands off to skills/brief/SKILL.md")
    skill = BRIEF_SKILL_PATH.read_text(encoding="utf-8")
    pinned = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))["version"]
    m = re.search(r"^metadata:\n[ \t]+version:[ \t]*(\S+)", skill, re.MULTILINE)
    if not m:
        problems.append("skills/brief/SKILL.md carries no metadata.version")
    elif m.group(1) != pinned:
        problems.append(
            f"skill metadata.version {m.group(1)} != pinned plugin version {pinned}"
        )
    return not problems, "; ".join(problems) or (
        f"/tutor:brief wraps skills/brief/SKILL.md, versioned {pinned} in lockstep"
    )


def check_brief_nl_triggers(_ctx):
    """Tripwire, not proof: the structural half of "fires from natural
    language" is a description naming deck intents beyond the command; the
    firing itself is the soft expectation, judged at dev time."""
    skill = BRIEF_SKILL_PATH.read_text(encoding="utf-8")
    m = re.search(r"^description:[ \t]*(.+)$", skill, re.MULTILINE)
    if not m:
        return False, "skills/brief/SKILL.md frontmatter has no description line"
    description = m.group(1)
    missing = [n for n in ("/tutor:brief", "new deck", "deck idea") if n not in description]
    return not missing, (
        f"description lacks {missing}" if missing
        else "the description names /tutor:brief plus natural-language deck intents"
    )


def check_fixture_briefs_validate(ctx):
    manifest = json.loads(ctx.path("manifest.json").read_text(encoding="utf-8"))
    pairings = manifest.get("briefs", {})
    briefs = sorted(ctx.path("briefs").glob("*.txt"))
    if not briefs:
        return False, "no fixture Briefs to validate"
    problems, donor_checked = [], 0
    for brief in briefs:
        args = [brief]
        pool = pairings.get(f"briefs/{brief.name}", {}).get("pool")
        if pool:
            args += ["--collection", ctx.path(pool)]
            donor_checked += 1
        result = run_brief_script(BRIEF_VALIDATOR, *args)
        if result.returncode != 0:
            verdict = result.stdout.strip() or result.stderr.strip()
            problems.append(f"{brief.name}: {verdict[:200]}")
    return not problems, "; ".join(problems) or (
        f"{len(briefs)} fixture Briefs valid, {donor_checked} checked against their paired Export"
    )


def check_power_ladder(_ctx):
    import tempfile

    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        good = pathlib.Path(tmp) / "good.txt"
        good.write_text("format: commander\npower: 4, big villain turns\n", encoding="utf-8")
        bad = pathlib.Path(tmp) / "bad.txt"
        bad.write_text("format: commander\npower: 6\n", encoding="utf-8")
        good_run = run_brief_script(BRIEF_VALIDATOR, good)
        bad_run = run_brief_script(BRIEF_VALIDATOR, bad)
    if good_run.returncode != 0:
        problems.append(
            f"'power: 4, big villain turns' rejected: {good_run.stdout.strip()[:200]}"
        )
    if bad_run.returncode != 1:
        problems.append(f"'power: 6' not rejected (exit {bad_run.returncode})")
    return not problems, "; ".join(problems) or (
        "trailing free text passes, an out-of-ladder number fails — the 1-5 number is canonical"
    )


def check_donor_grammar(ctx):
    import tempfile

    export = ctx.path("collections/real-collection.csv")
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        all_brief = pathlib.Path(tmp) / "all.txt"
        all_brief.write_text("format: commander\ndonor: all\n", encoding="utf-8")
        unknown = pathlib.Path(tmp) / "unknown.txt"
        unknown.write_text("format: commander\ndonor: No Such Deck\n", encoding="utf-8")
        all_run = run_brief_script(BRIEF_VALIDATOR, all_brief, "--collection", export)
        unknown_run = run_brief_script(BRIEF_VALIDATOR, unknown, "--collection", export)
    if all_run.returncode != 0:
        problems.append(f"'donor: all' rejected: {all_run.stdout.strip()[:200]}")
    if unknown_run.returncode != 1:
        problems.append(
            f"an unrecognized donor Deck name passed (exit {unknown_run.returncode})"
        )
    return not problems, "; ".join(problems) or (
        "donor: all frees the whole Collection; an unknown Deck name is rejected "
        "against the Export's deck rows"
    )


def check_play_variants_never_formats(ctx):
    problems, archenemy_fixture = [], None
    for brief in sorted(ctx.path("briefs").glob("*.txt")):
        entries, _ = parse_brief_lines(brief.read_text(encoding="utf-8"))
        fields = {}
        for key, value in entries:
            fields.setdefault(key, value)
        if fields.get("format", "").lower() in PLAY_VARIANTS:
            problems.append(
                f"{brief.name}: format: {fields['format']!r} is a play variant, never a Format"
            )
        if fields.get("play variant", "").lower() == "archenemy":
            archenemy_fixture = brief.name
            if not fields.get("centerpiece"):
                problems.append(f"{brief.name}: the Archenemy Brief names no villain Centerpiece")
            if not fields.get("format"):
                problems.append(f"{brief.name}: the Archenemy Brief is still built to some Format")
    if archenemy_fixture is None:
        problems.append("no fixture Brief expresses Archenemy through play variant:")
    return not problems, "; ".join(problems) or (
        f"{archenemy_fixture} rides play variant: archenemy on a Format with the villain "
        "as Centerpiece; no Brief misfiles a variant as its Format"
    )


def check_freshness_helper(ctx):
    import datetime

    export = ctx.path("collections/real-collection.csv")
    oracle = ctx.path("scryfall/oracle.jsonl")
    with open(oracle, encoding="utf-8") as handle:
        meta = json.loads(handle.readline())["oracle_meta"]
    base = datetime.date.fromisoformat(meta["generated_at"][:10])
    fresh_today = (base + datetime.timedelta(days=2)).isoformat()
    stale_today = (base + datetime.timedelta(days=40)).isoformat()

    problems = []
    fresh = run_brief_script(
        BRIEF_FRESHNESS, "--collection", export, "--oracle", oracle, "--today", fresh_today
    )
    if (
        fresh.returncode != 0
        or "export newest added:" not in fresh.stdout
        or "signal export-newer-than-oracle: no" not in fresh.stdout
    ):
        problems.append(
            f"fresh Export/Oracle pair misreported (exit {fresh.returncode}): "
            f"{(fresh.stdout or fresh.stderr).strip()[:200]}"
        )
    stale = run_brief_script(
        BRIEF_FRESHNESS, "--collection", export, "--oracle", oracle, "--today", stale_today
    )
    if stale.returncode != 1 or "signal oracle-older-than-30-days: yes" not in stale.stdout:
        problems.append(
            f"a 40-day-old Oracle raised no staleness signal (exit {stale.returncode})"
        )
    absent = run_brief_script(BRIEF_FRESHNESS, "--collection", export, "--today", fresh_today)
    if absent.returncode != 0 or "oracle: absent" not in absent.stdout:
        problems.append(f"an absent Oracle did not degrade gracefully (exit {absent.returncode})")
    return not problems, "; ".join(problems) or (
        "newest Added surfaced, the 30-day signal fires on cue, and an absent Oracle degrades gracefully"
    )


def check_brief_skill_content(_ctx):
    """Tripwire, not proof: the skill is prompt-ware judged by its artifacts;
    these needles keep the load-bearing grammar sentences from silently
    vanishing in an edit."""
    text = BRIEF_SKILL_PATH.read_text(encoding="utf-8")
    needles = [f"{key}:" for key in BRIEF_CANONICAL_KEYS] + [
        "Only `format` is required",
        "no `budget:` key",
        "defaults to 2",
        "freshness question",
        "recognized by shape alone",
        "/tutor:build",
    ]
    missing = [n for n in needles if n not in text]
    return not missing, (
        f"skills/brief/SKILL.md lacks {missing}" if missing
        else "all nine canonical keys, the format-only requirement, the budget ban, "
             "the Power default, the single freshness question, and the Build handoff are pinned"
    )


# --- Registry: exact expectation text -> fixed predicate --------------------
# Keys are pinned verbatim to the strings in evals.json; editing a wording
# means editing both, deliberately. Unregistered expectations are soft.

EXPECTATION_CHECKS = {
    "The realism fixture collections/real-collection.csv parses header-keyed as CSV with exactly 577 data rows.":
        check_realism_row_count,
    "A synthetic Collection row carries the etched Foil value the real Export lacks.":
        check_etched_foil,
    "Synthetic Collection rows carry non-English Language codes the real Export lacks, including the disputed zhs.":
        check_non_english_languages,
    "A synthetic Collection row carries a promo collector number (letter-suffixed or starred) the real Export lacks.":
        check_promo_collector_numbers,
    "Per-Format shaped pool Collections cover Kitchen 20 (Uncharted Haven beside mono-white candidates) and Standard (playset quantities), parsing with the full ManaBox header.":
        check_per_format_pools,
    "Fixture Briefs parse as flat key: value Blocks with the required format: line and only canonical Brief keys.":
        check_fixture_briefs,
    "Fixture Decks parse as ManaBox-importable Deck Blocks: title comment, Board headers, quantity lines with set-and-number pins on nonbasics.":
        check_fixture_decks,
    "Some fixture Decks carry planted flaws for Review evals, each registered in the manifest and naming cards present in its Deck (or absent from every Collection for availability flaws).":
        check_planted_flaws,
    "The pinned Scryfall snapshot covers every card the fixtures reference and nothing else, with its capture metadata on line one.":
        check_snapshot_coverage,
    "The fixture Oracle scryfall/oracle.jsonl is byte-identical to a fresh offline derivation from the pinned snapshot.":
        check_oracle_rederivation,
    "Every Oracle line is name-keyed with mana value, colors, color identity, type line, oracle text, the four sanctioned legalities, and the game_changer flag — no UUIDs, tokens excluded, basics included, multi-faced names flattened with //.":
        check_oracle_shape,
    "The Oracle's first line records generated_at and the source Export's newest Added watermark.":
        check_oracle_watermark,
    "Evals never touch the network: a tripwire scan finds the literal live Scryfall API host string in no eval or fixture file except the deliberate refresh script and the snapshot's provenance metadata.":
        check_offline_guarantee,
    "Run offline against the pinned snapshot, the oracle script writes the Oracle beside the realism Export: line one records generated_at plus the source Export's newest Added watermark, then one line per unique card name.":
        check_oracle_skill_output,
    "Every Oracle line the script writes is byte-identical to the fixture Oracle's line for the same card — the shape-exact record with four-Format legalities, the game_changer boolean, tokens excluded, basics included, multi-faced names flattened with //, and no UUIDs.":
        check_oracle_skill_agreement,
    "Malformed Export rows are skipped and reported with a count and examples, and a header missing the identity columns is the only hard failure.":
        check_oracle_skill_tolerance,
    "An Export row whose Scryfall ID the snapshot no longer knows still resolves through its Name + Set code.":
        check_oracle_skill_fallback,
    "The /tutor:brief command is a thin wrapper handing off to the brief skill, whose metadata.version matches the plugin manifest's pinned version.":
        check_brief_wiring,
    "The brief skill's description fires from natural language: it names deck-intent triggers beyond the /tutor:brief command itself.":
        check_brief_nl_triggers,
    "Every fixture Brief validates against the brief skill's validator, donors recognized from its manifest-paired Export's deck rows.":
        check_fixture_briefs_validate,
    "The validator holds the Power ladder: a 1-5 number with trailing free text passes and an out-of-ladder number fails.":
        check_power_ladder,
    "The validator holds donor grammar: donor: all passes and an unrecognized donor Deck name fails against the Export's deck rows.":
        check_donor_grammar,
    "No fixture Brief declares a play variant as its format:, and the Archenemy fixture expresses the variant in play variant: with the Centerpiece naming the villain.":
        check_play_variants_never_formats,
    "The freshness helper surfaces the fixture Export's newest Added and both Oracle staleness signals deterministically, and degrades gracefully when the Oracle is absent.":
        check_freshness_helper,
    "The brief skill's text pins the grammar it must emit: all nine canonical keys, only format required, no budget key, Power defaulting to 2, one freshness question, and a closing handoff to Build.":
        check_brief_skill_content,
}


# --- Runner -----------------------------------------------------------------

def load_cases():
    data = json.loads((EVALS_DIR / "evals.json").read_text(encoding="utf-8"))
    return data["skill_name"], data["evals"]


def case_name(case):
    return CASE_NAMES.get(case["id"], f"eval-{case['id']}")


def grade_case(case, ctx, out_dir):
    """Grade one case's mechanical expectations; return (all_passed, lines)."""
    name = case_name(case)
    graded, soft, lines = [], [], [f"## {name} (eval id {case['id']})"]
    for text in case["expectations"]:
        checker = EXPECTATION_CHECKS.get(text)
        if checker is None:
            soft.append(text)
            lines.append(f"soft   — {text}")
            continue
        try:
            passed, evidence = checker(ctx)
        except Exception as exc:  # a crashed predicate is a red, with evidence
            passed, evidence = False, f"predicate raised {type(exc).__name__}: {exc}"
        graded.append({"text": text, "passed": passed, "evidence": evidence})
        lines.append(f"{'green' if passed else 'RED  '}  — {text}")
        if not passed:
            lines.append(f"         evidence: {evidence}")

    passed_n = sum(1 for e in graded if e["passed"])
    failed_n = len(graded) - passed_n
    case_dir = out_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "eval_metadata.json").write_text(
        json.dumps(
            {
                "eval_id": case["id"],
                "eval_name": name,
                "prompt": case["prompt"],
                "assertions": list(case["expectations"]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (case_dir / "grading.json").write_text(
        json.dumps(
            {
                "expectations": graded,
                "summary": {
                    "passed": passed_n,
                    "failed": failed_n,
                    "total": len(graded),
                    "pass_rate": round(passed_n / len(graded), 4) if graded else 0.0,
                },
                "soft_expectations": soft,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines.append(
        f"{passed_n}/{len(graded)} mechanical expectations green"
        + (f"; {len(soft)} soft (dev-time judgment)" if soft else "")
    )
    return failed_n == 0, lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", help="run only the case with this name or id")
    parser.add_argument(
        "--fixture-root",
        default=str(EVALS_DIR / "fixtures"),
        help="fixture tree to grade (default: evals/fixtures)",
    )
    parser.add_argument(
        "--out",
        default=str(EVALS_DIR / "results"),
        help="where per-case results land (default: evals/results)",
    )
    args = parser.parse_args(argv)

    skill_name, cases = load_cases()
    if args.case:
        cases = [
            c for c in cases
            if args.case in (str(c["id"]), case_name(c))
        ]
        if not cases:
            print(f"no eval case named {args.case!r}", file=sys.stderr)
            return 2

    ctx = Context(args.fixture_root)
    out_dir = pathlib.Path(args.out)
    print(f"# {skill_name} offline eval run")
    all_green = True
    for case in cases:
        ok, lines = grade_case(case, ctx, out_dir)
        all_green = all_green and ok
        print()
        print("\n".join(lines))

    print()
    print("GREEN — offline eval run passed" if all_green else "RED — offline eval run failed")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
