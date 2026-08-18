"""Tests for Suite generation — Build starts red (issue #53).

The seams under test are the ticket's acceptance criteria, never internals:

- the runner CLI (``skills/suite-runner/scripts/check_deck.py``) interpreting
  Commander-shaped Suites — declarative data whose check ids resolve to the
  runner's fixed predicates (ADR 0005), including the Commander predicates
  (color identity, banlist, Game Changers, must-include),
- the generator CLI (``skills/build/scripts/generate_suite.py``) — Brief +
  Format profile (+ Oracle) in, the declarative Suite out, deterministic,
  refusing rather than silently bending a target, and
- the ``build-smoke`` eval case in the offline harness.

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
RUNNER = REPO / "skills" / "suite-runner" / "scripts" / "check_deck.py"
GENERATOR = REPO / "skills" / "build" / "scripts" / "generate_suite.py"
PROFILE = REPO / "skills" / "build" / "profiles" / "commander.yaml"
VALIDATOR = REPO / "skills" / "brief" / "scripts" / "validate_brief.py"
FIXTURES = REPO / "evals" / "fixtures"

# The date pinned into the committed build fixtures, so reports and Suites
# are byte-comparable regardless of the day tests run.
REFERENCE_DATE = "2026-08-18"


def run_cli(script, *args):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=120,
    )


class TempHome:
    """A temp Collection home holding the four runner inputs as files."""

    def __init__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._dir.name)

    def cleanup(self):
        self._dir.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path


# A minimal Commander-shaped Suite: only the params its listed checks read —
# none of the Kitchen 20 profile keys (rares, evergreen keywords, mono-color,
# nonbasic allow-list) exist here, exactly as a generated Commander Suite.
def mini_suite(checks, profile_lines=(), constraint_lines=(), quota_lines=()):
    lines = ["suite: Probe", "format: Commander", "profile:"]
    lines += [f"  {line}" for line in profile_lines]
    lines.append("quotas:")
    lines += [f"  {line}" for line in quota_lines]
    lines.append("constraints:")
    lines += [f"  {line}" for line in constraint_lines]
    lines.append("roles:")
    lines.append("checks:")
    for cid in checks:
        lines.append(f"  - id: {cid}")
        lines.append(f"    text: {cid} probe.")
    return "\n".join(lines) + "\n"


EMPTY_DECK = "// Probe\n// Mainboard\n"
EMPTY_COLLECTION = "Name,Quantity\n"


def run_mini(home, suite_text, deck_text=EMPTY_DECK, oracle_text="[]",
             collection_text=EMPTY_COLLECTION):
    return run_cli(
        RUNNER,
        "--suite", home.write("suite.yaml", suite_text),
        "--deck", home.write("deck.txt", deck_text),
        "--oracle", home.write("oracle.json", oracle_text),
        "--collection", home.write("collection.csv", collection_text),
        "--date", REFERENCE_DATE,
    )


class CommanderShapedSuiteRuns(unittest.TestCase):
    """A Suite is data the runner interprets: a Commander-shaped Suite —
    carrying only the parameters its listed checks read, none of the Kitchen
    20 keys — runs through the unmodified runner interface and reports."""

    def test_suite_without_kitchen20_params_reports(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        result = run_mini(home, mini_suite(["legality.size"],
                                           profile_lines=["deck_size: 100"]))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("verdict: red — 1 red / 0 green", result.stdout)
        self.assertIn("red   legality.size — 0 cards, need exactly 100",
                      result.stdout)


def oracle_card(name, **kw):
    """A minimal Collection-home Oracle record (issue #48 shape)."""
    base = {"name": name, "mana_value": 2.0, "colors": [], "color_identity": [],
            "type_line": "Creature", "oracle_text": "",
            "legalities": {"commander": "legal"}, "game_changer": False}
    base.update(kw)
    return base


def oracle_json(*cards):
    import json
    return json.dumps(list(cards))


class ColorIdentityCheck(unittest.TestCase):
    """Commander legality: every card stays inside the commander's color
    identity — red names the offenders, green on a conforming Deck, and
    vacuously green on the empty Deck (ADR 0005)."""

    SUITE = mini_suite(["legality.color_identity"],
                       profile_lines=["color_identity: [G, U]"])
    ORACLE = oracle_json(
        oracle_card("Llanowar Elves", color_identity=["G"]),
        oracle_card("Baylen, the Haymaker", color_identity=["G", "R", "W"]),
    )

    def test_offender_is_red_and_named(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = "// Probe\n// Mainboard\n1 Llanowar Elves\n1 Baylen, the Haymaker\n"
        result = run_mini(home, self.SUITE, deck_text=deck, oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "red   legality.color_identity — outside ['G', 'U']: "
            "Baylen, the Haymaker (R, W)",
            result.stdout,
        )

    def test_conforming_deck_is_green(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = "// Probe\n// Mainboard\n1 Llanowar Elves\n"
        result = run_mini(home, self.SUITE, deck_text=deck, oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "green legality.color_identity — every card inside ['G', 'U']",
            result.stdout,
        )

    def test_empty_deck_passes_vacuously(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        result = run_mini(home, self.SUITE, oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green legality.color_identity", result.stdout)


class BanlistCheck(unittest.TestCase):
    """Commander legality list: every card is legal under the profile's
    banlist key, read from the Oracle's legalities — a banned card is red by
    name with its status, an all-legal Deck green, the empty Deck vacuously
    green (ADR 0005: legality lists may pass vacuously)."""

    SUITE = mini_suite(["legality.banlist"],
                       profile_lines=["banlist_key: commander"])
    ORACLE = oracle_json(
        oracle_card("Llanowar Elves"),
        oracle_card("Griselbrand", legalities={"commander": "banned"}),
    )

    def test_banned_card_is_red_and_named(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = "// Probe\n// Mainboard\n1 Llanowar Elves\n1 Griselbrand\n"
        result = run_mini(home, self.SUITE, deck_text=deck, oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "red   legality.banlist — not legal in commander: Griselbrand (banned)",
            result.stdout,
        )

    def test_all_legal_deck_and_empty_deck_are_green(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        legal = run_mini(home, self.SUITE,
                         deck_text="// Probe\n// Mainboard\n1 Llanowar Elves\n",
                         oracle_text=self.ORACLE)
        empty = run_mini(home, self.SUITE, oracle_text=self.ORACLE)
        for result in (legal, empty):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "green legality.banlist — every card legal in commander",
                result.stdout,
            )


class GameChangersCheck(unittest.TestCase):
    """Commander brackets: at most the bracket's Game Changers limit, read
    from the Oracle's game_changer flag — over the limit is red naming the
    Game Changers, at or under it green, the empty Deck vacuously green."""

    ORACLE = oracle_json(
        oracle_card("Llanowar Elves"),
        oracle_card("Rhystic Study", game_changer=True),
        oracle_card("Vampiric Tutor", game_changer=True),
    )
    GC_DECK = ("// Probe\n// Mainboard\n1 Llanowar Elves\n"
               "1 Rhystic Study\n1 Vampiric Tutor\n")

    def suite(self, limit):
        return mini_suite(["legality.game_changers"],
                          profile_lines=[f"game_changers_max: {limit}"])

    def test_over_the_limit_is_red_and_named(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        result = run_mini(home, self.suite(0), deck_text=self.GC_DECK,
                          oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "red   legality.game_changers — 2 Game Changers, limit 0: "
            "Rhystic Study, Vampiric Tutor",
            result.stdout,
        )

    def test_within_the_limit_and_empty_deck_are_green(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        within = run_mini(home, self.suite(3), deck_text=self.GC_DECK,
                          oracle_text=self.ORACLE)
        self.assertEqual(within.returncode, 0, within.stdout + within.stderr)
        self.assertIn("green legality.game_changers — 2 Game Changers, limit 3",
                      within.stdout)
        empty = run_mini(home, self.suite(0), oracle_text=self.ORACLE)
        self.assertEqual(empty.returncode, 0, empty.stdout + empty.stderr)
        self.assertIn("green legality.game_changers — 0 Game Changers, limit 0",
                      empty.stdout)


class MustIncludeCheck(unittest.TestCase):
    """Mechanical Brief constraint: cards the Brief demands (the Centerpiece,
    'must include X') are in the Deck — red names what is missing, so this
    Check starts honestly red on the empty Deck."""

    SUITE = mini_suite(
        ["brief.includes"],
        constraint_lines=["must_include:", "  - Tatyova, Benthic Druid"],
    )
    ORACLE = oracle_json(oracle_card("Tatyova, Benthic Druid",
                                     color_identity=["G", "U"]))

    def test_empty_deck_is_red_naming_the_missing_card(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        result = run_mini(home, self.SUITE, oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("red   brief.includes — missing: Tatyova, Benthic Druid",
                      result.stdout)

    def test_present_card_is_green(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = "// Probe\n// Commander\n1 Tatyova, Benthic Druid\n// Mainboard\n"
        result = run_mini(home, self.SUITE, deck_text=deck, oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green brief.includes — all required cards present",
                      result.stdout)


class CurveChecksReadTheCollectionHomeOracle(unittest.TestCase):
    """The curve and cmc-cap predicates read `mana_value` — the Collection-home
    Oracle vocabulary (issue #48) — where the prototype's `cmc` is absent, so a
    generated Commander Suite stays runnable as Build adds real cards."""

    SUITE = mini_suite(
        ["curve.average", "curve.early_plays", "brief.cmc_max"],
        profile_lines=["curve_avg_max: 3.5", "early_nonland_cmc2_min: 1"],
        constraint_lines=["cmc_max: 3"],
    )
    ORACLE = oracle_json(
        oracle_card("Llanowar Elves", mana_value=2.0),
        oracle_card("Aggressive Mammoth", mana_value=5.0),
    )

    def test_mana_value_cards_are_counted_not_crashed(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = "// Probe\n// Mainboard\n1 Llanowar Elves\n1 Aggressive Mammoth\n"
        result = run_mini(home, self.SUITE, deck_text=deck, oracle_text=self.ORACLE)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("green curve.average — average 3.50, max 3.5", result.stdout)
        self.assertIn("green curve.early_plays — 1 nonland cards at mana value <=2, need 1",
                      result.stdout)
        self.assertIn("red   brief.cmc_max — above 3: Aggressive Mammoth", result.stdout)


class UnknownCheckIdRefusedCleanly(unittest.TestCase):
    """A check id resolving to no fixed predicate is a wrong Suite (or an old
    runner), never a verdict: the runner refuses with exit 2 — distinct from
    red's exit 1 — naming the id, and prints no half-report."""

    def test_unknown_id_names_itself_and_exits_2(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        result = run_mini(home, mini_suite(["legality.budget"]))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("legality.budget", result.stderr)
        self.assertEqual(result.stdout, "")


class ColorCoverageReadsTheCollectionHomeOracle(unittest.TestCase):
    """manabase.color_coverage works on the Collection-home Oracle vocabulary
    (issue #48), which carries no produced_mana field: production derives
    deterministically from the type line's basic land types and the oracle
    text's Add abilities — green when the mana base covers every spell color,
    red naming the gap, so the Check means something on a real Deck, not only
    the empty one. Where a produced_mana field exists (the suite-shape
    prototype's vocabulary), the field stays the authority."""

    SUITE = mini_suite(["manabase.color_coverage"])
    ORACLE = oracle_json(
        oracle_card("Llanowar Elves", colors=["G"], color_identity=["G"]),
        oracle_card("Counterspell", colors=["U"], color_identity=["U"]),
        oracle_card("Lightning Bolt", colors=["R"], color_identity=["R"]),
        oracle_card("Forest", mana_value=0.0, type_line="Basic Land — Forest",
                    oracle_text="({T}: Add {G}.)"),
        oracle_card("Temple of Mystery", mana_value=0.0, type_line="Land",
                    oracle_text="This land enters tapped.\n{T}: Add {G} or {U}."),
        oracle_card("Uncharted Haven", mana_value=0.0, type_line="Land",
                    oracle_text="This land enters tapped. As it enters, choose "
                                "a color.\n{T}: Add one mana of the chosen color."),
    )

    def run_deck(self, deck_lines, oracle_text=None):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = "// Probe\n// Mainboard\n" + "".join(f"1 {n}\n" for n in deck_lines)
        return run_mini(home, self.SUITE, deck_text=deck,
                        oracle_text=oracle_text or self.ORACLE)

    def test_basic_and_dual_lands_cover_the_spells(self):
        result = self.run_deck(["Llanowar Elves", "Counterspell",
                                "Forest", "Temple of Mystery"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "green manabase.color_coverage — spells need ['G', 'U'], "
            "lands make ['G', 'U']",
            result.stdout,
        )

    def test_uncovered_color_is_red_with_the_gap_shown(self):
        result = self.run_deck(["Llanowar Elves", "Lightning Bolt", "Forest"])
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "red   manabase.color_coverage — spells need ['G', 'R'], "
            "lands make ['G']",
            result.stdout,
        )

    def test_chosen_color_land_covers_any_spell_color(self):
        result = self.run_deck(["Lightning Bolt", "Uncharted Haven"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green manabase.color_coverage", result.stdout)

    def test_a_produced_mana_field_still_wins_over_derivation(self):
        oracle = oracle_json(
            oracle_card("Llanowar Elves", colors=["G"], color_identity=["G"]),
            oracle_card("Barren Glade", mana_value=0.0, type_line="Land",
                        oracle_text="({T}: Add {G}.)", produced_mana=[]),
        )
        result = self.run_deck(["Llanowar Elves", "Barren Glade"],
                               oracle_text=oracle)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "red   manabase.color_coverage — spells need ['G'], "
            "lands make nothing",
            result.stdout,
        )


class YamlParserStaysInLockstepWithTheRunner(unittest.TestCase):
    """generate_suite.py carries a deliberate copy of the runner's tiny
    YAML-subset parser — not imported, so skill assets stay self-contained —
    'kept in lockstep by hand'. This pin makes the lockstep mechanical: the
    two parser sources must stay byte-identical, so what the generator emits
    the runner re-reads with the same grammar."""

    @staticmethod
    def load(path, name):
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_parser_sources_are_identical(self):
        import inspect
        runner = self.load(RUNNER, "lockstep_runner")
        generator = self.load(GENERATOR, "lockstep_generator")
        for name in ("parse_scalar", "parse_yaml"):
            with self.subTest(function=name):
                self.assertEqual(
                    inspect.getsource(getattr(generator, name)),
                    inspect.getsource(getattr(runner, name)),
                    f"{name} drifted between generate_suite.py and check_deck.py",
                )


def generate(*args):
    return run_cli(GENERATOR, *args)


def generate_tatyova(*extra):
    return generate(
        "--brief", FIXTURES / "briefs" / "commander-tatyova-landfall.txt",
        "--profile", PROFILE,
        "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
        "--date", REFERENCE_DATE,
        *extra,
    )


class GeneratedSuiteReproducesTheFixture(unittest.TestCase):
    """Build start, end to end: the fixture Tatyova Brief plus the Commander
    Format profile plus the fixture Oracle yield the committed fixture Suite,
    byte-identical — snapshotted targets, quota table, mechanical constraints,
    Role tags section (empty before any card is picked), and check ids that
    resolve to the runner's fixed predicates. Data, never code (ADR 0005)."""

    def test_byte_identical_to_the_committed_fixture_suite(self):
        result = generate_tatyova()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = (FIXTURES / "build" / "tatyova-landfall.suite.yaml").read_text(
            encoding="utf-8")
        self.assertEqual(result.stdout, expected)


class ProfileConsistencyTargetIsSatisfiable(unittest.TestCase):
    """The Commander profile is self-consistent: its consistency threshold is
    satisfiable at lands_min. Exact hypergeometric P(>=2 lands in a 7-card
    hand) rises with the land count, so the land window's floor is the
    binding case — if the floor cleared less than p_2plus_lands_in_7_min,
    legality.land_count and consistency.opening_lands could never both be
    green and every Suite from this profile would be unwinnable."""

    def profile_value(self, text, key):
        import re
        m = re.search(rf"^  {key}: (\S+)$", text, re.MULTILINE)
        self.assertIsNotNone(m, f"the profile has no {key}: target")
        return float(m.group(1))

    def test_threshold_holds_at_the_land_window_floor(self):
        import math
        text = PROFILE.read_text(encoding="utf-8")
        deck_size = int(self.profile_value(text, "deck_size"))
        lands_min = int(self.profile_value(text, "lands_min"))
        threshold = self.profile_value(text, "p_2plus_lands_in_7_min")
        p_at_floor = 1 - sum(
            math.comb(lands_min, k) * math.comb(deck_size - lands_min, 7 - k)
            for k in (0, 1)
        ) / math.comb(deck_size, 7)
        self.assertGreaterEqual(
            p_at_floor, threshold,
            f"P(>=2 lands in 7 | N={deck_size}, K={lands_min}) = {p_at_floor:.4f} "
            f"< threshold {threshold}: no legal land count could green the "
            "consistency Check",
        )


TATYOVA_BRIEF = (FIXTURES / "briefs" / "commander-tatyova-landfall.txt")


class BriefOverridesNeverSilentlyBent(unittest.TestCase):
    """Check targets come from the Format profile; only the Brief may
    override them — each override lands under a `# brief:` provenance
    comment, and anything the generator cannot translate refuses the run
    rather than bending or dropping a target."""

    def brief_with(self, extra_lines=(), drop_prefix=None):
        text = TATYOVA_BRIEF.read_text(encoding="utf-8")
        lines = [l for l in text.splitlines()
                 if drop_prefix is None or not l.startswith(drop_prefix)]
        home = TempHome()
        self.addCleanup(home.cleanup)
        return home.write("brief.txt", "\n".join(lines + list(extra_lines)) + "\n")

    def generate_brief(self, brief_path, *extra):
        return generate("--brief", brief_path, "--profile", PROFILE,
                        "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
                        "--date", REFERENCE_DATE, *extra)

    def test_quota_ask_overrides_the_profile_with_provenance(self):
        brief = self.brief_with(["constraint: at least 12 ramp cards"])
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  # brief: constraint: at least 12 ramp cards\n  ramp: 12\n",
                      result.stdout)
        self.assertNotIn("ramp: 10", result.stdout)

    def test_lands_ask_overrides_the_profile_targets(self):
        brief = self.brief_with(["constraint: at least 38 lands"])
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  # brief: constraint: at least 38 lands\n  lands_min: 38\n",
                      result.stdout)

    def test_untranslatable_constraint_refuses_the_run(self):
        brief = self.brief_with(["constraint: keep it spicy"])
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("keep it spicy", result.stderr)
        self.assertIn("never silently", result.stderr)

    def test_quota_outside_the_role_vocabulary_refuses(self):
        brief = self.brief_with(["constraint: at least 4 dragons cards"])
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("dragons", result.stderr)
        self.assertIn("ramp", result.stderr)  # the vocabulary is named

    def test_identity_conflicting_with_the_oracle_refuses(self):
        brief = self.brief_with(["identity: gruul"], drop_prefix="identity:")
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("gruul", result.stderr)

    def test_missing_centerpiece_refuses_for_commander(self):
        brief = self.brief_with(drop_prefix="centerpiece:")
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("centerpiece", result.stderr)


class BriefGrammarMatchesTheValidator(unittest.TestCase):
    """One grammar, one authority (validate_brief.py): a Brief the validator
    rejects — here a repeated non-repeatable key — is unusable input to the
    generator too, never silently collapsed to its first occurrence; the
    repeatable keys (constraint, donor) still repeat."""

    def brief_plus(self, extra_lines):
        home = TempHome()
        self.addCleanup(home.cleanup)
        text = TATYOVA_BRIEF.read_text(encoding="utf-8")
        return home.write("brief.txt", text + "\n".join(extra_lines) + "\n")

    def generate_brief(self, brief_path):
        return generate("--brief", brief_path, "--profile", PROFILE,
                        "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
                        "--date", REFERENCE_DATE)

    def test_repeated_non_repeatable_key_is_refused_like_the_validator(self):
        brief = self.brief_plus(["power: 5"])  # the fixture already says power: 2
        rejected = run_cli(VALIDATOR, brief)
        self.assertEqual(rejected.returncode, 1, rejected.stdout)
        self.assertIn("repeats", rejected.stdout)
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn("'power'", result.stderr)
        self.assertIn("repeat", result.stderr)

    def test_repeatable_keys_still_repeat(self):
        brief = self.brief_plus(["constraint: at least 12 ramp cards",
                                 "donor: all"])  # second constraint, second donor
        accepted = run_cli(VALIDATOR, brief)
        self.assertEqual(accepted.returncode, 0, accepted.stdout)
        result = self.generate_brief(brief)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ramp: 12", result.stdout)


class PowerReadsAsTheBracket(unittest.TestCase):
    """Commander reads Power as the official Bracket: per-bracket Game
    Changers limits are 0 / 0 / 3 / unlimited / unlimited, and an unlimited
    bracket generates no Game Changers Check at all."""

    def generate_power(self, power_line):
        text = TATYOVA_BRIEF.read_text(encoding="utf-8")
        lines = [l for l in text.splitlines() if not l.startswith("power:")]
        home = TempHome()
        self.addCleanup(home.cleanup)
        brief = home.write("brief.txt", "\n".join(lines + list(power_line)) + "\n")
        return generate("--brief", brief, "--profile", PROFILE,
                        "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
                        "--date", REFERENCE_DATE)

    def test_bracket_3_snapshots_a_limit_of_3(self):
        result = self.generate_power(["power: 3, upgraded feel"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("game_changers_max: 3", result.stdout)
        self.assertIn("id: legality.game_changers", result.stdout)

    def test_unlimited_bracket_generates_no_game_changers_check(self):
        result = self.generate_power(["power: 4"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("game_changers_max", result.stdout)
        self.assertNotIn("legality.game_changers", result.stdout)

    def test_unstated_power_defaults_to_bracket_2_labelled_default(self):
        result = self.generate_power([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# default: power: 2 — bracket allows 0 Game Changers",
                      result.stdout)
        self.assertNotIn("# brief: power:", result.stdout)


class IdentityWithoutAnOracle(unittest.TestCase):
    """With no Oracle on hand the Brief's identity: word still resolves the
    color identity deterministically — Build can offer /tutor:oracle, but a
    settled Brief is enough to generate."""

    def test_named_identity_resolves_without_oracle(self):
        result = generate("--brief", TATYOVA_BRIEF, "--profile", PROFILE,
                          "--date", REFERENCE_DATE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  # brief: identity: simic\n  color_identity: [G, U]\n",
                      result.stdout)


# test_review_skill.py carries deliberate copies of these two helpers
# (run_fixture_suite and verdict_colors), and evals/run_evals.py carries the
# same check-line regex as report_colors — grader independence, never
# imported; kept in lockstep by hand. Edit them together.
def run_fixture_suite(deck_path):
    return run_cli(
        RUNNER,
        "--suite", FIXTURES / "build" / "tatyova-landfall.suite.yaml",
        "--deck", deck_path,
        "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
        "--collection", FIXTURES / "collections" / "real-collection.csv",
        "--date", REFERENCE_DATE,
    )


def verdicts(report):
    """(color, check id) pairs from a report Block's check lines."""
    import re as _re
    return dict(
        (m.group(2), m.group(1))
        for m in (_re.match(r"^(red|green)\s+(\S+) — ", line)
                  for line in report.splitlines())
        if m
    )


class BuildStartsRed(unittest.TestCase):
    """On the empty Deck, through the unmodified runner: every size,
    mana-base, curve, and quota Check is red; constraint-shaped Checks
    (singleton, legality lists, availability) pass vacuously — vacuous green
    is honest (ADR 0005 amending 0003). The report is the committed reference,
    byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_fixture_suite(FIXTURES / "build" / "tatyova-empty-deck.txt")

    def test_report_matches_the_committed_reference(self):
        expected = (FIXTURES / "build" / "tatyova-empty-report.txt").read_text(
            encoding="utf-8")
        self.assertEqual(self.result.stdout, expected)

    def test_exit_code_is_red(self):
        self.assertEqual(self.result.returncode, 1)

    def test_every_size_manabase_curve_and_quota_check_is_red(self):
        colors = verdicts(self.result.stdout)
        for cid in ("legality.size", "legality.land_count", "curve.average",
                    "curve.early_plays", "quota.ramp", "quota.draw",
                    "quota.removal", "quota.wipe", "quota.wincon",
                    "consistency.opening_lands", "brief.includes"):
            self.assertEqual(colors.get(cid), "red", f"{cid}: {colors.get(cid)}")

    def test_constraint_shaped_checks_pass_vacuously(self):
        colors = verdicts(self.result.stdout)
        for cid in ("legality.singleton", "legality.color_identity",
                    "legality.banlist", "legality.game_changers",
                    "availability.in_collection", "manabase.color_coverage",
                    "brief.cmc_max"):
            self.assertEqual(colors.get(cid), "green", f"{cid}: {colors.get(cid)}")


class PlantedFlawsGoRed(unittest.TestCase):
    """The same generated Suite over the flawed fixture Deck: the planted
    Commander flaws (manifest.json) — an unowned card, an off-identity card,
    a broken singleton — each turn their Check red naming the culprit."""

    @classmethod
    def setUpClass(cls):
        cls.result = run_fixture_suite(
            FIXTURES / "decks" / "tatyova-landfall-flawed.txt")

    def test_flaws_are_caught_naming_the_cards(self):
        self.assertEqual(self.result.returncode, 1)
        colors = verdicts(self.result.stdout)
        self.assertEqual(colors.get("availability.in_collection"), "red")
        self.assertIn("Rhystic Study", self.result.stdout)
        self.assertEqual(colors.get("legality.color_identity"), "red")
        self.assertIn("Baylen, the Haymaker", self.result.stdout)
        self.assertEqual(colors.get("legality.singleton"), "red")
        self.assertIn("Aetherspouts", self.result.stdout)


class BuildSmokeEvalRunsGreen(SmokeGradingMixin, unittest.TestCase):
    """Acceptance: the build-smoke eval case grades the whole seam offline —
    a fixture Brief yields a Suite of the expected shape and a red empty-Deck
    report through the runner — every mechanical expectation green."""

    CASE = "build-smoke"

    def test_case_exits_green(self):
        self.assertEqual(
            self.result.returncode, 0,
            f"build-smoke not green.\nstdout:\n{self.result.stdout}"
            f"\nstderr:\n{self.result.stderr}",
        )

    def test_suite_generation_graded_green(self):
        self.graded_green("byte-identical")

    def test_suite_shape_graded_green(self):
        self.graded_green("Check class")

    def test_empty_deck_report_graded_green(self):
        self.graded_green("empty fixture Deck")

    def test_command_wiring_graded_green(self):
        self.graded_green("/tutor:build")


if __name__ == "__main__":
    unittest.main()
