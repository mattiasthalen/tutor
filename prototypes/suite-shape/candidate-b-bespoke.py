#!/usr/bin/env python3
"""PROTOTYPE (throwaway) — candidate B: a bespoke script generated at Build start.

Every target, Role tag, and threshold is hardcoded: the script IS the Suite.
Nothing else reads it, nothing else renders it. Regenerating at Upgrade means
regenerating code — and trusting the model to reproduce ~200 lines byte-stably
when only the Brief was supposed to change.

Usage: python3 candidate-b-bespoke.py [deck.txt]
"""

import csv, json, math, os, re, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DECK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "decks", "final.txt")

# --- everything below is frozen into the artifact at generation time ---

ROLES = {
    "Healer's Hawk": ["creature", "theme"], "Hinterland Sanctifier": ["creature", "theme"],
    "Leonin Vanguard": ["creature", "theme"], "Bishop's Soldier": ["creature", "theme"],
    "Ajani's Pridemate": ["creature", "theme", "wincon"], "Prideful Parent": ["creature"],
    "Inspiring Overseer": ["creature", "theme", "draw"], "Dazzling Angel": ["creature", "theme"],
    "Felidar Savior": ["creature", "theme"], "Exemplar of Light": ["creature", "theme", "wincon", "draw"],
    "Pacifism": ["removal"], "Banishing Light": ["removal"],
    "Giada, Font of Hope": ["creature"], "Sun-Blessed Healer": ["creature", "theme"],
    "Vanguard Seraph": ["creature", "theme"], "Moment of Triumph": ["theme"],
    "Felidar Cub": ["creature", "removal"], "Disenchant": ["removal"],
    "Crusader of Odric": ["creature", "wincon"], "Courageous Goblin": ["creature"],
}
EVERGREEN = {"Deathtouch", "Defender", "Double strike", "Enchant", "Equip", "First strike",
             "Flash", "Flying", "Haste", "Hexproof", "Indestructible", "Lifelink", "Menace",
             "Protection", "Prowess", "Reach", "Trample", "Vigilance", "Ward"}

oracle = {c["name"]: c for c in json.load(open(os.path.join(HERE, "oracle.json")))}
collection = {}
for row in csv.DictReader(open(os.path.join(HERE, "collection.csv"), newline="")):
    collection[row["Name"]] = collection.get(row["Name"], 0) + int(row["Quantity"])

PIN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]{2,5})\)\s+(\S+)$")
LUMP = re.compile(r"^(\d+)\s+([^(]+)$")
deck_name, cards = "Untitled", []
for raw in open(DECK):
    line = raw.split(" // ")[0].strip()
    if not line:
        continue
    if line.startswith("//"):
        head = line[2:].strip()
        if head not in ("Commander", "Mainboard", "Sideboard", "Maybeboard") and deck_name == "Untitled":
            deck_name = head
        continue
    m = PIN.match(line) or LUMP.match(line)
    if m:
        cards.append((int(m.group(1)), m.group(2).strip()))

expand = [(n, oracle.get(n)) for q, n in cards for _ in range(q)]
nonland = [(n, c) for n, c in expand if c and "Land" not in c["type_line"]]
lands = [(n, c) for n, c in expand if c and "Land" in c["type_line"]]
total = len(expand)
results = []

def check(cid, ok, detail):
    results.append((cid, bool(ok), detail))

check("legality.size", total == 20, f"{total} cards, need exactly 20")
dupes = sorted({n for n, _ in nonland if sum(1 for m, _ in nonland if m == n) > 1})
check("legality.singleton", not dupes, "no nonland above 1 copy" if not dupes else f"over copy limit: {', '.join(dupes)}")
colors = sorted({col for _, c in expand if c for col in c.get("colors", [])})
check("legality.mono_color", len(colors) <= 1, f"colors {colors or ['none']}")
rares = sorted({n for n, c in expand if c and c["rarity"] == "rare"})
check("legality.rare_count", len(rares) == 1, f"{len(rares)} rare(s): {', '.join(rares) or 'none'}")
check("legality.land_count", 8 <= len(lands) <= 9, f"{len(lands)} lands, need 8-9")
bad_nb = sorted({n for n, c in lands if not c["type_line"].startswith("Basic Land") and n != "Uncharted Haven"})
check("legality.nonbasic_lands", not bad_nb, "allowed" if not bad_nb else f"not allowed: {', '.join(bad_nb)}")
off = sorted({n for n, c in expand if c and set(c.get("keywords", [])) - EVERGREEN})
check("legality.evergreen", not off, "all evergreen" if not off else f"non-evergreen: {', '.join(off)}")
need = {}
for q, n in cards:
    need[n] = need.get(n, 0) + q
short = sorted(n for n, k in need.items() if collection.get(n, 0) < k)
check("availability.in_collection", not short, "every card owned" if not short else f"missing: {', '.join(short)}")
producible = {m for _, c in lands for m in c.get("produced_mana", [])}
spell = {col for _, c in nonland for col in c.get("colors", [])}
check("manabase.color_coverage", not (spell - producible), f"spells need {sorted(spell) or 'nothing'}")
avg = sum(c["cmc"] for _, c in nonland) / len(nonland) if nonland else None
check("curve.average", avg is not None and avg <= 3.0, f"average {avg:.2f}, max 3.0" if avg is not None else "no nonland cards yet")
early = sum(1 for _, c in nonland if c["cmc"] <= 2)
check("curve.early_plays", early >= 4, f"{early} at mana value <=2, need 4")
for tag, target in [("creature", 8), ("theme", 6), ("removal", 2), ("draw", 1), ("wincon", 1)]:
    k = sum(1 for n, _ in expand if tag in ROLES.get(n, []))
    check(f"quota.{tag}", k >= target, f"{k} tagged {tag}, need {target}")
heavy = sorted({n for n, c in expand if c and c["cmc"] > 4})
check("brief.cmc_max", not heavy, "nothing above the cap" if not heavy else f"above 4: {', '.join(heavy)}")
if total >= 7:
    K = len(lands)
    p = 1 - sum(math.comb(K, k) * math.comb(total - K, 7 - k) for k in (0, 1) if total - K >= 7 - k) / math.comb(total, 7)
    check("consistency.opening_lands", p >= 0.85, f"P(>=2 lands in 7) = {p:.2f}, need 0.85")
else:
    check("consistency.opening_lands", False, f"deck has {total} cards, cannot draw 7")

red = sum(1 for _, ok, _ in results if not ok)
print(f"suite: Sunlit Flock\ndeck: {deck_name}\nformat: Kitchen 20\ndate: {date.today().isoformat()}")
print(f"oracle: data-backed ({len(oracle)} cards)")
print(f"verdict: {'green' if red == 0 else 'red'} — {red} red / {len(results) - red} green\n")
for cid, ok, detail in results:
    print(f"{'green' if ok else 'red  '} {cid} — {detail}")
sys.exit(0 if red == 0 else 1)
