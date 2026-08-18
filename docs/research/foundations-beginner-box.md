# Research: Foundations Beginner Box deck construction rules

- **Ticket:** [#17](https://github.com/mattiasthalen/tutor/issues/17)
- **Date:** 2026-08-18
- **Purpose:** Pin the construction profile of the *Magic: The Gathering Foundations* Beginner Box (released 2024-11-15) so the house Format "Kitchen 20" (issue #7) can mirror it: deck size and copy limit as legality rules; land mix and simplicity conventions as review guidance.

## Rules at a glance

| Property | Value |
| --- | --- |
| Decks in the box | 10 mono-color 20-card half-decks ("themed Jumpstart packets"), 200 cards total |
| Deck size as played | 40 cards — shuffle any two packets together (45 possible pairings) |
| Copies per card | 1 of each nonland card (strict singleton); only basic lands repeat |
| Color spread | Two packets per color (W/U/B/R/G); every card mono-color or colorless — zero multicolor cards in the box |
| Lands per packet | 8 of 20 in eight packets (7 basics + 1 Uncharted Haven); 9 of 20 in Inferno and Primal (8 basics + 1 Uncharted Haven) |
| Lands as played | 16–18 of 40 (40–45%) |
| Card pool | Foundations (FDN) only; Standard-legal until at least 2029 |
| Rarity ceiling | Exactly 1 rare per packet (its headline card); rest commons/uncommons; no mythics |
| Mechanics ceiling | Evergreen keywords plus a whisper of Raid; no planeswalkers; one legendary card in the whole box; mana values 1–7 |
| Starting life | 20 (standard two-player rule; box ships two d20 spindown counters) — see confidence note |

## Findings

### 1. Box contents and deck count

The official contents article lists: **10 themed Jumpstart decks** of **20 cards from Foundations (FDN)** each, 2 reference cards, 1 reference guide booklet, 2 "How to Play" guides, 2 gameboard playmats, and 2 spindown life counters. Mark Rosewater confirms "ten 20-card packs" and "a total of 200 cards." ([WotC contents article][contents], [Making Magic part 2][mm2])

Two of the ten packets — **Cats** (white) and **Vampires** (black) — double as the tutorial decks: their cards come pre-ordered so the guided first game plays out the same way every time ("specifically ordered for the tutorial ... you'll draw the cards at the top of the table first"). The other eight are ordinary shuffled packets. ([contents][contents])

### 2. Deck size and how a game deck is built

The packets are half-decks: "Shuffle two together and play!" — a played deck is **40 cards** made of any two 20-card packets, giving 45 distinct pairings ("pick two halves of your deck, then shuffle them together ... 45 different decks"). This is the Jumpstart model, not 60-card constructed — the Comprehensive Rules' constructed floor (60 cards, 4-copy limit, CR 100.2a) deliberately does not apply. ([contents][contents], [mm2][mm2], [CR][cr])

### 3. Copies per card

Every packet decklist in the official article runs **1 copy of each nonland card** — 11–12 singleton spells plus 1 Uncharted Haven — with only basic lands repeated (7–8 per packet). Scryfall's print tagging independently confirms: the 129 FDN prints flagged `beginnerbox` are exactly 118 unique spells + Uncharted Haven + 10 basic-land prints (2 arts × 5 types), i.e. **no nonland card appears twice anywhere in the box**, and no card is shared between packets except Uncharted Haven and basics. ([contents][contents], [Scryfall search `is:beginnerbox`][scry])

### 4. Color spread

Two packets per color, each strictly mono-color:

| Color | Packets |
| --- | --- |
| White | Cats, Healing |
| Blue | Wizards, Pirates |
| Black | Vampires, Undead |
| Red | Goblins, Inferno |
| Green | Elves, Primal |

The Scryfall data shows **zero multicolor cards** in the box (the only cards without a single color are 3 colorless artifacts and the lands; the fourth artifact, Carnelian Orb of Dragonkind, is itself mono-red), so a combined deck is always exactly one or two colors. Each packet's single nonbasic land, **Uncharted Haven** (common; enters tapped, choose a color, taps for that color), is the box's only mana fixing and makes any two-packet pairing work. ([mm2][mm2], [Scryfall][scry])

### 5. Land counts

Per the official decklists:

- **8 packets run 8 lands / 20** (40%): 7 basics + 1 Uncharted Haven — Cats, Healing, Wizards, Pirates, Vampires, Undead, Goblins, Elves.
- **2 packets run 9 lands / 20** (45%): 8 basics + 1 Uncharted Haven — **Inferno** (8 Mountain) and **Primal** (8 Forest), the two big-creature packets with the highest mana values.

Combined 40-card decks therefore play **16, 17, or 18 lands** (40–45%), including 2 Uncharted Haven. ([contents][contents]; spell-count cross-check via [Scryfall][scry]: 8 packets × 12 spells + 2 packets × 11 spells = 118 unique spells, matching the tagged prints exactly)

### 6. Simplicity conventions

What keeps the decks beginner-simple, per the primary sources:

- **Card pool:** all 200 cards are from Foundations (FDN, released 2024-11-15), the evergreen core set that stays "in Standard until at least 2029." Every box has identical contents: "Every Foundations Beginner Box includes the same deck themes." ([announcement][announce], [mm2][mm2], [Scryfall set data][scryset])
- **Rarity:** exactly **one rare per packet**, always its build-around headline card (Jazal Goldmane, Ancestor Dragon, Mystic Archaeologist, Corsair Captain, Crossway Troublemakers, Death Baron, Dropkick Bomber, Terror of Mount Velus, Elvish Archdruid, Aggressive Mammoth); everything else is common (67 spells) or uncommon (41 spells). **No mythics.** ([Scryfall][scry] rarity per print, decklists from [contents][contents])
- **Mechanics ceiling:** keywords across all 130 cards are almost entirely evergreen — flying (16 cards), flash (6), enchant (5), trample (3), reach (3), lifelink (2), vigilance (2), equip (2), double strike (2), plus single cards with haste, ward, first strike, deathtouch, scry, kicker, mill. The only set mechanic is **Raid** on 2 cards. **No planeswalkers**, and exactly **one legendary card** in the whole box (Jazal Goldmane). Mana values span 1–7. ([Scryfall][scry])
- **Themes:** ten tribal/strategy themes "carefully chosen" to be "beginner friendly," two per color, each showcasing one clear plan (go-wide cats, lifegain, card draw, tempo pirates, drain vampires, graveyard zombies, goblin swarm, dragons/burn, elf ramp, big stompy). ([mm2][mm2])
- **Guided ramp-up:** tutorial game with the pre-ordered Cats and Vampires decks first, then re-shuffle and replay, then start mixing any two packets. ([contents][contents])

### 7. Starting life total

No Beginner Box web source states a bespoke life total. The box teaches the standard two-player game, and the standard rule is **20 life**: "103.3. Each player begins the game with a starting life total of 20." (Comprehensive Rules; quoted from the 2022-09-08 text — later CR revisions renumber the subrule but keep the rule.) The box ships **two d20 spindown life counters**, consistent with 20. ([CR][cr], [contents][contents])

## Appendix: the ten packet decklists

From the official contents article; quantities are 1 unless noted. Rares in **bold** (rarity per Scryfall).

**Cats (W) — 7 Plains, Uncharted Haven:** Savannah Lions, Leonin Skyhunter, Prideful Parent, Felidar Savior, **Jazal Goldmane**, Pacifism, Ingenious Leonin, Helpful Hunter, Leonin Vanguard, Moment of Triumph, Elspeth's Smite, Angelic Edict.

**Healing (W) — 7 Plains, Uncharted Haven:** **Ancestor Dragon**, Dazzling Angel, Quick-Draw Katana, Ajani's Pridemate, Adamant Will, Bishop's Soldier, Deadly Riposte, Herald of Faith, Inspiring Overseer, Prayer of Binding, Twinblade Paladin, Hinterland Sanctifier.

**Wizards (U) — 7 Islands, Uncharted Haven:** **Mystic Archaeologist**, Arcane Epiphany, Clinquant Skymage, Erudite Wizard, Icewind Elemental, Mischievous Mystic, Fleeting Distraction, Burrog Befuddler, Exclusion Mage, Into the Roil, Quick Study, Starlight Snare.

**Pirates (U) — 7 Islands, Uncharted Haven:** **Corsair Captain**, Bigfin Bouncer, Skyship Buccaneer, Brineborn Cutthroat, Spectral Sailor, Tolarian Terror, Cancel, Eaten by Piranhas, Kitesail Corsair, Opt, Storm Fleet Spy, Pirate's Cutlass.

**Vampires (B) — 7 Swamps, Uncharted Haven:** Vampire Interloper, Vampire Spawn, Moment of Craving, Highborn Vampire, Untamed Hunger, Bloodtithe Collector, **Crossway Troublemakers**, Vengeful Bloodwitch, Hero's Downfall, Vampire Neonate, Offer Immortality, Stromkirk Bloodthief.

**Undead (B) — 7 Swamps, Uncharted Haven:** **Death Baron**, Hungry Ghoul, Diregraf Ghoul, Eaten Alive, Reassembling Skeleton, Cemetery Recruitment, Crow of Dark Tidings, Deadly Plot, Maalfeld Twins, Skeleton Archer, Suspicious Shambler, Undying Malice.

**Goblins (R) — 7 Mountains, Uncharted Haven:** **Dropkick Bomber**, Incinerating Blast, Frenzied Goblin, Battle-Rattle Shaman, Dragon Fodder, Goblin Oriflamme, Goblin Smuggler, Kindled Fury, Raging Redcap, Swab Goblin, Volley Veteran, Goblin Firebomb.

**Inferno (R) — 8 Mountains, Uncharted Haven:** **Terror of Mount Velus**, Fiery Annihilation, Firespitter Whelp, Carnelian Orb of Dragonkind, Dragonlord's Servant, Fire Elemental, Kargan Dragonrider, Rapacious Dragon, Scorching Dragonfire, Seize the Spoils, Skyraker Giant.

**Elves (G) — 7 Forests, Uncharted Haven:** **Elvish Archdruid**, Beast-Kin Ranger, Elvish Regrower, Felling Blow, Broken Wings, Dwynen's Elite, Llanowar Elves, Snakeskin Veil, Joraga Invocation, Tajuru Pathwarden, Thornweald Archer, Wildheart Invoker.

**Primal (G) — 8 Forests, Uncharted Haven:** **Aggressive Mammoth**, Bite Down, Giant Growth, Mild-Mannered Librarian, Wildwood Scourge, Bear Cub, Biogenic Upgrade, Druid of the Cowl, Magnigoth Sentry, New Horizons, Thrashing Brontodon.

Scryfall tags the physical prints as FDN collector numbers 488–564 and 730 (Beginner Box printings) plus 30 main-set-numbered prints and basics 272–281, all with promo type `beginnerbox`.

## Confidence notes

- **High confidence** (two independent primary sources agree — WotC decklists and Scryfall print tags): deck count, deck size, singleton copy limit, color spread, land counts, rarity spread, mechanics ceiling, FDN-only pool.
- **Correction applied:** the WotC article's Goblins list as machine-extracted read "Volley" and "Veteran Goblin Firebomb"; Scryfall shows the actual prints are **Volley Veteran** (FDN 550) and **Goblin Firebomb** (FDN 562). High confidence in the corrected reading.
- **Medium confidence (explicit inference):** the 20-life start. It follows from CR 103.3 plus the included d20 spindowns, but no Beginner Box-specific web source states it outright, and the printed "How to Play" booklets inside the box were not directly inspected. Flag for re-check if a scan of the booklet turns up.

## Sources

- [Magic: The Gathering Foundations Beginner Box Contents][contents] — Wizards of the Coast (contents list, all ten decklists, tutorial ordering)
- [Starting with a Good Foundations, Part 2][mm2] — Mark Rosewater, Making Magic (design intent: ten packs, 200 cards, two themes per color, 45 pairings, identical boxes)
- [A First Look at Magic: The Gathering Foundations][announce] — Wizards of the Coast (product line, "in Standard until at least 2029")
- [Foundations product page][product] — Wizards of the Coast (marketing copy, November 15 release)
- [Scryfall search `is:beginnerbox`][scry] — Scryfall API (130 prints: names, rarities, collector numbers, keywords, colors, types)
- [Scryfall set FDN][scryset] — Scryfall API (release date 2024-11-15, set type core)
- [Magic Comprehensive Rules][cr] — Wizards of the Coast (CR 103.3 starting life 20; CR 100.2a constructed baseline for contrast)

[contents]: https://magic.wizards.com/en/news/feature/foundations-beginner-box-contents
[mm2]: https://magic.wizards.com/en/news/making-magic/starting-with-a-good-foundations-part-2
[announce]: https://magic.wizards.com/en/news/announcements/announcing-magic-the-gathering-foundations
[product]: https://magic.wizards.com/en/products/foundations
[scry]: https://scryfall.com/search?q=is%3Abeginnerbox
[scryset]: https://scryfall.com/sets/fdn
[cr]: https://magic.wizards.com/en/rules
