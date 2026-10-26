"""
Phase 3A test strategy: the character system may change ONE number — the
festival's initial ask — and nothing else. These tests prove the four spouses
open at differentiated, character-consistent budgets, that the proposal is
consumed by the UNCHANGED negotiation engine, and that FLX (reserved for
Phase 3B) has no effect anywhere.
"""
import unittest

from models.constants import (
    ARCHETYPES, CHARACTER_PROFILES, FESTIVAL_EVENT, MARRIAGE_MONTH,
    MONTHLY_INCOME, POSTURE_SCALE, CHAR_ADJ_MIN, CHAR_ADJ_MAX,
)
from services import festival_service as fs
from services import negotiation_service as ns
from models.negotiation_intents import ACCEPT_PROPOSAL, COUNTER_OFFER


class TestCharacterProfiles(unittest.TestCase):
    def test_all_archetypes_have_profiles_with_exactly_four_traits(self):
        self.assertEqual(set(CHARACTER_PROFILES), set(ARCHETYPES))
        for traits in CHARACTER_PROFILES.values():
            self.assertEqual(set(traits), {"PRU", "STA", "FAM", "FLX"})

    def test_approved_trait_values(self):
        self.assertEqual(CHARACTER_PROFILES["saver"],
                         {"PRU": 70, "STA": 30, "FAM": 85, "FLX": 55})
        self.assertEqual(CHARACTER_PROFILES["earner"],
                         {"PRU": 35, "STA": 90, "FAM": 55, "FLX": 40})
        self.assertEqual(CHARACTER_PROFILES["investor"],
                         {"PRU": 90, "STA": 40, "FAM": 35, "FLX": 65})
        self.assertEqual(CHARACTER_PROFILES["anchor"],
                         {"PRU": 60, "STA": 45, "FAM": 80, "FLX": 50})


class TestCharAdj(unittest.TestCase):
    def test_approved_formula_values(self):
        self.assertAlmostEqual(fs.char_adjustment("saver"), 1.013, places=3)
        self.assertAlmostEqual(fs.char_adjustment("earner"), 1.159, places=3)
        self.assertAlmostEqual(fs.char_adjustment("investor"), 0.861, places=3)
        self.assertAlmostEqual(fs.char_adjustment("anchor"), 1.059, places=3)

    def test_unknown_archetype_is_character_neutral(self):
        self.assertEqual(fs.char_adjustment("nonsense"), 1.0)

    def test_clamped_for_extreme_traits(self):
        CHARACTER_PROFILES["_extreme"] = {"PRU": 0, "STA": 100, "FAM": 100, "FLX": 50}
        try:
            self.assertEqual(fs.char_adjustment("_extreme"), CHAR_ADJ_MAX)
            CHARACTER_PROFILES["_extreme"] = {"PRU": 100, "STA": 0, "FAM": 0, "FLX": 50}
            self.assertEqual(fs.char_adjustment("_extreme"), CHAR_ADJ_MIN)
        finally:
            del CHARACTER_PROFILES["_extreme"]

    def test_flx_has_no_effect_on_char_adj(self):
        """FLX is Phase 3B. If it ever leaks into CharAdj, this fails."""
        original = CHARACTER_PROFILES["saver"]["FLX"]
        baseline = fs.char_adjustment("saver")
        try:
            for flx in (0, 100):
                CHARACTER_PROFILES["saver"]["FLX"] = flx
                self.assertEqual(fs.char_adjustment("saver"), baseline)
        finally:
            CHARACTER_PROFILES["saver"]["FLX"] = original


