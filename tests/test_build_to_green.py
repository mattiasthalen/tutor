"""Tests for Build to green — the Deck Block ships (issue #54).

The seams under test are the ticket's acceptance criteria, never internals:

- the availability CLI (``skills/build/scripts/availability.py``) — the
  Collection's free pool under the Brief's ``donor:`` lines: deck-row copies
  committed by default, donors freeing them, ``donor: all`` freeing
  everything, and declined contention reported in the honest sentence shape
  ("wanted Rhystic Study; all copies committed to Tatyova"),
- the runner CLI interpreting Suites that carry ``constraints.donors`` —
  contention-aware availability as Suite data (ADR 0005), legacy Suites
  byte-identical,
- the generator CLI snapshotting ``donor:`` lines into the Suite,
- the ship CLI (``skills/build/scripts/ship_deck.py``) — the
  ManaBox-importable Deck Block: nonbasics pinned to the exact owned printing
  (the fancier print among the copies the ``donor:`` lines leave free —
  committed copies are never pinned), basics lumped per name last in each
  Board after a blank line, inline ``// category`` comments, the Maybeboard
  wishlist unpinned and possibly unowned, the Fan Content footer, and a
  byte-identical round-trip, and
- the ``build-deep`` eval case in the offline harness.

Everything runs through the CLIs — exit codes and stdout/files — offline,
against committed fixtures or temp files written per test.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

from test_eval_harness import SmokeGradingMixin

REPO = pathlib.Path(__file__).resolve().parents[1]
AVAILABILITY = REPO / "skills" / "build" / "scripts" / "availability.py"
FIXTURES = REPO / "evals" / "fixtures"
REAL_EXPORT = FIXTURES / "collections" / "real-collection.csv"
TATYOVA_BRIEF = FIXTURES / "briefs" / "commander-tatyova-landfall.txt"


def run_cli(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=120,
    )


class DeclinedContentionIsReported(unittest.TestCase):
    """AC: copies in existing Decks are committed by default and declined
    contention is reported — a wanted card whose every copy sits in a Deck
    the Brief never named as donor comes back as the honest sentence, and
    the run exits red (1)."""

    def test_fully_committed_want_yields_the_sentence(self):
        # Exsanguinate: every owned copy is committed to the Zoraline deck in
        # the realism Export; the fixture Brief frees only Baylen.
        result = run_cli(AVAILABILITY, "--collection", REAL_EXPORT,
                         "--brief", TATYOVA_BRIEF, "--want", "Exsanguinate")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Exsanguinate; all copies committed to Zoraline, Cosmos Caller",
            result.stdout,
        )


class DonorLinesFreeCommittedCopies(unittest.TestCase):
    """AC: the Brief's donor: lines free a Deck's committed copies;
    donor: all frees everything; with no donor lines every deck-row copy
    stays committed."""

    def test_donor_deck_copies_are_free(self):
        # Seize the Spoils: one binder copy, one committed to Baylen — the
        # fixture Brief's donor line frees the Baylen copy, so both are free.
        result = run_cli(AVAILABILITY, "--collection", REAL_EXPORT,
                         "--brief", TATYOVA_BRIEF,
                         "--want", "Seize the Spoils", "--want", "Seize the Spoils")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Seize the Spoils: 2 free of 2 owned", result.stdout)

    def test_donor_all_frees_everything(self):
        result = run_cli(AVAILABILITY, "--collection", REAL_EXPORT,
                         "--donor", "all", "--want", "Exsanguinate")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Exsanguinate: 1 free of 1 owned", result.stdout)

    def test_no_donor_lines_keeps_every_deck_row_committed(self):
        # Quick Study: 2 owned, 1 committed to the Tatyova deck. Without any
        # donor line, only the binder copy is free — wanting both declines.
        result = run_cli(AVAILABILITY, "--collection", REAL_EXPORT,
                         "--want", "Quick Study", "--want", "Quick Study")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Quick Study (need 2); 1 free, 1 committed to "
            "Tatyova, Benthic Druid",
            result.stdout,
        )

    def test_unowned_want_is_not_contention(self):
        result = run_cli(AVAILABILITY, "--collection", REAL_EXPORT,
                         "--want", "Rhystic Study")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("wanted Rhystic Study; not in the Collection", result.stdout)

    def test_copies_split_across_decks_name_every_holder(self):
        # Broken Wings: one copy in Baylen, one in Tatyova, none in a binder.
        result = run_cli(AVAILABILITY, "--collection", REAL_EXPORT,
                         "--want", "Broken Wings")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Broken Wings; all copies committed to "
            "Baylen, the Haymaker, Tatyova, Benthic Druid",
            result.stdout,
        )


class WholeDeckAvailability(unittest.TestCase):
    """AC: the Deck draws only from the Collection — a whole Deck Block is
    checked at each card's count, pins and inline comments tolerated, and the
    Maybeboard (the wishlist Board, possibly unowned) never counted."""

    DECK = (
        "// Probe\n"
        "\n"
        "// Mainboard\n"
        "1 Quick Study (SOS) 65 // draw\n"
        "1 Exsanguinate\n"
        "\n"
        "2 Forest\n"
        "\n"
        "// Maybeboard\n"
        "1 Rhystic Study // unowned wishlist entry\n"
    )

    def run_deck(self, deck_text, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            deck = pathlib.Path(tmp) / "deck.txt"
            deck.write_text(deck_text, encoding="utf-8")
            return run_cli(AVAILABILITY, "--collection", REAL_EXPORT,
                           "--deck", deck, *extra)

    def test_deck_mode_declines_contention_and_skips_the_maybeboard(self):
        result = self.run_deck(self.DECK)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Exsanguinate; all copies committed to Zoraline, Cosmos Caller",
            result.stdout,
        )
        # The Maybeboard's unowned card is never a shortage.
        self.assertNotIn("Rhystic Study", result.stdout)

    def test_deck_mode_is_green_when_every_copy_is_free(self):
        result = self.run_deck(self.DECK, "--donor", "all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Quick Study: 2 free of 2 owned", result.stdout)
        self.assertIn("Forest:", result.stdout)


class BareLinesResolveThroughOwnedNames(unittest.TestCase):
    """A bare line holding " // " is ambiguous — a multi-faced name or an
    inline comment. The Collection settles it, the same order as the ship's:
    the whole remainder wins when the Collection owns it, otherwise the
    comment reading applies — never a glued 'name // comment' want."""

    COLLECTION = (
        "Name,Quantity\n"
        "Llanowar Elves,1\n"
        "Emeritus of Abundance // Regrowth,1\n"
    )
    DECK = (
        "// Probe\n"
        "// Mainboard\n"
        "1 Llanowar Elves // ramp\n"
        "1 Emeritus of Abundance // Regrowth\n"
    )

    def test_comment_reading_and_owned_whole_name_both_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            deck = home / "deck.txt"
            deck.write_text(self.DECK, encoding="utf-8")
            collection = home / "collection.csv"
            collection.write_text(self.COLLECTION, encoding="utf-8")
            result = run_cli(AVAILABILITY, "--collection", collection,
                             "--deck", deck)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Llanowar Elves: 1 free of 1 owned", result.stdout)
        self.assertIn("Emeritus of Abundance // Regrowth: 1 free of 1 owned",
                      result.stdout)
        self.assertNotIn("Llanowar Elves // ramp", result.stdout)


GENERATOR = REPO / "skills" / "build" / "scripts" / "generate_suite.py"
PROFILE = REPO / "skills" / "build" / "profiles" / "commander.yaml"
ORACLE = FIXTURES / "scryfall" / "oracle.jsonl"
REFERENCE_DATE = "2026-08-18"


class DonorsAreSuiteData(unittest.TestCase):
    """ADR 0005: the Suite is declarative data the fixed runner interprets —
    the Brief's donor: lines land in the Suite's constraints under brief:
    provenance, every line collected, and a Brief with no donor lines still
    pins committed-by-default as `donors: []`."""

    def generate(self, brief_path):
        return run_cli(GENERATOR, "--brief", brief_path, "--profile", PROFILE,
                       "--oracle", ORACLE, "--date", REFERENCE_DATE)

    def test_donor_lines_land_under_provenance(self):
        result = self.generate(TATYOVA_BRIEF)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "  donors:\n"
            "    # brief: donor: Baylen, the Haymaker\n"
            "    - Baylen, the Haymaker\n",
            result.stdout,
        )

    def test_every_donor_line_is_collected(self):
        text = TATYOVA_BRIEF.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            brief = pathlib.Path(tmp) / "brief.txt"
            brief.write_text(text + "donor: Tatyova, Benthic Druid\n",
                             encoding="utf-8")
            result = self.generate(brief)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("    - Baylen, the Haymaker\n", result.stdout)
        self.assertIn(
            "    # brief: donor: Tatyova, Benthic Druid\n"
            "    - Tatyova, Benthic Druid\n",
            result.stdout,
        )

    def test_no_donor_lines_pins_committed_by_default(self):
        text = TATYOVA_BRIEF.read_text(encoding="utf-8")
        lines = [l for l in text.splitlines() if not l.startswith("donor:")]
        with tempfile.TemporaryDirectory() as tmp:
            brief = pathlib.Path(tmp) / "brief.txt"
            brief.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result = self.generate(brief)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "  # default: no donor lines — every deck-row copy stays committed\n"
            "  donors: []\n",
            result.stdout,
        )


from test_build_skill import (  # noqa: E402 — shared CLI seam helpers
    TempHome, mini_suite, oracle_card, oracle_json, run_mini,
)

CONTENTION_COLLECTION = (
    "Binder Name,Binder Type,Name,Quantity\n"
    "Shoebox,binder,Llanowar Elves,1\n"
    "Tatyova,deck,Rhystic Study,1\n"
)
CONTENTION_DECK = "// Probe\n// Mainboard\n1 Llanowar Elves\n1 Rhystic Study\n"
CONTENTION_ORACLE = oracle_json(
    oracle_card("Llanowar Elves"), oracle_card("Rhystic Study"),
)


def availability_suite(*donor_lines):
    """A minimal Suite whose only Check is availability, carrying the given
    constraints.donors entries (no argument = no donors key at all — the
    legacy Suite shape)."""
    constraint_lines = []
    if donor_lines:
        if donor_lines == ("[]",):
            constraint_lines = ["donors: []"]
        else:
            constraint_lines = ["donors:"] + [f"  - {d}" for d in donor_lines]
    return mini_suite(["availability.in_collection"],
                      constraint_lines=constraint_lines)


class RunnerAvailabilityIsContentionAware(unittest.TestCase):
    """The Suite's availability Check honors committed-by-default when the
    Suite data says so (ADR 0005: parameters live in data): deck-row copies
    count as committed unless a donors entry frees their Deck, the red
    evidence names the committing Deck, and a Suite without the donors key
    keeps the legacy owned-count reading byte-for-byte."""

    def run_suite(self, suite):
        home = TempHome()
        self.addCleanup(home.cleanup)
        return run_mini(home, suite, deck_text=CONTENTION_DECK,
                        oracle_text=CONTENTION_ORACLE,
                        collection_text=CONTENTION_COLLECTION)

    def test_committed_copy_is_red_naming_the_deck(self):
        result = self.run_suite(availability_suite("[]"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "red   availability.in_collection — missing: Rhystic Study "
            "(need 1, own 1, free 0 — committed to Tatyova)",
            result.stdout,
        )

    def test_donor_frees_the_deck_and_all_frees_everything(self):
        for donors in (("Tatyova",), ("all",)):
            with self.subTest(donors=donors):
                result = self.run_suite(availability_suite(*donors))
                self.assertEqual(result.returncode, 0,
                                 result.stdout + result.stderr)
                self.assertIn(
                    "green availability.in_collection — every card owned",
                    result.stdout,
                )

    def test_suite_without_donors_key_keeps_the_legacy_reading(self):
        result = self.run_suite(availability_suite())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green availability.in_collection — every card owned",
                      result.stdout)


class PinnedMultiFacedNamesResolve(unittest.TestCase):
    """The Deck Block carries multi-faced names flattened with // — the
    Oracle's own vocabulary — so a pinned line like
    `1 Emeritus of Abundance // Regrowth (SOS) 145` must resolve to the full
    Oracle name, never be truncated as an inline comment, while a pinned line
    with a real trailing comment still parses."""

    ORACLE = oracle_json(
        oracle_card("Emeritus of Abundance // Regrowth"),
        oracle_card("Llanowar Elves"),
    )
    COLLECTION = (
        "Name,Quantity\n"
        "Emeritus of Abundance // Regrowth,1\n"
        "Llanowar Elves,1\n"
    )
    DECK = (
        "// Probe\n// Mainboard\n"
        "1 Emeritus of Abundance // Regrowth (SOS) 145\n"
        "1 Llanowar Elves (FDN) 227 // ramp\n"
    )

    def test_full_name_reaches_the_oracle_and_the_collection(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        suite = mini_suite(["availability.in_collection"])
        result = run_mini(home, suite, deck_text=self.DECK,
                          oracle_text=self.ORACLE,
                          collection_text=self.COLLECTION)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green availability.in_collection — every card owned",
                      result.stdout)
        self.assertNotIn("unknown to Oracle", result.stdout)


SHIP = REPO / "skills" / "build" / "scripts" / "ship_deck.py"

FOOTER = ("// tutor is unofficial Fan Content permitted under the Fan Content "
          "Policy. Not approved/endorsed by Wizards. Portions of the materials "
          "used are property of Wizards of the Coast. ©Wizards of the Coast LLC.")

SHIP_EXPORT = (
    "Binder Name,Binder Type,Name,Set code,Collector number,Foil,Quantity\n"
    "Box,binder,Sol Ring,C21,263,normal,1\n"
    "Box,binder,Meren of Clan Nel Toth,C15,49,normal,1\n"
    "Box,binder,Eternal Witness,MH2,302,normal,1\n"
    "Box,binder,Forest,FDN,280,normal,12\n"
    "Box,binder,Swamp,FDN,286,normal,8\n"
)


def run_ship(deck_text, collection_text=SHIP_EXPORT, *extra, brief_text=None):
    with tempfile.TemporaryDirectory() as tmp:
        home = pathlib.Path(tmp)
        deck = home / "deck.txt"
        deck.write_text(deck_text, encoding="utf-8")
        collection = home / "collection.csv"
        collection.write_text(collection_text, encoding="utf-8")
        if brief_text is not None:
            brief = home / "brief.txt"
            brief.write_text(brief_text, encoding="utf-8")
            extra = (*extra, "--brief", brief)
        return run_cli(SHIP, "--deck", deck, "--collection", collection, *extra)


class ShippedDeckBlockShape(unittest.TestCase):
    """AC: the Deck Block is text ManaBox actually imports — first line
    `// <name>`, Board headers only for the Boards present, each nonbasic
    pinned to the exact owned printing with set code and collector number,
    basics lumped per name last in each Board after a blank line, and the
    short-form Fan Content footer line on the generated artifact."""

    DRAFT = (
        "// Golgari Reanimator\n"
        "// Commander\n"
        "1 Meren of Clan Nel Toth\n"
        "// Mainboard\n"
        "1 Sol Ring\n"
        "12 Forest\n"
        "1 Eternal Witness\n"
        "8 Swamp\n"
    )

    def test_ships_the_pinned_example_shape(self):
        result = run_ship(self.DRAFT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            "// Golgari Reanimator\n"
            "\n"
            "// Commander\n"
            "1 Meren of Clan Nel Toth (C15) 49\n"
            "\n"
            "// Mainboard\n"
            "1 Eternal Witness (MH2) 302\n"
            "1 Sol Ring (C21) 263\n"
            "\n"
            "12 Forest\n"
            "8 Swamp\n"
            "\n"
            + FOOTER + "\n",
        )


class FancierOwnedPrintWins(unittest.TestCase):
    """AC: each nonbasic pinned to the exact owned printing with the fancier
    owned print chosen when several exist — Scryfall's finishes ladder,
    etched over foil over normal — spilling to the next printing when the
    fanciest has too few copies, so physical assembly matches card for card."""

    EXPORT = (
        "Binder Name,Binder Type,Name,Set code,Collector number,Foil,Quantity\n"
        "Box,binder,Lightning Bolt,M11,146,normal,3\n"
        "Box,binder,Lightning Bolt,CLB,187,foil,2\n"
        "Box,binder,Sol Ring,C21,263,etched,1\n"
        "Box,binder,Sol Ring,LTC,284,foil,1\n"
    )

    def test_foil_beats_normal_and_etched_beats_foil(self):
        deck = "// Probe\n// Mainboard\n1 Lightning Bolt\n1 Sol Ring\n"
        result = run_ship(deck, self.EXPORT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Lightning Bolt (CLB) 187\n", result.stdout)
        self.assertIn("1 Sol Ring (C21) 263\n", result.stdout)

    def test_playset_spills_across_printings_fanciest_first(self):
        deck = "// Probe\n// Mainboard\n4 Lightning Bolt\n"
        result = run_ship(deck, self.EXPORT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "2 Lightning Bolt (CLB) 187\n2 Lightning Bolt (M11) 146\n",
            result.stdout,
        )


class PinsDrawOnlyFromFreeCopies(unittest.TestCase):
    """AC: the Deck draws only from the Collection with deck-row copies
    committed by default — the pin too. A fancier printing whose only
    physical copies sit in a committed, non-donor Deck never wins over a
    plainer free copy; a `donor:` line (or --donor) frees a Deck's copies
    for pinning; the spill across printings stays inside the free counts;
    and a want the free copies cannot cover refuses in the pinned
    declined-contention wording."""

    EXPORT = (
        "Binder Name,Binder Type,Name,Set code,Collector number,Foil,Quantity\n"
        "Commander Pile,deck,Sol Ring,C21,263,foil,1\n"
        "Box,binder,Sol Ring,CMM,464,normal,1\n"
        "Zoraline,deck,Lightning Bolt,CLB,187,foil,2\n"
        "Box,binder,Lightning Bolt,CLB,187,foil,1\n"
        "Box,binder,Lightning Bolt,M11,146,normal,3\n"
    )
    DECK = "// Probe\n// Mainboard\n1 Sol Ring\n"

    def test_committed_foil_never_outranks_the_free_normal(self):
        # The review's reproduction: the only foil Sol Ring sits in a
        # committed Deck; the free copy is a plain CMM normal.
        result = run_ship(self.DECK, self.EXPORT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Sol Ring (CMM) 464\n", result.stdout)
        self.assertNotIn("(C21)", result.stdout)

    def test_donor_frees_the_fancier_copy_for_pinning(self):
        result = run_ship(self.DECK, self.EXPORT, "--donor", "Commander Pile")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Sol Ring (C21) 263\n", result.stdout)

    def test_brief_donor_lines_free_for_pinning(self):
        brief = "format: commander\ndonor: Commander Pile\n"
        result = run_ship(self.DECK, self.EXPORT, brief_text=brief)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Sol Ring (C21) 263\n", result.stdout)

    def test_spill_stays_inside_the_free_copies(self):
        # 3 wanted: one CLB foil is free (the other two sit in Zoraline), so
        # the fancier print takes one and the free normals cover the rest.
        deck = "// Probe\n// Mainboard\n3 Lightning Bolt\n"
        result = run_ship(deck, self.EXPORT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "1 Lightning Bolt (CLB) 187\n2 Lightning Bolt (M11) 146\n",
            result.stdout,
        )

    def test_too_few_free_copies_refuses_in_the_pinned_wording(self):
        deck = "// Probe\n// Mainboard\n2 Sol Ring\n"
        result = run_ship(deck, self.EXPORT)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Sol Ring (need 2); 1 free, 1 committed to Commander Pile",
            result.stderr,
        )

    def test_all_copies_committed_refuses_in_the_pinned_wording(self):
        export = (
            "Binder Name,Binder Type,Name,Set code,Collector number,Foil,Quantity\n"
            "Commander Pile,deck,Sol Ring,C21,263,foil,1\n"
        )
        result = run_ship(self.DECK, export)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Sol Ring; all copies committed to Commander Pile",
            result.stderr,
        )


class PinShapedCommentTailIsSwallowed(unittest.TestCase):
    """Documented behaviour, judged acceptable on review: all three parsers
    match the pin on the raw line first, so a trailing comment whose own tail
    is pin-shaped re-anchors the pin on that tail and the rest of the line is
    swallowed into the name — the ship then refuses on the swallowed reading
    rather than guessing at a split."""

    def test_swallowed_name_refuses_naming_the_whole_reading(self):
        deck = ("// Probe\n// Mainboard\n"
                "1 Sol Ring (C21) 263 // swap for (SOS) 145\n")
        result = run_ship(deck)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Sol Ring (C21) 263 // swap for", result.stderr)
        self.assertIn("not in the Collection", result.stderr)


class MaybeboardIsTheWishlist(unittest.TestCase):
    """AC: the Maybeboard is the wishlist Board — entries may be unowned and
    carry no printing pin, the one place the collection-only rule bends —
    while an unowned nonbasic anywhere else refuses the ship naming the
    card."""

    def test_maybeboard_entries_stay_unpinned_and_may_be_unowned(self):
        deck = ("// Probe\n// Mainboard\n1 Sol Ring\n// Maybeboard\n"
                "1 Mikaeus, the Unhallowed // would make the deck imba\n"
                "1 Sol Ring (C21) 263\n")
        result = run_ship(deck)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "// Maybeboard\n"
            "1 Mikaeus, the Unhallowed // would make the deck imba\n"
            "1 Sol Ring\n",
            result.stdout,
        )

    def test_unowned_mainboard_nonbasic_refuses_naming_the_card(self):
        deck = "// Probe\n// Mainboard\n1 Mikaeus, the Unhallowed\n"
        result = run_ship(deck)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Mikaeus, the Unhallowed", result.stderr)
        self.assertIn("Maybeboard", result.stderr)


class ShippingIsTheIdentityOnItsOwnOutput(unittest.TestCase):
    """AC: Blocks survive the round-trip — re-shipping a shipped Deck Block
    is byte-identical, categories and the footer included, and the footer is
    never doubled."""

    DRAFT = (
        "// Golgari Reanimator\n"
        "// Commander\n"
        "1 Meren of Clan Nel Toth\n"
        "// Mainboard\n"
        "1 Sol Ring // ramp\n"
        "12 Forest\n"
        "8 Swamp\n"
        "// Maybeboard\n"
        "1 Mikaeus, the Unhallowed // would make the deck imba\n"
    )

    def test_round_trip_is_byte_identical_with_one_footer(self):
        first = run_ship(self.DRAFT)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("1 Sol Ring (C21) 263 // ramp\n", first.stdout)
        second = run_ship(first.stdout)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(second.stdout, first.stdout)
        self.assertEqual(first.stdout.count(FOOTER), 1)


class MultiFacedNamesShipWhole(unittest.TestCase):
    """Multi-faced names are flattened with " // " (the Oracle's vocabulary):
    a bare line naming one whole is a card, not a comment, whenever the name
    is known to the Collection or the Oracle — and the pin re-anchors it
    either way."""

    EXPORT = (
        "Binder Name,Binder Type,Name,Set code,Collector number,Foil,Quantity\n"
        "Box,binder,Emeritus of Abundance // Regrowth,SOS,145,normal,1\n"
    )

    def test_bare_known_whole_name_is_pinned_not_truncated(self):
        deck = "// Probe\n// Mainboard\n1 Emeritus of Abundance // Regrowth\n"
        result = run_ship(deck, self.EXPORT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Emeritus of Abundance // Regrowth (SOS) 145\n",
                      result.stdout)


RUNNER = REPO / "skills" / "suite-runner" / "scripts" / "check_deck.py"
VALIDATOR = REPO / "skills" / "brief" / "scripts" / "validate_brief.py"
UPGRADE_BRIEF = FIXTURES / "build" / "tatyova-upgrade.brief.txt"
BUILT_SUITE = FIXTURES / "build" / "tatyova-landfall.built.suite.yaml"
BUILT_DECK = FIXTURES / "build" / "tatyova-built-deck.txt"
BUILT_REPORT = FIXTURES / "build" / "tatyova-built-report.txt"


class BuildEndsGreenThroughTheFixedRunner(unittest.TestCase):
    """AC: Build loops — adding and swapping owned cards — until the Suite is
    green, and the Suite re-runs through the fixed runner. The committed
    built fixtures are that finished state: the Upgrade Brief (the existing
    ManaBox Tatyova deck rebuilt, its own rows freed by donor: lines), the
    built Suite (the generated Suite plus recorded Role tags, targets never
    bent), the shipped Deck Block, and the all-green report, byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_cli(
            RUNNER,
            "--suite", BUILT_SUITE,
            "--deck", BUILT_DECK,
            "--oracle", ORACLE,
            "--collection", REAL_EXPORT,
            "--date", REFERENCE_DATE,
        )

    def test_the_upgrade_brief_validates_against_the_export(self):
        result = run_cli(VALIDATOR, UPGRADE_BRIEF, "--collection", REAL_EXPORT)
        self.assertEqual(result.returncode, 0, result.stdout)
        text = UPGRADE_BRIEF.read_text(encoding="utf-8")
        self.assertIn("donor: Tatyova, Benthic Druid\n", text,
                      "the Upgrade frees the target Deck's own rows via donor:")

    def test_every_check_is_green_and_the_report_is_the_committed_reference(self):
        self.assertEqual(self.result.returncode, 0,
                         self.result.stdout + self.result.stderr)
        self.assertIn("verdict: green — 0 red /", self.result.stdout)
        expected = BUILT_REPORT.read_text(encoding="utf-8")
        self.assertEqual(self.result.stdout, expected)

    def test_build_never_bends_targets_only_roles_are_added(self):
        regenerated = run_cli(GENERATOR, "--brief", UPGRADE_BRIEF,
                              "--profile", PROFILE, "--oracle", ORACLE,
                              "--date", REFERENCE_DATE)
        self.assertEqual(regenerated.returncode, 0, regenerated.stderr)
        without_roles, role_lines, in_roles = [], [], False
        for line in BUILT_SUITE.read_text(encoding="utf-8").splitlines(True):
            if not line.startswith(" ") and line.strip():
                in_roles = line.rstrip() == "roles:"
            if in_roles and line.startswith("  ") and not line.lstrip().startswith("#"):
                role_lines.append(line)
                continue
            without_roles.append(line)
        self.assertEqual("".join(without_roles), regenerated.stdout,
                         "the built Suite must be the generated Suite plus "
                         "Role tags — a target changed")
        self.assertGreater(len(role_lines), 60,
                           "the built Suite records Role judgment per card")

    def test_the_shipped_deck_block_round_trips_byte_identical(self):
        # The re-ship reads the same Brief: the pin draws only from the
        # copies its donor: lines leave free.
        result = run_cli(SHIP, "--deck", BUILT_DECK,
                         "--collection", REAL_EXPORT,
                         "--brief", UPGRADE_BRIEF, "--oracle", ORACLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, BUILT_DECK.read_text(encoding="utf-8"))

    def test_the_shipped_deck_carries_footer_categories_and_maybeboard(self):
        text = BUILT_DECK.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("// Tatyova Landfall\n"))
        self.assertEqual(text.count(FOOTER), 1)
        self.assertIn("// Maybeboard\n", text)
        self.assertIn("1 Rhystic Study //", text)  # unowned, unpinned wishlist
        self.assertIn(" // draw", text)  # an inline category comment survives


