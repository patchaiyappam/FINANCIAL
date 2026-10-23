import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tools.strategy_simulation import run, run_investments
from models.constants import SCORE_WEIGHTS


class StrategySimulationTests(unittest.TestCase):
    def test_twelve_month_repeatability_and_unmodified_weights(self):
        first = run()
        self.assertEqual(first, run())
        self.assertEqual(len(first), 6)
        self.assertEqual(SCORE_WEIGHTS, {'net_worth': .4, 'liquidity': .15,
                         'debt_control': .15, 'risk_protection': .15, 'discipline': .15})
        for strategy in first:
            self.assertEqual([s['month'] for s in strategy['history']], list(range(1, 13)))
            for state in strategy['history']:
                self.assertGreaterEqual(state['cash'], -0.02)
                self.assertGreaterEqual(state['financial_health_score'], 0)
                self.assertLessEqual(state['financial_health_score'], 100)
                self.assertAlmostEqual(state['net_worth'], state['cash'] + state['stocks'] + state['gold'] + state['emergency_fund'] - state['loans'], places=1)
        repeated = next(s for s in first if s['strategy'].startswith('F:'))
        self.assertGreater(repeated['auto_loans'], 1)

    def test_investment_strategies_repeat_for_all_twelve_months(self):
        first = run_investments()
        self.assertEqual(first, run_investments())
        self.assertEqual(len(first), 4)
        for strategy in first:
            self.assertEqual([s['month'] for s in strategy['history']], list(range(1, 13)))
            self.assertGreater(strategy['investment_value'], 0)
            for state in strategy['history']:
                self.assertGreaterEqual(state['cash'], -0.02)
                self.assertGreaterEqual(state['financial_health_score'], 0)
                self.assertLessEqual(state['financial_health_score'], 100)


if __name__ == '__main__':
    unittest.main()
