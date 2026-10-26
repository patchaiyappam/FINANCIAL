import unittest
from engine.scoring import calculate_financial_health_score, net_worth_component
from engine.monthly_processor import process_month_for_player, household_expenses
from models.constants import (
    ARCHETYPES, SPOUSE_BASE_EXPENSE, MONTHLY_INCOME, LIFESTYLE_COSTS,
    INITIAL_BUDGET, WEDDING_COST, MARRIAGE_MONTH
)
from engine.market_engine import calculate_inflation_adjustment
from models.constants import SATISFACTION_START, satisfaction_expense_drift


def _net_injection(arch_id):
    a = ARCHETYPES[arch_id]
    return a['stocks'] + a['gold'] + a['ef'] - a['loan']


class TestMarriageSystem(unittest.TestCase):
    def test_spouse_expense_starts_after_marriage_month(self):
        player = {"spouse_archetype": "saver", "lifestyle_type": "city"}
        self.assertEqual(household_expenses(player, MARRIAGE_MONTH)["spouse"], 0)
        self.assertEqual(household_expenses(player, MARRIAGE_MONTH + 1)["spouse"],
                         SPOUSE_BASE_EXPENSE + ARCHETYPES["saver"]["expense_mod"])

    def test_no_spouse_salary_in_marriage_month_score(self):
        args = dict(net_worth=100000, month=MARRIAGE_MONTH,
                    spouse_assets=35000, wedding_cost=WEDDING_COST)
        self.assertEqual(net_worth_component(spouse_income=5000, **args),
                         net_worth_component(spouse_income=16000, **args))

    # ── D-03 regression: net-worth normalization must be archetype-neutral ──
    def test_injected_assets_discount_the_ratio(self):
        # For a FIXED net worth, a spouse who brought more assets must not score
        # HIGHER — the brought assets are resources to grow, not growth. Folding
        # them into the denominator makes a bigger injection score no higher.
        nw, month, income = 250000, 12, 4000
        heavy = net_worth_component(nw, month, income, 55000, WEDDING_COST)
        light = net_worth_component(nw, month, income, 5000, WEDDING_COST)
        self.assertLess(heavy, light)

    def test_capital_preservation_scores_equally_across_archetypes(self):
        # A player who exactly preserves their TOTAL household resources (ratio 1)
        # must get the identical net-worth score no matter which archetype they
        # married. Before D-03 the asset-heavy archetypes scored higher for the
        # same skill because their brought assets were missing from the denominator.
        month = 12
        married_months = month - MARRIAGE_MONTH
        scores = []
        for arch_id, arc in ARCHETYPES.items():
            resources = (INITIAL_BUDGET + MONTHLY_INCOME * (month - 1)
                         + arc['income'] * married_months
                         + _net_injection(arch_id) - WEDDING_COST)
            # net worth == resources ⇒ ratio 1.0 for every archetype
            s = net_worth_component(resources, month, arc['income'],
                                    _net_injection(arch_id), WEDDING_COST)
            scores.append(round(s, 6))
        self.assertEqual(len(set(scores)), 1,
                         f"net-worth score not archetype-neutral at ratio 1: {scores}")

    def test_net_worth_normalization_with_spouse_income(self):
        # Without spouse income
        nw_score_single = net_worth_component(net_worth=100000, month=MARRIAGE_MONTH + 1, spouse_income=0.0)
        
        # With spouse income (e.g. Earner: 36000)
        nw_score_married = net_worth_component(net_worth=100000, month=MARRIAGE_MONTH + 1, spouse_income=36000)
        
        # Since expected resources is higher for married players, they should get a lower score for the SAME net worth
        self.assertTrue(nw_score_married < nw_score_single)

    def test_monthly_processor_adds_spouse_income_and_expenses(self):
        player = {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "month": 6,
            "cash": 10000,
            "stocks": 0,
            "gold": 0,
            "emergency_fund": 0,
            "loans": 0,
            "lifestyle_type": "city",
            "bike_status": False,
            "spouse_archetype": "saver" # Saver has income 10000, expense_mod -9000
        }
        
        result = process_month_for_player(
            player=player,
            month=7,
            admin_events=[],
            active_loans=[],
            pending_sales=[],
            auto_events=False,
            auto_market=False
        )
        
        # Derived from constants rather than hardcoded, so a future rebalance of
        # LIFESTYLE_COSTS updates the expectation instead of silently failing.
        # (This assertion previously hardcoded 79193.98 against a city expense of
        # 40,000; the 2026-07-21 rebalance raised it to 78,000 and broke the test.)
        expense = calculate_inflation_adjustment(LIFESTYLE_COSTS['city']['total'], 7)
        spouse_expense = SPOUSE_BASE_EXPENSE + ARCHETYPES['saver']['expense_mod']
        spouse_income = ARCHETYPES['saver']['income']
        # ADR-014 added a bounded relationship drift to household costs. Derived
        # here rather than hardcoded so a future retune updates the expectation
        # instead of silently failing this test.
        drift = satisfaction_expense_drift(SATISFACTION_START)
        expected = round(10000 + MONTHLY_INCOME + spouse_income
                         - expense - spouse_expense - drift, 2)
        self.assertAlmostEqual(result["ending_cash"], expected, places=2)
        self.assertEqual(result["updated_state"]["spouse_archetype"], "saver")

if __name__ == "__main__":
    unittest.main()
