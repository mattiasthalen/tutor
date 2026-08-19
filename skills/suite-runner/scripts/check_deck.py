#!/usr/bin/env python3
"""tutor Suite runner — the one deterministic code seam (ADR 0005).

The Suite is declarative data generated once at Build start: snapshotted
Format-profile targets, quotas, mechanical Brief constraints, Role tags
(judgment recorded once per card), and a check list whose ids resolve to the
fixed predicates below. This runner interprets any such Suite over Deck,
Oracle, and Collection files, offline — the Suite is the runner's input,
never code. Same Deck, same card facts, same verdict, every run.

Ported from the suite-shape prototype (branch
claude/deck-test-artifact-shape-wk1txl), the reference implementation; its
captured runs are this runner's offline test fixtures.

stdlib only, on purpose: the runner must execute wherever a bare Python 3 is
available, with nothing to install. The YAML subset parser below exists so
the Suite stays human-readable without buying a dependency.

Usage:
  python3 check_deck.py --suite suite.yaml --deck deck.txt \
      --oracle oracle.jsonl --collection collection.csv    # run, print report Block
  python3 check_deck.py --suite suite.yaml --render-checklist
                                                           # walkable checklist from the same Suite
  --date YYYY-MM-DD pins the report's date line (defaults to today), so two
  runs over the same inputs are byte-identical and diff cleanly.

Exit code: 0 when every Check is green, 1 when any is red.
"""

import argparse, csv, json, math, re, sys
from datetime import date

# ---------- tiny YAML-subset parser (2-space indents, dicts, lists, inline [a, b]) ----------

def parse_scalar(s):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [parse_scalar(x) for x in inner.split(",")] if inner else []
    if s in ("true", "false"):
        return s == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s

def parse_yaml(text):
    lines = [l.rstrip() for l in text.splitlines()
             if l.strip() and not l.strip().startswith("#")]

    def indent_of(l):
        return len(l) - len(l.lstrip())

    def parse_block(i, ind):
        if lines[i].lstrip().startswith("- "):
            items = []
            while i < len(lines) and indent_of(lines[i]) == ind and lines[i].lstrip().startswith("- "):
                head = lines[i].lstrip()[2:]
                if ":" in head:  # list of dicts: "- key: value" + deeper keys
                    item = {}
                    k, _, v = head.partition(":")
                    item[k.strip()] = parse_scalar(v)
                    i += 1
                    while i < len(lines) and indent_of(lines[i]) == ind + 2 and not lines[i].lstrip().startswith("- "):
                        k, _, v = lines[i].lstrip().partition(":")
                        item[k.strip()] = parse_scalar(v)
                        i += 1
                    items.append(item)
                else:
                    items.append(parse_scalar(head))
                    i += 1
            return items, i
        out = {}
        while i < len(lines) and indent_of(lines[i]) == ind:
            l = lines[i].lstrip()
            k, _, v = l.partition(":")
            if v.strip():
                out[k.strip()] = parse_scalar(v)
                i += 1
            else:
                sub, i2 = parse_block(i + 1, indent_of(lines[i + 1])) if i + 1 < len(lines) and indent_of(lines[i + 1]) > ind else ({}, i + 1)
                out[k.strip()] = sub
                i = i2
        return out, i

    val, _ = parse_block(0, 0)
    return val

# ---------- Deck Block parser (ManaBox-importable text, per the Block-formats decision) ----------

PIN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]{2,5})\)\s+(\S+)$")
LUMP = re.compile(r"^(\d+)\s+([^(]+)$")

def parse_deck(text):
    name, board, cards = None, None, []   # cards: (qty, name)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//"):
            head = line[2:].strip()
            if head in ("Commander", "Mainboard", "Sideboard", "Maybeboard"):
                board = head
            elif name is None:
                name = head
            continue
        if board == "Maybeboard":     # wishlist: not part of the playable Deck
            continue
        # Multi-faced names are flattened with " // " (the Oracle's own
        # vocabulary), so a pinned line is matched raw first — the trailing
        # "(SET) number" anchors the name — and only then is one trailing
        # " // comment" stripped for pinned-with-comment and bare lines.
        stripped = line.rsplit(" // ", 1)[0].strip() if " // " in line else line
        m = PIN.match(line) or PIN.match(stripped) or LUMP.match(stripped)
        if m:
            cards.append((int(m.group(1)), m.group(2).strip()))
    # An untitled Block keeps name None: the report falls back to "Untitled"
    # at the print seam, while the availability Check's self-free filter sees
    # None — so a ManaBox deck literally named "Untitled" stays committed.
    return name, cards

