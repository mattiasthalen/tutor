"""Tests for Tables — multi-deck sittings (issue #59).

A Table is planned in one brief conversation (a Table Brief plus N untouched
per-Deck Briefs), built Seat by Seat in seat order through the unchanged
build loop, and judged as one sitting by a Table Review. What is tested here
are the deterministic public seams only:

- ``skills/brief/scripts/validate_brief.py`` — the one Brief grammar
  authority, now covering the Table Brief Block (the ``table:`` anchor plus
  ``seat:`` lines) and the cross-Brief table checks: the seat join, the
  copy-down of table-level power/constraints/play variant/donors, and the
  mechanical declared-Power match,
- ``skills/build/scripts/availability.py`` — the contention arithmetic, now
  counting an earlier Seat's finished Deck Block as committed copies via
  ``--table-mate`` (table-mates are never Donor Decks),
- ``skills/build/scripts/ship_deck.py`` — printing pins drawn from the free
  pool with table-mate pins subtracted first,
- ``skills/review/scripts/assemble_table_review.py`` — the mechanical half
  of the Table Review, and
- the ``table-smoke`` eval case in the offline harness.

Everything runs through the CLIs — exit codes and stdout — never internals.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

from test_eval_harness import SmokeGradingMixin, run_harness

REPO = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = REPO / "skills" / "brief" / "scripts" / "validate_brief.py"
AVAILABILITY = REPO / "skills" / "build" / "scripts" / "availability.py"
SHIP = REPO / "skills" / "build" / "scripts" / "ship_deck.py"
TABLE_ASSEMBLER = (
    REPO / "skills" / "review" / "scripts" / "assemble_table_review.py"
)
FIXTURES = REPO / "evals" / "fixtures"

TABLE_FIXTURE = FIXTURES / "table" / "family-archenemy-night.table.txt"
MISMATCHED_FIXTURE = (
    FIXTURES / "table" / "family-archenemy-night-mismatched.table.txt"
)
VILLAIN_BRIEF = FIXTURES / "briefs" / "archenemy-bolas-villain.txt"
HERO_BRIEF = FIXTURES / "briefs" / "archenemy-meren-hero.txt"
REAL_EXPORT = FIXTURES / "collections" / "real-collection.csv"


def run_script(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_validator(*args):
    return run_script(VALIDATOR, *args)


class TableBriefGrammar(unittest.TestCase):
    """Acceptance: the Table Brief is recognized by its ``table:`` anchor
    plus ``seat:`` lines — an index that never embeds the per-Deck Briefs."""

    def validate_text(self, text, *args):
        with tempfile.TemporaryDirectory() as tmp:
            table = pathlib.Path(tmp) / "table.txt"
            table.write_text(text, encoding="utf-8")
            return run_validator(table, *args)

    def assert_invalid(self, text, needle):
        result = self.validate_text(text)
        self.assertEqual(result.returncode, 1, f"accepted:\n{text}\n{result.stdout}")
        self.assertIn("invalid", result.stdout)
        self.assertIn(needle, result.stdout, f"no {needle!r} in:\n{result.stdout}")

    def test_fixture_table_brief_is_valid(self):
        result = run_validator(TABLE_FIXTURE)
        self.assertEqual(
            result.returncode, 0,
            f"fixture Table Brief judged invalid:\n{result.stdout}{result.stderr}",
        )
        self.assertIn("Table Brief", result.stdout)

    def test_spec_sample_table_brief_is_valid(self):
        # The Tables decision's own sample, verbatim from spec #46 — the deck
        # name "Nicol Bolas, God-Pharaoh" carries a comma; only a trailing
        # ", power N" is the override.
        result = self.validate_text(
            "table: Family Archenemy Night\n"
            "format: commander\n"
            "play variant: archenemy\n"
            "power: 3\n"
            "seat: villain — Nicol Bolas, God-Pharaoh, power 4\n"
            "seat: hero — Meren Reanimator\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_roleless_seat_line_is_valid(self):
        result = self.validate_text(
            "table: Pod Night\nformat: commander\n"
            "seat: Tatyova Landfall\nseat: Meren Reanimator\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_single_seat_is_rejected(self):
        self.assert_invalid(
            "table: Solo\nformat: commander\nseat: Tatyova Landfall\n",
            "two Seats",
        )

    def test_missing_format_is_rejected(self):
        # One Format per Table: the Table Brief pins it.
        self.assert_invalid(
            "table: No Format\nseat: A Deck\nseat: B Deck\n", "format"
        )

    def test_per_deck_keys_are_rejected_never_embedded(self):
        # The Table Brief is an index — per-Deck keys mean a per-Deck Brief
        # is being embedded, and Blocks never embed one another.
        for key in ("name: Meren Reanimator", "centerpiece: Meren of Clan Nel Toth",
                    "identity: golgari"):
            self.assert_invalid(
                f"table: Night\nformat: commander\n{key}\n"
                "seat: A Deck\nseat: B Deck\n",
                "never embeds",
            )

    def test_empty_seat_deck_name_is_rejected(self):
        self.assert_invalid(
            "table: Night\nformat: commander\n"
            "seat: villain — , power 4\nseat: B Deck\n",
            "deck name",
        )

    def test_duplicate_seat_deck_name_is_rejected(self):
        # One physical Deck cannot fill two Seats at the same sitting.
        self.assert_invalid(
            "table: Night\nformat: commander\n"
            "seat: Same Deck\nseat: Same Deck\n",
            "Same Deck",
        )

    def test_out_of_ladder_seat_power_is_rejected(self):
        self.assert_invalid(
            "table: Night\nformat: commander\n"
            "seat: A Deck, power 6\nseat: B Deck\n",
            "1-5",
        )

    def test_table_power_with_trailing_text_is_valid(self):
        result = self.validate_text(
            "table: Night\nformat: commander\npower: 3, battlecruiser feel\n"
            "seat: A Deck\nseat: B Deck\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_kitchen20_table_carries_no_power(self):
        # Kitchen 20 Seats carry no Power — the Format pins it.
        self.assert_invalid(
            "table: Teaching Night\nformat: kitchen 20\npower: 2\n"
            "seat: Sunlit Whiskers\nseat: Ember Pups\n",
            "Kitchen 20",
        )

    def test_kitchen20_seat_power_override_is_rejected(self):
        self.assert_invalid(
            "table: Teaching Night\nformat: kitchen 20\n"
            "seat: Sunlit Whiskers, power 2\nseat: Ember Pups\n",
            "Kitchen 20",
        )

    def test_kitchen20_table_without_power_is_valid(self):
        result = self.validate_text(
            "table: Teaching Night\nformat: kitchen 20\n"
            "play variant: jumpstart 40\n"
            "seat: Sunlit Whiskers\nseat: Ember Pups\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_donor_naming_a_seat_deck_is_rejected(self):
        # Table-mates are never Donor Decks.
        self.assert_invalid(
            "table: Night\nformat: commander\ndonor: A Deck\n"
            "seat: A Deck\nseat: B Deck\n",
            "never Donor Decks",
        )


MINIMAL_TABLE = (
    "table: Night\nformat: commander\npower: 3\n"
    "seat: villain — A Deck, power 4\nseat: hero — B Deck\n"
)
MINIMAL_SEAT_A = "name: A Deck\nformat: commander\npower: 4\n"
MINIMAL_SEAT_B = "name: B Deck\nformat: commander\npower: 3\n"


class TableSeatJoinAndCopyDown(unittest.TestCase):
    """Acceptance: one brief conversation produces a Table Brief plus N
    untouched per-Deck Briefs; table-level power, constraints, play variant,
    and donors copy into each Seat's Brief, and every seat: deck name joins
    that Brief's name: line."""

    def validate_table(self, table_text, seat_texts, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            table = root / "table.txt"
            table.write_text(table_text, encoding="utf-8")
            args = [table]
            for index, text in enumerate(seat_texts):
                seat = root / f"seat{index}.txt"
                seat.write_text(text, encoding="utf-8")
                args += ["--seat-brief", seat]
            return run_validator(*args, *extra)

    def test_fixture_table_with_its_seat_briefs_is_valid(self):
        result = run_validator(
            TABLE_FIXTURE,
            "--seat-brief", VILLAIN_BRIEF,
            "--seat-brief", HERO_BRIEF,
            "--collection", REAL_EXPORT,
        )
        self.assertEqual(
            result.returncode, 0,
            f"fixture Table judged invalid:\n{result.stdout}{result.stderr}",
        )
        self.assertIn("2 seat", result.stdout)

    def test_seat_without_a_provided_brief_is_reported(self):
        result = self.validate_table(MINIMAL_TABLE, [MINIMAL_SEAT_A])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("joins no provided Brief", result.stdout)
        self.assertIn("B Deck", result.stdout)

    def test_stray_brief_filling_no_seat_is_reported(self):
        stray = "name: C Deck\nformat: commander\npower: 3\n"
        result = self.validate_table(
            MINIMAL_TABLE, [MINIMAL_SEAT_A, MINIMAL_SEAT_B, stray]
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("fills no seat", result.stdout)
        self.assertIn("C Deck", result.stdout)

    def test_format_mismatch_is_reported_one_format_per_table(self):
        off_format = "name: B Deck\nformat: standard\npower: 3\n"
        result = self.validate_table(MINIMAL_TABLE, [MINIMAL_SEAT_A, off_format])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("one Format per Table", result.stdout)

    def test_uncopied_play_variant_is_reported(self):
        table = MINIMAL_TABLE.replace(
            "power: 3\n", "play variant: archenemy\npower: 3\n"
        )
        seat_a = MINIMAL_SEAT_A.replace(
            "format: commander\n", "format: commander\nplay variant: archenemy\n"
        )
        result = self.validate_table(table, [seat_a, MINIMAL_SEAT_B])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("play variant", result.stdout)
        self.assertIn("not copied", result.stdout)

    def test_uncopied_constraint_is_reported(self):
        table = MINIMAL_TABLE.replace(
            "power: 3\n", "power: 3\nconstraint: nothing above 8 mana\n"
        )
        result = self.validate_table(table, [MINIMAL_SEAT_A, MINIMAL_SEAT_B])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("constraint", result.stdout)
        self.assertIn("not copied", result.stdout)

    def test_uncopied_donor_is_reported(self):
        table = MINIMAL_TABLE.replace(
            "power: 3\n", "power: 3\ndonor: Some Old Deck\n"
        )
        result = self.validate_table(table, [MINIMAL_SEAT_A, MINIMAL_SEAT_B])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("donor", result.stdout)
        self.assertIn("not copied", result.stdout)

    def test_seat_brief_donor_naming_a_table_mate_is_rejected(self):
        seat_b = MINIMAL_SEAT_B + "donor: A Deck\n"
        result = self.validate_table(MINIMAL_TABLE, [MINIMAL_SEAT_A, seat_b])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("never Donor Decks", result.stdout)

    def test_seat_brief_donor_naming_its_own_deck_is_the_upgrade_pattern(self):
        # An Upgrade frees the target Deck's own rows — a Seat's Brief naming
        # its own deck as donor is that ordinary pattern, not table poaching.
        seat_b = MINIMAL_SEAT_B + "donor: B Deck\n"
        result = self.validate_table(MINIMAL_TABLE, [MINIMAL_SEAT_A, seat_b])
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_seat_briefs_beside_a_per_deck_brief_are_unusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            brief = root / "brief.txt"
            brief.write_text("format: commander\n", encoding="utf-8")
            seat = root / "seat.txt"
            seat.write_text(MINIMAL_SEAT_A, encoding="utf-8")
            result = run_validator(brief, "--seat-brief", seat)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_a_table_brief_as_seat_brief_is_reported(self):
        result = self.validate_table(
            MINIMAL_TABLE, [MINIMAL_SEAT_A, MINIMAL_TABLE]
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("Table Brief", result.stdout)


class DeclaredPowerMatchCheck(unittest.TestCase):
    """Acceptance: declared-Power match is a mechanical Check — every Seat's
    effective Power equals the table's unless its seat line overrides."""

    validate_table = TableSeatJoinAndCopyDown.validate_table

    def test_fixture_table_power_match_is_green(self):
        # Villain overrides to 4 and its Brief declares 4; the hero seat
        # inherits the table's 3 and its Brief declares 3.
        result = run_validator(
            TABLE_FIXTURE,
            "--seat-brief", VILLAIN_BRIEF,
            "--seat-brief", HERO_BRIEF,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("declared-Power", result.stdout)

    def test_mismatched_fixture_goes_red_naming_the_seat(self):
        result = run_validator(
            MISMATCHED_FIXTURE,
            "--seat-brief", VILLAIN_BRIEF,
            "--seat-brief", HERO_BRIEF,
        )
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("declared-Power match", result.stdout)
        self.assertIn("Meren Reanimator", result.stdout)
        self.assertNotIn("Bolas Villain: ", result.stdout)

    def test_omitted_powers_default_together(self):
        # No table power:, no Brief power: — both read the shared default 2.
        table = "table: Night\nformat: commander\nseat: A Deck\nseat: B Deck\n"
        seats = ["name: A Deck\nformat: commander\n",
                 "name: B Deck\nformat: commander\n"]
        result = self.validate_table(table, seats)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_omitted_brief_power_mismatches_an_explicit_table_power(self):
        # The Brief's omitted power reads as 2; the table asks 3.
        table = "table: Night\nformat: commander\npower: 3\nseat: A Deck\nseat: B Deck\n"
        seats = ["name: A Deck\nformat: commander\npower: 3\n",
                 "name: B Deck\nformat: commander\n"]
        result = self.validate_table(table, seats)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("declared-Power match", result.stdout)
        self.assertIn("B Deck", result.stdout)

    def test_trailing_free_text_compares_on_the_number(self):
        # "4, big villain turns" declares 4 — the number is canonical.
        table = ("table: Night\nformat: commander\npower: 3\n"
                 "seat: villain — A Deck, power 4\nseat: B Deck\n")
        seats = ["name: A Deck\nformat: commander\npower: 4, big villain turns\n",
                 "name: B Deck\nformat: commander\npower: 3, but political\n"]
        result = self.validate_table(table, seats)
        self.assertEqual(result.returncode, 0, result.stdout)


# An earlier Seat's finished Deck Block, as the sequential build leaves it:
# real owned cards from the realism Export. Corsair Captain and Alania are
# the Collection's only copies; Giant Growth (FDN) 223 is one of two owned
# printings; the Maybeboard entry is wishlist, never a physical take.
VILLAIN_BLOCK = """\
// Bolas Villain

// Commander
1 Alania, Divergent Storm

// Mainboard
1 Corsair Captain
1 Giant Growth (FDN) 223

// Maybeboard
1 Arcane Omens
"""


class AvailabilityCountsTableMates(unittest.TestCase):
    """Acceptance: seat order = build order = contention priority — an
    earlier Seat's finished Deck Block counts as committed copies, and
    table-mates are never Donor Decks."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.villain_block = pathlib.Path(cls.tmp.name) / "bolas-villain.deck.txt"
        cls.villain_block.write_text(VILLAIN_BLOCK, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def availability(self, *args):
        return run_script(AVAILABILITY, "--collection", REAL_EXPORT, *args)

    def test_want_is_free_before_the_earlier_seat_finishes(self):
        result = self.availability("--want", "Corsair Captain")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 free of 1 owned", result.stdout)

    def test_earlier_seat_block_counts_as_committed_copies(self):
        result = self.availability(
            "--table-mate", self.villain_block, "--want", "Corsair Captain"
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Corsair Captain; all copies committed to Bolas Villain",
            result.stdout,
        )

    def test_commander_board_copies_count_too(self):
        result = self.availability(
            "--table-mate", self.villain_block,
            "--want", "Alania, Divergent Storm",
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("committed to Bolas Villain", result.stdout)

    def test_donor_lines_never_free_a_table_mate(self):
        for donor in ("Bolas Villain", "all"):
            result = self.availability(
                "--table-mate", self.villain_block,
                "--donor", donor,
                "--want", "Corsair Captain",
            )
            self.assertEqual(
                result.returncode, 1,
                f"--donor {donor} freed a table-mate's copies:\n{result.stdout}",
            )

    def test_table_mate_maybeboard_is_wishlist_not_a_take(self):
        result = self.availability(
            "--table-mate", self.villain_block, "--want", "Arcane Omens"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_remaining_copies_stay_free_at_the_honest_count(self):
        result = self.availability(
            "--table-mate", self.villain_block, "--want", "Giant Growth"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 free of 2 owned, 1 committed to Bolas Villain",
                      result.stdout)

    def test_whole_deck_checked_against_table_mates(self):
        with tempfile.TemporaryDirectory() as tmp:
            hero = pathlib.Path(tmp) / "hero.deck.txt"
            hero.write_text(
                "// Meren Reanimator\n\n// Mainboard\n1 Corsair Captain\n",
                encoding="utf-8",
            )
            result = self.availability(
                "--table-mate", self.villain_block, "--deck", hero
            )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("committed to Bolas Villain", result.stdout)

    def test_unreadable_table_mate_block_is_unusable(self):
        result = self.availability(
            "--table-mate", "no-such-block.txt", "--want", "Corsair Captain"
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


class ShipPinsRespectTableMates(unittest.TestCase):
    """Acceptance: an earlier Seat's finished Deck Block counts as committed
    copies — the printing pin draws only from what table-mates left free."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.tmp.name)
        cls.villain_block = root / "bolas-villain.deck.txt"
        cls.villain_block.write_text(VILLAIN_BLOCK, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ship(self, deck_text, *args):
        with tempfile.TemporaryDirectory() as tmp:
            deck = pathlib.Path(tmp) / "hero.deck.txt"
            deck.write_text(deck_text, encoding="utf-8")
            return run_script(
                SHIP, "--deck", deck, "--collection", REAL_EXPORT, *args
            )

    def test_pin_spills_to_the_printing_the_table_mate_left_free(self):
        # The villain took Giant Growth (FDN) 223; the hero's pin lands on
        # the owned (SOA) 52 copy instead.
        result = self.ship(
            "// Meren Reanimator\n\n// Mainboard\n1 Giant Growth\n",
            "--table-mate", self.villain_block,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Giant Growth (SOA) 52", result.stdout)
        self.assertNotIn("(FDN) 223", result.stdout)

    def test_pin_refuses_when_the_table_mate_holds_every_copy(self):
        result = self.ship(
            "// Meren Reanimator\n\n// Mainboard\n1 Corsair Captain\n",
            "--table-mate", self.villain_block,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Corsair Captain; all copies committed to Bolas Villain",
            result.stderr,
        )
        self.assertIn("never Donor Decks", result.stderr)

    def test_without_table_mates_the_fancier_ranked_pin_stands(self):
        result = self.ship(
            "// Meren Reanimator\n\n// Mainboard\n1 Giant Growth\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Giant Growth (FDN) 223", result.stdout)


def table_finding(severity="note", seats=("Bolas Villain",),
                  cards=("Probe Card",), problem="a probe problem",
                  **suggestion):
    entry = {"severity": severity, "seats": list(seats), "cards": list(cards),
             "problem": problem}
    entry.update(suggestion)
    return entry


class TableReviewAssembler(unittest.TestCase):
    """Acceptance: the Table Review judges the sitting as a whole — a Table
    Review Block with table:/date: lines, one overall verdict:, per-axis
    sections (power spread, play patterns, contention fallout) whose
    findings name Seats and cards, Verdicts computed, never re-judged."""

    AXES = ("power spread", "play patterns", "contention fallout")

    def assemble(self, power_spread, play_patterns, contention, *extra):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            args = [
                "--table-name", "Family Archenemy Night",
                "--date", "2026-08-19",
            ]
            for flag, findings in (
                ("--power-spread", power_spread),
                ("--play-patterns", play_patterns),
                ("--contention", contention),
            ):
                path = root / f"{flag.strip('-')}.json"
                path.write_text(json.dumps(findings), encoding="utf-8")
                args += [flag, path]
            return run_script(TABLE_ASSEMBLER, *args, *extra)

    def test_block_shape_names_seats_and_cards(self):
        result = self.assemble(
            [table_finding("blocker", ("Bolas Villain",), ("Expropriate",),
                           "chained extra turns land on power-3 heroes")],
            [],
            [table_finding("note", ("Meren Reanimator", "Bolas Villain"),
                           ("Corsair Captain",),
                           "both Seats wanted the same pirate")],
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(
            lines[:3],
            ["table: Family Archenemy Night", "date: 2026-08-19",
             "verdict: rebuild"],
        )
        self.assertEqual(
            [l for l in lines if l.startswith("verdict: ")],
            ["verdict: rebuild"],
        )
        positions = []
        for axis, verdict in (("power spread", "rebuild"),
                              ("play patterns", "ship"),
                              ("contention fallout", "playable")):
            self.assertIn(f"{axis}: {verdict}", lines)
            positions.append(lines.index(f"{axis}: {verdict}"))
        self.assertEqual(positions, sorted(positions), "axes out of order")
        self.assertIn(
            "blocker — seats: Bolas Villain — cards: Expropriate — "
            "chained extra turns land on power-3 heroes",
            lines,
        )
        self.assertIn(
            "note — seats: Meren Reanimator; Bolas Villain — cards: "
            "Corsair Captain — both Seats wanted the same pirate",
            lines,
        )

    def test_overall_verdict_is_the_worst_axis(self):
        clean = self.assemble([], [], [])
        self.assertIn("verdict: ship", clean.stdout)
        noted = self.assemble([], [table_finding()], [])
        self.assertIn("verdict: playable", noted.stdout)
        blocked = self.assemble([], [], [table_finding("blocker")])
        self.assertIn("verdict: rebuild", blocked.stdout)

    def test_blocker_past_the_display_cap_still_rebuilds(self):
        findings = [table_finding(cards=(f"Note {n}",)) for n in range(5)]
        findings.append(table_finding("blocker", cards=("Buried Blocker",)))
        result = self.assemble(findings, [], [])
        self.assertIn("power spread: rebuild", result.stdout)
        self.assertIn("verdict: rebuild", result.stdout)
        # Worst first: the blocker rises above the cap, never buried.
        self.assertIn("Buried Blocker", result.stdout)

    def test_cap_five_with_rest_summary_naming_seats_and_cards(self):
        findings = [
            table_finding(seats=(f"Seat {n}",), cards=(f"Card {n}",))
            for n in range(1, 8)
        ]
        result = self.assemble(findings, [], [])
        shown = [l for l in result.stdout.splitlines()
                 if l.startswith("note — ")]
        self.assertEqual(len(shown), 5, result.stdout)
        rest = [l for l in result.stdout.splitlines() if l.startswith("rest: ")]
        self.assertEqual(
            rest,
            ["rest: 2 more notes — seats: Seat 6; Seat 7 — cards: "
             "Card 6; Card 7"],
        )

    def test_malformed_findings_are_refused_with_no_partial_block(self):
        for label, bad in (
            ("no seats key", {"severity": "note", "cards": ["A Card"],
                              "problem": "x"}),
            ("empty seats", table_finding(seats=())),
            ("no cards key", {"severity": "note", "seats": ["A Seat"],
                              "problem": "x"}),
            ("two suggestions", table_finding(swap="A", maybeboard="B")),
            ("unknown severity", table_finding(severity="fatal")),
            ("unknown key", table_finding(fix="reseat the table")),
        ):
            result = self.assemble([bad], [], [])
            self.assertEqual(result.returncode, 2, f"{label}: {result.stdout}")
            self.assertEqual(result.stdout, "", f"{label} left a partial Block")

    def test_same_findings_assemble_to_the_same_bytes(self):
        twice = [
            self.assemble([table_finding("blocker")], [table_finding()], []).stdout
            for _ in range(2)
        ]
        self.assertEqual(twice[0], twice[1])


class TableSmokeEvalCase(SmokeGradingMixin, unittest.TestCase):
    """Acceptance: an eval covers Tables — a fixture Table Brief drives
    sequential builds that respect contention, and the power-match Check
    goes red on a mismatched fixture. Live conversation, build, and Table
    Review quality stay soft, dev-time judged."""

    CASE = "table-smoke"

    def test_table_smoke_runs_green(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"table-smoke not green.\nstdout:\n{self.result.stdout}"
            f"\nstderr:\n{self.result.stderr}",
        )
        self.assertEqual(self.grading["summary"]["failed"], 0)
        self.assertGreater(self.grading["summary"]["passed"], 0)

    def test_power_match_check_is_hard_graded(self):
        self.graded_green("declared-Power match")

    def test_sequential_contention_is_hard_graded(self):
        self.graded_green("committed copies")

    def test_live_expectations_stay_soft(self):
        soft = " ".join(self.grading["soft_expectations"])
        self.assertIn("Run live", soft)
        self.assertIn("brief conversation", soft)
        self.assertIn("Table Review", soft)


class TableSmokeCanGoRed(unittest.TestCase):
    """Green is only trustworthy if a mismatched fixture actually turns the
    case red: raise the hero Brief's declared Power and watch the
    declared-Power match catch it on the good Table too."""

    def test_tampered_seat_power_turns_the_case_red(self):
        import json
        import shutil

        with tempfile.TemporaryDirectory() as tmp:
            tampered_root = pathlib.Path(tmp) / "fixtures"
            shutil.copytree(FIXTURES, tampered_root)
            hero = tampered_root / "briefs" / "archenemy-meren-hero.txt"
            hero.write_text(
                hero.read_text(encoding="utf-8").replace(
                    "power: 3\n", "power: 5\n"
                ),
                encoding="utf-8",
            )
            out = pathlib.Path(tmp) / "results"
            result = run_harness(
                "--case", "table-smoke",
                "--fixture-root", tampered_root,
                "--out", out,
            )
            self.assertEqual(
                result.returncode, 1,
                f"table-smoke stayed green on a Power mismatch.\n"
                f"stdout:\n{result.stdout}",
            )
            grading = json.loads(
                (out / "table-smoke" / "grading.json").read_text(encoding="utf-8")
            )
            failed = [e for e in grading["expectations"] if not e["passed"]]
            self.assertTrue(
                any("declared-Power" in e["text"] for e in failed),
                f"no declared-Power expectation went red: "
                f"{[e['text'] for e in failed]}",
            )


if __name__ == "__main__":
    unittest.main()
