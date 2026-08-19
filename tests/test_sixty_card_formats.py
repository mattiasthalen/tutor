"""Tests for the 60-card Formats vertical (issue #58).

The seams under test are the ticket's acceptance criteria, never internals:

- the four Format profile files (``skills/build/profiles/{casual-60,standard,
  modern,pioneer}.yaml``) read as data through the generator's own public
  parse — Casual 60 targets, thin sanctioned profiles whose legality comes
  from the Oracle's per-card legalities, the shared Power ladder, and the one
  shared review-standards list,
- the generator CLI (``skills/build/scripts/generate_suite.py``) — Power
  defaulting to 2, mono-color identity words, and the committed Casual 60
  Suite regenerating up to its recorded Role tags,
- the runner CLI (``skills/suite-runner/scripts/check_deck.py``) — the
  four-copy limit as a parameter, the committed Casual 60 Deck all green
  byte-identical, and the sanctioned-legality Check red on a fixture card the
  Oracle marks illegal in that Format, and
- the assembler CLI (``skills/review/scripts/assemble_review.py``) — the
  committed Casual 60 Review Block reassembling byte-identical.

Everything runs through the CLIs and files — offline, against committed
fixtures or temp files written per test.
"""

import pathlib
import sys
import unittest

from test_build_skill import (
    REFERENCE_DATE, TempHome, mini_suite, oracle_card, oracle_json, run_cli,
    run_mini,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
RUNNER = REPO / "skills" / "suite-runner" / "scripts" / "check_deck.py"
GENERATOR = REPO / "skills" / "build" / "scripts" / "generate_suite.py"
ASSEMBLER = REPO / "skills" / "review" / "scripts" / "assemble_review.py"
PROFILES = REPO / "skills" / "build" / "profiles"
FIXTURES = REPO / "evals" / "fixtures"

sys.path.insert(0, str(REPO / "skills" / "build" / "scripts"))
import generate_suite  # noqa: E402  (the profile's own public parse)

SIXTY_CARD_FORMATS = {
    "casual-60": ("casual 60", "Casual 60"),
    "standard": ("standard", "Standard"),
    "modern": ("modern", "Modern"),
    "pioneer": ("pioneer", "Pioneer"),
}
SANCTIONED = ("standard", "modern", "pioneer")


def load_profile(slug):
    text = (PROFILES / f"{slug}.yaml").read_text(encoding="utf-8")
    return generate_suite.parse_yaml(text), text


class Casual60ProfileIsData(unittest.TestCase):
    """Acceptance: Casual 60 profile — deck size, copy limits, check
    targets — all first-class data, no banlist, no Centerpiece demand."""

    @classmethod
    def setUpClass(cls):
        cls.prof, cls.text = load_profile("casual-60")

    def test_format_names(self):
        self.assertEqual(self.prof["format"], "casual 60")
        self.assertEqual(self.prof["display_name"], "Casual 60")

    def test_deck_size_and_copy_limit(self):
        self.assertEqual(self.prof["profile"]["deck_size"], 60)
        self.assertEqual(self.prof["profile"]["copy_limit_nonland"], 4)

    def test_check_targets_present(self):
        profile = self.prof["profile"]
        for target in ("lands_min", "lands_max", "curve_avg_max",
                       "early_nonland_cmc2_min", "p_2plus_lands_in_7_min"):
            self.assertIn(target, profile)
        self.assertLessEqual(profile["lands_min"], profile["lands_max"])

    def test_consistency_target_satisfiable_at_lands_min(self):
        # The binding case is lands_min (P rises with the land count): the
        # committed threshold must be at or below the exact hypergeometric
        # P(>=2 lands in a 7-card hand | N=60, K=lands_min), rounded down.
        import math
        p = self.prof["profile"]
        N, K, n = p["deck_size"], p["lands_min"], 7
        pge2 = 1 - sum(
            math.comb(K, k) * math.comb(N - K, n - k) for k in (0, 1)
        ) / math.comb(N, n)
        self.assertLessEqual(p["p_2plus_lands_in_7_min"], round(pge2, 2))

    def test_no_banlist_and_no_centerpiece_demand(self):
        self.assertNotIn("banlist_key", self.prof["profile"])
        self.assertNotEqual(self.prof.get("centerpiece"), "required")
        check_ids = [c["id"] for c in self.prof["checks"]]
        self.assertNotIn("legality.banlist", check_ids)

    def test_quotas_over_the_role_vocabulary(self):
        vocabulary = {"ramp", "draw", "removal", "wipe", "wincon",
                      "theme", "other"}
        quotas = self.prof.get("quotas", {})
        self.assertTrue(quotas, "no Role quotas authored")
        self.assertLessEqual(set(quotas), vocabulary)


def section_slice(text, name):
    """The raw lines of one top-level section, comments included — the byte
    surface the four profiles must share where a section is shared. A
    deliberate sibling of the harness's section_lines (evals/run_evals.py):
    the same section walk over a stricter surface — grader independence,
    never imported, kept in lockstep by hand. Edit them together."""
    lines = text.splitlines()
    out, inside = [], False
    for line in lines:
        if line and not line.startswith(" ") and not line.startswith("#"):
            inside = line.rstrip() == f"{name}:"
            continue
        if inside and line.strip():
            out.append(line)
    return "\n".join(out)


def ban_keys(node, path=""):
    """Every mapping key mentioning 'ban', with its path — the tripwire for a
    hand-maintained banlist hiding anywhere in a profile."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{path}.{key}" if path else str(key)
            if "ban" in str(key).lower():
                found.append(where)
            found += ban_keys(value, where)
    elif isinstance(node, list):
        for item in node:
            found += ban_keys(item, path)
    return found


class SanctionedProfilesAreThin(unittest.TestCase):
    """Acceptance: thin Standard / Modern / Pioneer profiles — legality read
    per card from the Oracle's legalities, no hand-maintained banlists; the
    profiles are Casual 60 plus exactly the banlist parameter."""

    @classmethod
    def setUpClass(cls):
        cls.casual, cls.casual_text = load_profile("casual-60")

    def test_sanctioned_profiles_add_only_the_banlist_parameter(self):
        for slug in SANCTIONED:
            prof, _ = load_profile(slug)
            fmt, display = SIXTY_CARD_FORMATS[slug]
            with self.subTest(slug=slug):
                self.assertEqual(prof["format"], fmt)
                self.assertEqual(prof["display_name"], display)
                expected_profile = dict(self.casual["profile"])
                expected_profile["banlist_key"] = fmt
                self.assertEqual(prof["profile"], expected_profile)
                self.assertEqual(prof["quotas"], self.casual["quotas"])
                self.assertEqual(prof["role_guidance"],
                                 self.casual["role_guidance"])

    def test_banlist_key_is_the_oracle_legalities_key(self):
        oracle_line = (FIXTURES / "scryfall" / "oracle.jsonl").open(
            encoding="utf-8").readlines()[1]
        import json
        legality_keys = set(json.loads(oracle_line)["legalities"])
        for slug in SANCTIONED:
            prof, _ = load_profile(slug)
            with self.subTest(slug=slug):
                self.assertIn(prof["profile"]["banlist_key"], legality_keys)

    def test_banlist_check_is_the_only_addition_to_the_check_list(self):
        casual_ids = [c["id"] for c in self.casual["checks"]]
        for slug in SANCTIONED:
            prof, _ = load_profile(slug)
            with self.subTest(slug=slug):
                ids = [c["id"] for c in prof["checks"]]
                self.assertIn("legality.banlist", ids)
                self.assertEqual(
                    [i for i in ids if i != "legality.banlist"], casual_ids)

    def test_no_hand_maintained_banlist_anywhere(self):
        for slug in ("casual-60",) + SANCTIONED:
            prof, _ = load_profile(slug)
            keys = [k for k in ban_keys(prof) if k != "profile.banlist_key"]
            with self.subTest(slug=slug):
                self.assertEqual(keys, [], f"ban-shaped data beyond the key: {keys}")
                if slug != "casual-60":
                    # The parameter names a key the runner reads per card —
                    # a string, never a list of card names.
                    self.assertIsInstance(prof["profile"]["banlist_key"], str)


class SharedLadderAndReviewStandards(unittest.TestCase):
    """Acceptance: Power profile-interpreted on the shared 1-5 ladder (1 jank
    ... 5 competitive); the four 60-card Formats share one review-standards
    list."""

    SHARED_SECTIONS = ("power_ladder", "review_standards")

    def test_shared_sections_byte_identical_across_the_four(self):
        slugs = list(SIXTY_CARD_FORMATS)
        reference_text = (PROFILES / "casual-60.yaml").read_text(encoding="utf-8")
        for section in self.SHARED_SECTIONS:
            reference = section_slice(reference_text, section)
            self.assertTrue(reference, f"casual-60 has no {section}: section")
            for slug in slugs[1:]:
                text = (PROFILES / f"{slug}.yaml").read_text(encoding="utf-8")
                with self.subTest(slug=slug, section=section):
                    self.assertEqual(section_slice(text, section), reference)

    def test_ladder_runs_one_jank_to_five_competitive(self):
        for slug in SIXTY_CARD_FORMATS:
            prof, _ = load_profile(slug)
            ladder = prof["power_ladder"]
            with self.subTest(slug=slug):
                # Mapping keys stay strings in the YAML subset — the same
                # contract the generator reads Commander's bracket table with.
                self.assertEqual(sorted(ladder), ["1", "2", "3", "4", "5"])
                self.assertIn("jank", str(ladder["1"]).lower())
                self.assertIn("competitive", str(ladder["5"]).lower())

    def test_review_standards_carry_guidance_text(self):
        for slug in SIXTY_CARD_FORMATS:
            prof, _ = load_profile(slug)
            standards = prof["review_standards"]
            with self.subTest(slug=slug):
                self.assertTrue(standards)
                for name, guidance in standards.items():
                    self.assertTrue(str(guidance).strip(),
                                    f"{name} carries no guidance")

    def test_an_entry_overrides_a_baseline_smell_by_name(self):
        # The override mechanism the review skill pins: an entry sharing a
        # baseline Smell's name replaces that Smell's reading. The shared
        # 60-card list re-reads interaction mismatch for the duel.
        prof, _ = load_profile("casual-60")
        self.assertIn("interaction mismatch", prof["review_standards"])


class GeneratorReadsSixtyCardBriefs(unittest.TestCase):
    """Acceptance: Power is profile-interpreted on the shared 1-5 ladder,
    defaulting to 2; the fixture Briefs' mono-color identity words generate."""

    def generate(self, brief_text, slug="casual-60"):
        home = TempHome()
        self.addCleanup(home.cleanup)
        brief = home.write("brief.txt", brief_text)
        return run_cli(
            GENERATOR, "--brief", brief,
            "--profile", PROFILES / f"{slug}.yaml",
            "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
            "--date", REFERENCE_DATE,
        )

    def test_unstated_power_defaults_to_2_in_the_suite(self):
        result = self.generate("format: casual 60\nidentity: red\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("brief: casual 60 — power 2\n", result.stdout)
        # No Commander bracket table exists here: the default leaves no
        # Game Changers target behind, and no such Check runs.
        self.assertNotIn("game_changers", result.stdout)

    def test_stated_power_lands_in_the_suite(self):
        result = self.generate("format: standard\npower: 3\n", slug="standard")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("brief: standard — power 3\n", result.stdout)

    def test_mono_color_identity_words_generate(self):
        # The fixture Standard Brief says identity: mono-red — the natural
        # phrasing must resolve to the single color, not refuse.
        result = self.generate("format: casual 60\nidentity: mono-red\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("color_identity: [R]\n", result.stdout)

    def test_fixture_standard_brief_generates_a_standard_suite(self):
        brief = (FIXTURES / "briefs" / "standard-ember-stampede.txt").read_text(
            encoding="utf-8")
        result = self.generate(brief, slug="standard")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("format: Standard\n", result.stdout)
        self.assertIn("banlist_key: standard\n", result.stdout)
        self.assertIn("- id: legality.banlist\n", result.stdout)


class FourCopyLimitIsAParameter(unittest.TestCase):
    """Acceptance: copy limits are profile data the fixed runner reads —
    the same legality.singleton predicate, parameter 4, honest detail both
    ways. The Format changes; the runner does not."""

    SUITE = mini_suite(["legality.singleton"],
                       profile_lines=["copy_limit_nonland: 4"])
    ORACLE = oracle_json(oracle_card("Raccoon Rallier"))
    COLLECTION = "Name,Quantity\nRaccoon Rallier,8\n"

    def run_copies(self, copies):
        home = TempHome()
        self.addCleanup(home.cleanup)
        deck = f"// Probe\n// Mainboard\n{copies} Raccoon Rallier\n"
        return run_mini(home, self.SUITE, deck_text=deck,
                        oracle_text=self.ORACLE,
                        collection_text=self.COLLECTION)

    def test_a_playset_is_green_with_the_limit_in_the_detail(self):
        result = self.run_copies(4)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green legality.singleton — no nonland above 4 copies",
                      result.stdout)

    def test_a_fifth_copy_is_red_naming_the_card(self):
        result = self.run_copies(5)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("red   legality.singleton — over copy limit: "
                      "Raccoon Rallier", result.stdout)

    def test_limit_one_keeps_the_commander_detail_byte_exact(self):
        home = TempHome()
        self.addCleanup(home.cleanup)
        suite = mini_suite(["legality.singleton"],
                           profile_lines=["copy_limit_nonland: 1"])
        result = run_mini(home, suite,
                          deck_text="// Probe\n// Mainboard\n1 Raccoon Rallier\n",
                          oracle_text=self.ORACLE,
                          collection_text=self.COLLECTION)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("green legality.singleton — no nonland above 1 copy",
                      result.stdout)


CASUAL_BRIEF = FIXTURES / "briefs" / "casual60-kitchen-stampede.txt"
CASUAL_SUITE = FIXTURES / "build" / "kitchen-stampede.built.suite.yaml"
CASUAL_DECK = FIXTURES / "decks" / "kitchen-stampede.txt"
CASUAL_REPORT = FIXTURES / "build" / "kitchen-stampede-built-report.txt"
STANDARD_POOL = FIXTURES / "collections" / "synthetic-standard-pool.csv"
FLAWED_STANDARD_DECK = FIXTURES / "decks" / "ember-stampede-flawed.txt"
REVIEW_FIXTURES = FIXTURES / "review"


class Casual60FixtureBuilds(unittest.TestCase):
    """Acceptance: a Casual 60 fixture builds — the committed Suite is the
    generator's output plus recorded Role tags, and the committed Deck runs
    all green through the unmodified runner, byte-identical to the committed
    report."""

    def test_built_suite_differs_from_fresh_generation_by_roles_only(self):
        result = run_cli(
            GENERATOR, "--brief", CASUAL_BRIEF,
            "--profile", PROFILES / "casual-60.yaml",
            "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
            "--date", REFERENCE_DATE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        without_roles, role_lines, in_roles = [], [], False
        for line in CASUAL_SUITE.read_text(encoding="utf-8").splitlines(True):
            if not line.startswith(" ") and line.strip():
                in_roles = line.rstrip() == "roles:"
            if in_roles and line.startswith("  ") and not line.lstrip().startswith("#"):
                role_lines.append(line)
                continue
            without_roles.append(line)
        self.assertEqual("".join(without_roles), result.stdout,
                         "the built Suite differs beyond its roles: section")
        self.assertTrue(role_lines, "no Role judgment recorded")

    def test_committed_deck_runs_all_green_byte_identical(self):
        result = run_cli(
            RUNNER, "--suite", CASUAL_SUITE, "--deck", CASUAL_DECK,
            "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
            "--collection", STANDARD_POOL,
            "--date", REFERENCE_DATE,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout,
                         CASUAL_REPORT.read_text(encoding="utf-8"))
        self.assertIn("verdict: green — 0 red /", result.stdout)
        self.assertIn("green legality.singleton — no nonland above 4 copies",
                      result.stdout)


class SanctionedLegalityGoesRed(unittest.TestCase):
    """Acceptance: a sanctioned-legality Check goes red on a fixture card
    illegal in that Format — read per card from the Oracle's legalities,
    through the unmodified runner."""

    @classmethod
    def setUpClass(cls):
        cls.home = TempHome()
        result = run_cli(
            GENERATOR,
            "--brief", FIXTURES / "briefs" / "standard-ember-stampede.txt",
            "--profile", PROFILES / "standard.yaml",
            "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
            "--date", REFERENCE_DATE,
            "--out", cls.home.root / "standard.suite.yaml",
        )
        assert result.returncode == 0, result.stderr

    @classmethod
    def tearDownClass(cls):
        cls.home.cleanup()

    def run_standard_suite(self, deck):
        return run_cli(
            RUNNER, "--suite", self.home.root / "standard.suite.yaml",
            "--deck", deck,
            "--oracle", FIXTURES / "scryfall" / "oracle.jsonl",
            "--collection", STANDARD_POOL,
            "--date", REFERENCE_DATE,
        )

    def test_illegal_fixture_card_turns_the_banlist_check_red(self):
        result = self.run_standard_suite(FLAWED_STANDARD_DECK)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("red   legality.banlist — not legal in standard: "
                      "Brotherhood's End (not_legal)", result.stdout)

    def test_the_all_legal_deck_keeps_the_banlist_check_green(self):
        result = self.run_standard_suite(CASUAL_DECK)
        self.assertIn("green legality.banlist — every card legal in standard",
                      result.stdout)


class Casual60FixtureReviews(unittest.TestCase):
    """Acceptance: a Casual 60 fixture reviews — the committed axis Findings
    assemble byte-identical into the committed Review Block through the
    unmodified assembler, Verdicts computed."""

    def test_review_block_reassembles_byte_identical(self):
        result = run_cli(
            ASSEMBLER, "--deck-name", "Kitchen Stampede",
            "--standards", REVIEW_FIXTURES / "kitchen-stampede.standards-findings.json",
            "--brief", REVIEW_FIXTURES / "kitchen-stampede.brief-findings.json",
            "--date", REFERENCE_DATE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        committed = (REVIEW_FIXTURES / "kitchen-stampede.review.txt").read_text(
            encoding="utf-8")
        self.assertEqual(result.stdout, committed)
        self.assertIn("verdict: playable", result.stdout)
        self.assertIn("standards: playable", result.stdout)


if __name__ == "__main__":
    unittest.main()