# ---------- data access ----------

def load_oracle(path):
    """Card facts by name, in either Oracle form: `oracle.jsonl` — the
    Collection-home file (ADR 0007), JSON Lines whose first line is a metadata
    record (`generated_at` plus the source-Export watermark) — or a plain JSON
    array. Sniffed by the first character; records without a card `name`
    (the metadata line) are skipped."""
    with open(path) as f:
        text = f.read()
    if text.lstrip().startswith("["):
        records = json.loads(text)
    else:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    return {c["name"]: c for c in records if "name" in c}

def load_collection(path):
    """Owned copies by card name from the Collection Export. Header-keyed,
    UTF-8 with BOM tolerance, malformed rows skipped — the ingestion posture
    of spec #46, mirroring the owned side of the build skill's availability.py
    `load_pool` — kept in lockstep by hand, never imported, because skill
    assets stay self-contained. Edit the two together."""
    counts = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("Name") or "").strip()
            try:
                quantity = int(row.get("Quantity", 1))
            except (TypeError, ValueError):
                continue
            if not name:
                continue
            counts[name] = counts.get(name, 0) + quantity
    return counts

def load_commitments(path):
    """Copies already committed to existing Decks: Export rows with Binder
    Type `deck` belong to the Deck named by Binder Name. Returns
    {card name: {deck name: copies}}; empty wherever the Export carries no
    binder columns. Read only when the Suite's constraints carry a donors
    entry — the contention-aware availability Check (issue #54). Header-keyed,
    UTF-8 with BOM tolerance, malformed rows skipped — the ingestion posture
    of spec #46.

    A deliberate mirror of the build skill's availability.py `load_pool`
    committed-side reading — kept in lockstep by hand, never imported,
    because skill assets stay self-contained. Edit the two together."""
    committed = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("Name") or "").strip()
            try:
                quantity = int(row.get("Quantity", 1))
            except (TypeError, ValueError):
                continue
            if not name:
                continue
            if (row.get("Binder Type") or "").strip() != "deck":
                continue
            deck = (row.get("Binder Name") or "").strip()
            if not deck:
                continue
            decks = committed.setdefault(name, {})
            decks[deck] = decks.get(deck, 0) + quantity
    return committed

def is_land(card):
    return "Land" in card.get("type_line", "")

def is_basic(card):
    return card.get("type_line", "").startswith("Basic Land")

def mana_value(card):
    """Mana value of a card, under either Oracle vocabulary: `cmc` (the
    suite-shape prototype's fixtures) or `mana_value` (the Collection-home
    Oracle of ADR 0007, issue #48)."""
    return card["cmc"] if "cmc" in card else card["mana_value"]

BASIC_LAND_TYPE_MANA = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
ADD_CLAUSE = re.compile(r"\b[Aa]dd\b([^.\n]*)")
MANA_SYMBOL = re.compile(r"\{([WUBRGC])\}")
ANY_COLOR_CLAUSE = re.compile(
    r"mana of any(?: one)? color|of the chosen color|of that color|in any combination")

def produced_mana(card):
    """Mana a land can produce, under either Oracle vocabulary: the
    `produced_mana` field (the suite-shape prototype's fixtures) or — for the
    Collection-home Oracle of ADR 0007, which carries no such field — derived
    deterministically from the type line's basic land types and the oracle
    text's "Add ..." abilities (a chosen-/any-color ability produces all
    five)."""
    if "produced_mana" in card:
        return card["produced_mana"]
    produced = {BASIC_LAND_TYPE_MANA[t] for t in BASIC_LAND_TYPE_MANA
                if t in card.get("type_line", "")}
    for clause in ADD_CLAUSE.findall(card.get("oracle_text", "")):
        produced.update(MANA_SYMBOL.findall(clause))
        if ANY_COLOR_CLAUSE.search(clause):
            produced.update("WUBRG")
    return sorted(produced)

RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}

# ---------- the Checks (fixed predicates; every parameter comes from the Suite —
# bar deck_name, read off the Deck Block's own title) ----------