class TestFestivalAsk(unittest.TestCase):
    def test_ask_matches_formula_dynamically(self):
        """The ask must derive from Monthly Surplus/posture/importance/CharAdj — not a constant."""
        from models.constants import LIFESTYLE_COSTS, SPOUSE_BASE_EXPENSE
        for aid, arch in ARCHETYPES.items():
            hhi = MONTHLY_INCOME + arch["income"]
            mandatory_living = LIFESTYLE_COSTS["city"]["total"] + SPOUSE_BASE_EXPENSE + arch["expense_mod"]
            surplus_mo = max(1000.0, hhi - mandatory_living)
            posture = max(0.85, min(1.20, 1 + arch["expense_mod"] / POSTURE_SCALE))
            raw = (surplus_mo * FESTIVAL_EVENT["base_k"] * posture
                   * FESTIVAL_EVENT["importance"] * fs.char_adjustment(aid))
            self.assertEqual(fs.compute_festival_ask(aid),
                             int(round(raw / 500) * 500), aid)

    def test_function_budget_requires_planning(self):
        for aid in ARCHETYPES:
            self.assertGreaterEqual(fs.compute_festival_ask(aid), 10000)

    def test_four_characters_are_differentiated(self):
        asks = {a: fs.compute_festival_ask(a) for a in ARCHETYPES}
        self.assertEqual(len(set(asks.values())), len(ARCHETYPES))
        # Character-consistent ordering: status-driven Earner highest,
        # prudent Investor lowest.
        self.assertEqual(max(asks, key=asks.get), "earner")
        self.assertEqual(min(asks, key=asks.get), "investor")

    def test_guardrails_relative_to_surplus(self):
        from models.constants import LIFESTYLE_COSTS, SPOUSE_BASE_EXPENSE
        for aid, arch in ARCHETYPES.items():
            hhi = MONTHLY_INCOME + arch["income"]
            mandatory_living = LIFESTYLE_COSTS["city"]["total"] + SPOUSE_BASE_EXPENSE + arch["expense_mod"]
            surplus_mo = max(1000.0, hhi - mandatory_living)
            ask = fs.compute_festival_ask(aid)
            self.assertGreaterEqual(ask, 0.25 * surplus_mo, aid)
            self.assertLessEqual(ask, 2.5 * surplus_mo, aid)


class TestFestivalProposal(unittest.TestCase):
    def test_deterministic_and_idempotent(self):
        a = fs.generate_festival_budget("user-1", FESTIVAL_EVENT["month"], "earner")
        b = fs.generate_festival_budget("user-1", FESTIVAL_EVENT["month"], "earner")
        self.assertEqual(a, b)

    def test_same_shape_as_existing_proposals(self):
        monthly = ns.generate_proposal("user-1", 5, "earner")
        festival = fs.generate_festival_budget("user-1", FESTIVAL_EVENT["month"], "earner")
        self.assertEqual(set(monthly.keys()), set(festival.keys()))
        self.assertEqual(festival["month"], FESTIVAL_EVENT["month"])
        self.assertEqual(festival["kind"], "festival")

    def test_unknown_archetype_returns_none(self):
        self.assertIsNone(fs.generate_festival_budget("u", 6, "single"))


class TestNegotiationEngineUnchanged(unittest.TestCase):
    """The existing engine consumes the festival proposal with zero changes:
    archetype floors, the no-instant-convincing rule and pure-cash effects
    all behave exactly as for any 'lifestyle'-class proposal."""

    def setUp(self):
        self.p = fs.generate_festival_budget("user-1", FESTIVAL_EVENT["month"], "saver")

    def test_accept_full_costs_cash_only(self):
        r = ns.evaluate(ACCEPT_PROPOSAL, {}, self.p, 1, 60, 500000)
        self.assertTrue(r["resolved"])
        self.assertEqual(r["effects"], {"cash": -self.p["ask"]})  # no stocks/ef/expense return

    def test_floor_is_archetype_based_not_character_based(self):
        from models.constants import negotiation_min_ratio
        r = ns.evaluate(COUNTER_OFFER, {"amount": 1000}, self.p, 2, 60, 500000)
        self.assertEqual(r["required_minimum"],
                         round(self.p["ask"] * negotiation_min_ratio("saver", 60), 2))

    def test_no_instant_convincing_still_holds(self):
        r = ns.evaluate(COUNTER_OFFER, {"amount": self.p["ask"] - 500}, self.p, 1, 60, 500000)
        self.assertFalse(r["resolved"])
        self.assertEqual(r["outcome"], "continue")

    def test_festival_month_tracks_marriage_month(self):
        self.assertEqual(FESTIVAL_EVENT["month"], MARRIAGE_MONTH + 1)


if __name__ == "__main__":
    unittest.main()