class OracleGapDegradesPerCard(unittest.TestCase):
    """AC: a Deck card missing from the Oracle degrades per-card to flagged
    model knowledge, never a hard failure — the runner still reports, names
    the uncovered card in the report head, and exits red or green, never
    with the wrong-Suite refusal."""

    def test_missing_card_is_flagged_never_fatal(self):
        oracle_lines = [
            line for line in ORACLE.read_text(encoding="utf-8").splitlines()
            if '"Divination"' not in line
        ]
        with tempfile.TemporaryDirectory() as tmp:
            gapped = pathlib.Path(tmp) / "oracle.jsonl"
            gapped.write_text("\n".join(oracle_lines) + "\n", encoding="utf-8")
            result = run_cli(
                RUNNER,
                "--suite", BUILT_SUITE,
                "--deck", BUILT_DECK,
                "--oracle", gapped,
                "--collection", REAL_EXPORT,
                "--date", REFERENCE_DATE,
            )
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertIn("unknown to Oracle: Divination", result.stdout)
        self.assertIn("verdict:", result.stdout)


class BuildDeepEvalRunsGreen(SmokeGradingMixin, unittest.TestCase):
    """Acceptance: the build-deep eval case grades the whole seam offline —
    hard graders on Collection-only drawing, Format legality through the
    fixed runner, the ManaBox-importable Deck Block, and the Block
    round-trip; the Brief's-intent grader stays soft."""

    CASE = "build-deep"

    def test_case_exits_green(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"build-deep not green.\nstdout:\n{self.result.stdout}"
            f"\nstderr:\n{self.result.stderr}",
        )

    def test_upgrade_brief_graded_green(self):
        self.graded_green("Upgrade Brief")

    def test_collection_only_drawing_graded_green(self):
        self.graded_green("drawn from the Collection")

    def test_declined_contention_graded_green(self):
        self.graded_green("Declined contention")

    def test_green_report_through_the_fixed_runner_graded_green(self):
        self.graded_green("re-runs through the fixed runner")

    def test_targets_never_bent_graded_green(self):
        self.graded_green("never bends targets")

    def test_manabox_importable_block_graded_green(self):
        self.graded_green("ManaBox-importable")

    def test_maybeboard_wishlist_graded_green(self):
        self.graded_green("wishlist Board")

    def test_round_trip_graded_green(self):
        self.graded_green("round-trip")

    def test_oracle_gap_degradation_graded_green(self):
        self.graded_green("missing from the Oracle")

    def test_pasted_export_smoke_graded_green(self):
        self.graded_green("paste-shaped")

    def test_skill_back_half_content_graded_green(self):
        self.graded_green("back half")

    def test_brief_intent_stays_soft(self):
        self.assertTrue(
            any("honors the Brief" in text
                for text in self.grading["soft_expectations"]),
            "the Brief's-intent grader must stay soft LLM judgment",
        )


if __name__ == "__main__":
    unittest.main()