def run_checks(suite, deck_cards, oracle, collection, commitments=None,
               deck_name=None):
    p, q, cons, roles = suite["profile"], suite["quotas"], suite["constraints"], suite["roles"]
    # The Suite's check list decides what runs (ADR 0005: check ids resolve to
    # fixed predicates) — a Suite carries only the parameters its own checks
    # read, so nothing below touches a parameter its check never listed.
    wanted = {c["id"] for c in suite["checks"]}
    expand = []
    unknown = []
    for qty, nm in deck_cards:
        card = oracle.get(nm)
        if card is None:
            unknown.append(nm)
        expand += [(nm, card)] * qty
    nonland = [(n, c) for n, c in expand if c and not is_land(c)]
    lands = [(n, c) for n, c in expand if c and is_land(c)]

    def role_count(tag):
        return sum(1 for n, c in expand if tag in roles.get(n, []))

    results = {}

    def check(cid, ok, detail):
        results[cid] = (bool(ok), detail)

    total = len(expand)
    if "legality.size" in wanted:
        check("legality.size", total == p["deck_size"], f"{total} cards, need exactly {p['deck_size']}")

    if "legality.singleton" in wanted:
        # The copy limit is Suite data (issue #58): 1 in Commander, 4 in the
        # 60-card Formats — same predicate, honest detail either way.
        limit = p["copy_limit_nonland"]
        dupes = sorted({n for n, c in nonland if sum(1 for m, _ in nonland if m == n) > limit})
        check("legality.singleton", not dupes, f"no nonland above {limit} {'copy' if limit == 1 else 'copies'}" if not dupes else f"over copy limit: {', '.join(dupes)}")

    if "legality.mono_color" in wanted:
        colors = sorted({col for n, c in expand if c for col in c.get("colors", [])})
        multi = sorted({n for n, c in expand if c and len(c.get("colors", [])) > 1})
        ok = len(colors) <= p["colors_max"] and len(multi) <= p["multicolor_cards"]
        check("legality.mono_color", ok, f"colors {colors or ['none']}, multicolor {multi or 'none'}")

    if "legality.rare_count" in wanted:
        rares = sorted({n for n, c in expand if c and c.get("rarity") == "rare"})
        over = sorted({n for n, c in expand if c and RARITY_ORDER.get(c.get("rarity"), 0) > RARITY_ORDER[p["rarity_ceiling"]]})
        ok = len(rares) == p["rares_exact"] and not over
        check("legality.rare_count", ok, f"{len(rares)} rare(s): {', '.join(rares) or 'none'}" + (f"; above ceiling: {', '.join(over)}" if over else ""))

    if "legality.color_identity" in wanted:
        allowed = set(p["color_identity"])
        outside = sorted({
            f"{n} ({', '.join(sorted(set(c.get('color_identity', [])) - allowed))})"
            for n, c in expand if c and set(c.get("color_identity", [])) - allowed
        })
        check("legality.color_identity", not outside,
              f"every card inside {sorted(allowed)}" if not outside
              else f"outside {sorted(allowed)}: {'; '.join(outside)}")

    if "legality.banlist" in wanted:
        key = p["banlist_key"]
        illegal = sorted({
            f"{n} ({c.get('legalities', {}).get(key, 'no legality data')})"
            for n, c in expand if c and c.get("legalities", {}).get(key) != "legal"
        })
        check("legality.banlist", not illegal,
              f"every card legal in {key}" if not illegal
              else f"not legal in {key}: {'; '.join(illegal)}")

    if "legality.game_changers" in wanted:
        changers = [n for n, c in expand if c and c.get("game_changer")]
        count = len(changers)
        check("legality.game_changers", count <= p["game_changers_max"],
              f"{count} Game Changers, limit {p['game_changers_max']}"
              + (f": {', '.join(sorted(set(changers)))}" if count > p["game_changers_max"] else ""))

    if "legality.land_count" in wanted:
        check("legality.land_count", p["lands_min"] <= len(lands) <= p["lands_max"], f"{len(lands)} lands, need {p['lands_min']}-{p['lands_max']}")

    if "legality.nonbasic_lands" in wanted:
        bad_nb = sorted({n for n, c in lands if not is_basic(c) and n not in p["nonbasic_allowed"]})
        check("legality.nonbasic_lands", not bad_nb, "nonbasics all on the allowed list" if not bad_nb else f"not allowed: {', '.join(bad_nb)}")

    if "legality.evergreen" in wanted:
        ever = set(p["evergreen_keywords"])
        offenders = sorted({f"{n} ({', '.join(set(c.get('keywords', [])) - ever)})" for n, c in expand if c and set(c.get("keywords", [])) - ever})
        check("legality.evergreen", not offenders, "all keywords evergreen" if not offenders else f"non-evergreen: {'; '.join(offenders)}")

    if "availability.in_collection" in wanted:
        need = {}
        for qty, nm in deck_cards:
            need[nm] = need.get(nm, 0) + qty
        # Contention-aware when the Suite says so (issue #54): a donors entry
        # under constraints — data, never code — turns on committed-by-default:
        # deck-row copies count only when their Deck is a donor ('all' frees
        # every Deck). A Suite without the key keeps the plain owned count.
        # One Deck is always free without a donors entry: the Deck under
        # check itself — rows committed to the ManaBox deck carrying the Deck
        # Block's own title are the rebuilt Deck's own copies, so the
        # byte-identical Suite re-runs at Upgrade against the fresh Export
        # and the Deck never contends with itself (issue #56). The self-free
        # filter below (deck != deck_name) is a deliberate mirror of the
        # build skill's availability.py arithmetic — the Brief's name: line /
        # Deck Block title appended to the freed Decks — kept in lockstep by
        # hand, never imported. Edit the two together.
        donors = cons.get("donors")
        donor_names = None if donors is None else {str(d).strip() for d in donors}
        if donor_names is None or any(d.lower() == "all" for d in donor_names):
            free = dict(collection)
            held_by = {}
        else:
            held_by = {nm: {deck: q for deck, q in decks.items()
                            if deck not in donor_names and deck != deck_name}
                       for nm, decks in (commitments or {}).items()}
            free = {nm: collection.get(nm, 0) - sum(held_by.get(nm, {}).values())
                    for nm in collection}
        def shortfall(nm, n):
            owned = collection.get(nm, 0)
            held = held_by.get(nm)
            if not held or owned == 0:
                return f"{nm} (need {n}, own {owned})"
            return (f"{nm} (need {n}, own {owned}, free {max(free.get(nm, 0), 0)} "
                    f"— committed to {', '.join(sorted(held))})")
        short = sorted(shortfall(nm, n) for nm, n in need.items() if free.get(nm, 0) < n)
        check("availability.in_collection", not short, "every card owned" if not short else f"missing: {'; '.join(short)}")

    if "manabase.color_coverage" in wanted:
        spell_colors = {col for n, c in nonland for col in c.get("colors", [])}
        producible = {m for n, c in lands for m in produced_mana(c)}
        gap = sorted(spell_colors - producible)
        check("manabase.color_coverage", not gap and (not spell_colors or lands), f"spells need {sorted(spell_colors) or 'nothing'}, lands make {sorted(producible) or 'nothing'}")

    if "curve.average" in wanted:
        if nonland:
            avg = sum(mana_value(c) for n, c in nonland) / len(nonland)
            check("curve.average", avg <= p["curve_avg_max"], f"average {avg:.2f}, max {p['curve_avg_max']}")
        else:
            check("curve.average", False, "no nonland cards yet")

    if "curve.early_plays" in wanted:
        early = sum(1 for n, c in nonland if mana_value(c) <= 2)
        check("curve.early_plays", early >= p["early_nonland_cmc2_min"], f"{early} nonland cards at mana value <=2, need {p['early_nonland_cmc2_min']}")

    for tag, target in q.items():
        if f"quota.{tag}" in wanted:
            n = role_count(tag)
            check(f"quota.{tag}", n >= target, f"{n} tagged {tag}, need {target}")

    if "brief.includes" in wanted:
        have = {nm for qty, nm in deck_cards if qty > 0}
        absent = [nm for nm in cons["must_include"] if nm not in have]
        check("brief.includes", not absent,
              "all required cards present" if not absent
              else f"missing: {'; '.join(absent)}")

    if "brief.cmc_max" in wanted:
        heavy = sorted({n for n, c in expand if c and mana_value(c) > cons["cmc_max"]})
        check("brief.cmc_max", not heavy, "nothing above the cap" if not heavy else f"above {cons['cmc_max']}: {', '.join(heavy)}")

    if "consistency.opening_lands" in wanted:
        N, K, n = total, len(lands), 7
        if N >= n:
            pge2 = 1 - sum(math.comb(K, k) * math.comb(N - K, n - k) for k in (0, 1) if N - K >= n - k) / math.comb(N, n)
            check("consistency.opening_lands", pge2 >= p["p_2plus_lands_in_7_min"], f"P(>=2 lands in 7) = {pge2:.2f}, need {p['p_2plus_lands_in_7_min']}")
        else:
            check("consistency.opening_lands", False, f"deck has {N} cards, cannot draw 7")

    unresolved = sorted(wanted - set(results))
    if unresolved:
        print(f"check id(s) resolving to no fixed predicate: {', '.join(unresolved)} — "
              "the Suite is data for this runner; an unknown id means a wrong Suite "
              "or an old runner, never a verdict", file=sys.stderr)
        sys.exit(2)

    return results, unknown

