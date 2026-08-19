"""Tests for the Upgrade path — Build re-run semantics (issue #56).

The seams under test are the ticket's acceptance criteria, never internals:

- the availability CLI (``skills/build/scripts/availability.py``) — a Build
  re-run given an existing Deck frees that Deck's own copies automatically:
  Export rows committed to the Deck the Brief's ``name:`` line (or the Deck
  Block's title) names are free without any ``donor:`` line, while every
  other Deck's copies stay committed,
- the ship CLI (``skills/build/scripts/ship_deck.py``) — printing pins draw
  from the rebuilt Deck's own freed copies, so re-shipping after the human
  imported the Deck into ManaBox never raids the Deck it is rebuilding,
- the runner CLI (``skills/suite-runner/scripts/check_deck.py``) — the
  byte-identical Suite re-runs against a fresh Export: the availability
  Check's committed-by-default arithmetic never holds the Deck-under-check's
  own rows against it (the rebuilt Deck never contends with itself), and
- the ``upgrade-deep`` eval case in the offline harness.

Everything runs through the CLIs — exit codes and stdout/files — offline,
against committed fixtures or temp files written per test.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

from test_build_skill import (  # noqa: E402 — shared CLI seam helpers
    TempHome, mini_suite, oracle_card, oracle_json, run_mini,
)
from test_eval_harness import SmokeGradingMixin

REPO = pathlib.Path(__file__).resolve().parents[1]
AVAILABILITY = REPO / "skills" / "build" / "scripts" / "availability.py"

# An Export captured after the human imported the built Deck into ManaBox:
# the Deck's own copies now sit in a ManaBox deck carrying the Deck's name.
UPGRADE_EXPORT = (
    "Binder Name,Binder Type,Name,Quantity\n"
    "Tatyova Landfall,deck,Sol Ring,1\n"
    "Old Pile,deck,Lightning Bolt,1\n"
    "Shoebox,binder,Llanowar Elves,1\n"
)

SELF_BRIEF = "name: Tatyova Landfall\nformat: commander\n"


def run_cli(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=120,
    )


class BuildReRunFreesOwnCopiesAutomatically(unittest.TestCase):
    """AC: a Build re-run given an existing Deck frees that Deck's own copies
    automatically — the rebuilt Deck never contends with itself, and no
    donor: line naming the Deck itself is ever needed."""

    def test_the_brief_named_deck_own_copies_are_free(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        collection = home.write("collection.csv", UPGRADE_EXPORT)
        brief = home.write("brief.txt", SELF_BRIEF)
        result = run_cli(AVAILABILITY, "--collection", collection,
                         "--brief", brief, "--want", "Sol Ring")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Sol Ring: 1 free of 1 owned", result.stdout)

    def test_other_decks_copies_stay_committed(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        collection = home.write("collection.csv", UPGRADE_EXPORT)
        brief = home.write("brief.txt", SELF_BRIEF)
        result = run_cli(AVAILABILITY, "--collection", collection,
                         "--brief", brief, "--want", "Lightning Bolt")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Lightning Bolt; all copies committed to Old Pile",
            result.stdout,
        )

    def test_a_differently_named_brief_frees_nothing(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        collection = home.write("collection.csv", UPGRADE_EXPORT)
        brief = home.write("brief.txt", "name: Another Deck\nformat: commander\n")
        result = run_cli(AVAILABILITY, "--collection", collection,
                         "--brief", brief, "--want", "Sol Ring")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Sol Ring; all copies committed to Tatyova Landfall",
            result.stdout,
        )

    def test_the_deck_blocks_title_frees_its_own_copies_too(self):
        # --deck mode with no Brief at all: the Block's '// <name>' title is
        # the ManaBox deck name the import created — its rows are the Deck's.
        home = TempHome()
        self.addCleanup(home.cleanup)
        collection = home.write("collection.csv", UPGRADE_EXPORT)
        deck = home.write(
            "deck.txt", "// Tatyova Landfall\n// Mainboard\n1 Sol Ring\n")
        result = run_cli(AVAILABILITY, "--collection", collection,
                         "--deck", deck)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Sol Ring: 1 free of 1 owned", result.stdout)


SHIP = REPO / "skills" / "build" / "scripts" / "ship_deck.py"

SHIP_UPGRADE_EXPORT = (
    "Binder Name,Binder Type,Name,Set code,Collector number,Foil,Quantity\n"
    "Tatyova Landfall,deck,Sol Ring,C21,263,foil,1\n"
    "Old Pile,deck,Lightning Bolt,CLB,187,foil,1\n"
)


class ShipPinsDrawFromTheRebuiltDecksOwnCopies(unittest.TestCase):
    """AC: the rebuilt Deck never contends with itself — after the human
    imported the shipped Block into ManaBox, a re-ship against the fresh
    Export pins the Deck's own copies without any donor: line, while another
    Deck's copies still refuse in the declined-contention sentence."""

    def run_ship(self, deck_text):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = home.write("deck.txt", deck_text)
        collection = home.write("collection.csv", SHIP_UPGRADE_EXPORT)
        return run_cli(SHIP, "--deck", deck, "--collection", collection)

    def test_own_committed_copy_pins_without_a_donor_line(self):
        result = self.run_ship(
            "// Tatyova Landfall\n// Mainboard\n1 Sol Ring\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("1 Sol Ring (C21) 263\n", result.stdout)

    def test_another_decks_copy_still_refuses(self):
        result = self.run_ship(
            "// Tatyova Landfall\n// Mainboard\n1 Lightning Bolt\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "wanted Lightning Bolt; all copies committed to Old Pile",
            result.stderr,
        )


class RunnerAvailabilityNeverContendsWithTheDeckItself(unittest.TestCase):
    """AC: the byte-identical Suite re-runs against the fresh Export — the
    availability Check's committed-by-default arithmetic (a Suite carrying
    constraints.donors) treats rows committed to the Deck-under-check's own
    title as free, so an Upgrade needs no regeneration and no donor: line
    naming the Deck itself; every other Deck's rows stay committed."""

    UPGRADED_COLLECTION = (
        "Binder Name,Binder Type,Name,Quantity\n"
        "Tatyova Landfall,deck,Rhystic Study,1\n"
        "Old Pile,deck,Lightning Bolt,1\n"
    )
    ORACLE = oracle_json(
        oracle_card("Rhystic Study"), oracle_card("Lightning Bolt"),
    )
    SUITE = mini_suite(["availability.in_collection"],
                       constraint_lines=["donors: []"])

    def run_deck(self, deck_text):
        home = TempHome()
        self.addCleanup(home.cleanup)
        return run_mini(home, self.SUITE, deck_text=deck_text,
                        oracle_text=self.ORACLE,
                        collection_text=self.UPGRADED_COLLECTION)

    def test_own_rows_are_free_under_the_decks_title(self):
        result = self.run_deck(
            "// Tatyova Landfall\n// Mainboard\n1 Rhystic Study\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green availability.in_collection — every card owned",
                      result.stdout)

    def test_other_decks_rows_stay_committed(self):
        result = self.run_deck(
            "// Tatyova Landfall\n// Mainboard\n1 Lightning Bolt\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "red   availability.in_collection — missing: Lightning Bolt "
            "(need 1, own 1, free 0 — committed to Old Pile)",
            result.stdout,
        )


class UpgradeDeepEvalRunsGreen(SmokeGradingMixin, unittest.TestCase):
    """Acceptance: the upgrade-deep eval case grades the Upgrade offline —
    an Upgrade run leaves the Suite bytes unchanged and reproduces the
    committed all-green report against the fresh Export, freed-own-copies
    availability is verified against the Collection fixture, contention
    stays real for every other Deck, and the build skill pins the Upgrade
    contract."""

    CASE = "upgrade-deep"

    def test_case_exits_green(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"upgrade-deep not green.\nstdout:\n{self.result.stdout}"
            f"\nstderr:\n{self.result.stderr}",
        )

    def test_freed_own_copies_availability_graded_green(self):
        self.graded_green("frees that Deck's own copies automatically")

    def test_suite_bytes_unchanged_graded_green(self):
        self.graded_green("byte-identical Suite artifact re-runs")

    def test_roles_already_cover_the_deck_graded_green(self):
        self.graded_green("only cards new to the pool")

    def test_contention_stays_real_graded_green(self):
        self.graded_green("Contention stays real")

    def test_upgrade_contract_pinned_graded_green(self):
        self.graded_green("Upgrade contract")


if __name__ == "__main__":
    unittest.main()