# ---------- report Block ----------

def report(suite, deck_name, results, unknown, oracle_size, run_date):
    red = [cid for cid in results if not results[cid][0]]
    lines = [
        f"suite: {suite['suite']}",
        f"deck: {deck_name}",
        f"format: {suite['format']}",
        f"date: {run_date.isoformat()}",
        f"oracle: data-backed ({oracle_size} cards)" + (f" — unknown to Oracle: {', '.join(unknown)}" if unknown else ""),
        f"verdict: {'green' if not red else 'red'} — {len(red)} red / {len(results) - len(red)} green",
        "",
    ]
    for c in suite["checks"]:
        cid = c["id"]
        ok, detail = results[cid]
        lines.append(f"{'green' if ok else 'red  '} {cid} — {detail}")
    return "\n".join(lines)

# ---------- checklist render: the same Suite data, walked where no sandbox exists ----------

def render_checklist(suite):
    params = dict(suite["profile"])
    params.update({f"quotas.{k}": v for k, v in suite["quotas"].items()})
    params.update(suite["constraints"])

    def sub(text):
        return re.sub(r"\{([\w.]+)\}", lambda m: ", ".join(map(str, params[m.group(1)])) if isinstance(params.get(m.group(1)), list) else str(params.get(m.group(1), m.group(0))), text)

    out = [
        f"# Suite checklist: {suite['suite']} ({suite['format']})",
        "",
        "Walked by the model when no code sandbox exists. Count against the Oracle where",
        "present; with no Oracle, use card knowledge and flag every verdict best-effort.",
        "Mark each line red or green with the counted evidence — never a bare tick.",
        "",
    ]
    out += [f"- [ ] `{c['id']}` — {sub(c['text'])}" for c in suite["checks"]]
    out += ["", "## Role tags (judgment recorded at Build; count, never re-judge)", ""]
    out += [f"- {name}: {', '.join(tags)}" for name, tags in suite["roles"].items()]
    return "\n".join(out)

# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description="Run a declarative tutor Suite over a Deck, offline.")
    ap.add_argument("--suite", required=True, help="Suite file (YAML-subset Block)")
    ap.add_argument("--deck", help="Deck Block file (ManaBox-importable text)")
    ap.add_argument("--oracle", help="Oracle card-facts file (oracle.jsonl JSON Lines, or a JSON array)")
    ap.add_argument("--collection", help="Collection Export file (ManaBox CSV)")
    ap.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="date for the report's date line (default: today)")
    ap.add_argument("--render-checklist", action="store_true",
                    help="print the Suite as a walkable checklist instead of running it")
    args = ap.parse_args()

    with open(args.suite) as f:
        suite = parse_yaml(f.read())
    if args.render_checklist:
        print(render_checklist(suite))
        return

    for name in ("deck", "oracle", "collection"):
        if getattr(args, name) is None:
            ap.error(f"--{name} is required to run the Suite")
    run_date = date.fromisoformat(args.date) if args.date else date.today()

    oracle = load_oracle(args.oracle)
    collection = load_collection(args.collection)
    commitments = (load_commitments(args.collection)
                   if suite.get("constraints", {}).get("donors") is not None else None)
    with open(args.deck) as f:
        deck_name, deck_cards = parse_deck(f.read())
    results, unknown = run_checks(suite, deck_cards, oracle, collection, commitments,
                                  deck_name=deck_name)
    print(report(suite, deck_name or "Untitled", results, unknown, len(oracle), run_date))
    sys.exit(0 if all(ok for ok, _ in results.values()) else 1)

if __name__ == "__main__":
    main()
