import unittest
from engine.investment_engine import (
    INVESTMENT_PRODUCTS, add_investment_lot, empty_portfolio,
    portfolio_value, process_investment_portfolio, sell_investment,
    portfolio_risk_exposure,
)
from engine.market_engine import calculate_net_worth, calculate_risk_score


class InvestmentEngineTests(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "name": "Recovery", "reason": "Broad recovery", "stock_pct": 0.06,
            "gold_pct": -0.01, "source": "auto", "regime": "recovery",
        }

    def test_lots_are_valued_and_malformed_rows_are_ignored(self):
        portfolio = add_investment_lot(empty_portfolio(), "index_fund", 10000, 1)
        self.assertEqual(portfolio_value(portfolio), 10000)
        portfolio["unknown"] = [{"value": 100000}]
        portfolio["ppf"].append({"value": "broken", "purchase_month": 1})
        self.assertEqual(portfolio_value(portfolio), 10000)

    def test_fixed_deposit_matures_back_to_cash_after_three_returns(self):
        portfolio = add_investment_lot(empty_portfolio(), "bank_fd_3m", 10000, 1)
        month2 = process_investment_portfolio(portfolio, 2, self.scenario)
        self.assertEqual(month2["cash_credit"], 0)
        self.assertAlmostEqual(portfolio_value(month2["portfolio"]), 10000 * (1 + (1.064 ** (1 / 12) - 1)), places=2)
        month3 = process_investment_portfolio(month2["portfolio"], 3, self.scenario)
        month4 = process_investment_portfolio(month3["portfolio"], 4, self.scenario)
        self.assertGreater(month4["cash_credit"], 10000)
        self.assertAlmostEqual(portfolio_value(month4["portfolio"]), 0, places=2)

    def test_index_fund_uses_shared_market_scenario_less_fee(self):
        portfolio = add_investment_lot(empty_portfolio(), "index_fund", 10000, 1)
        moved = process_investment_portfolio(portfolio, 2, self.scenario)
        self.assertAlmostEqual(portfolio_value(moved["portfolio"]), 10000 * (1 + 0.06 - 0.0004), places=2)

    def test_arbitrage_and_gold_etf_use_separate_shared_market_behaviour(self):
        portfolio = empty_portfolio()
        portfolio = add_investment_lot(portfolio, "arbitrage_fund", 10000, 1)
        portfolio = add_investment_lot(portfolio, "gold_etf", 10000, 1)
        moved = process_investment_portfolio(portfolio, 2, self.scenario)
        arb_value = moved["portfolio"]["arbitrage_fund"][0]["value"]
        gold_value = moved["portfolio"]["gold_etf"][0]["value"]
        self.assertGreater(arb_value, 10000)
        self.assertAlmostEqual(gold_value, 10000 * (1 - 0.01 - 0.0005), places=2)

    def test_business_venture_has_downside_and_maturity_tradeoff(self):
        portfolio = add_investment_lot(empty_portfolio(), "business_venture", 10000, 1)
        crash = {**self.scenario, "regime": "crash", "stock_pct": -0.20, "gold_pct": 0.08}
        moved = process_investment_portfolio(portfolio, 2, crash)
        self.assertLess(moved["portfolio"]["business_venture"][0]["value"], 10000)
        self.assertGreater(portfolio_risk_exposure(portfolio), 8000)
        self.assertEqual(moved["cash_credit"], 0)
        sold = sell_investment(portfolio, "business_venture", 1000, 2)
        self.assertAlmostEqual(sold["penalty"], 50)

    def test_risk_exposure_does_not_misclassify_fixed_products_as_equity(self):
        fd = add_investment_lot(empty_portfolio(), "bank_fd_3m", 10000, 1)
        self.assertAlmostEqual(portfolio_risk_exposure(fd), 300)
        equity = add_investment_lot(empty_portfolio(), "index_fund", 10000, 1)
        self.assertAlmostEqual(portfolio_risk_exposure(equity), 10000)

    def test_ppf_cannot_be_withdrawn_during_game(self):
        portfolio = add_investment_lot(empty_portfolio(), "ppf", 5000, 1)
        with self.assertRaisesRegex(ValueError, "cannot be withdrawn"):
            sell_investment(portfolio, "ppf", 1000, 2)

    def test_retirement_assets_remain_locked_after_month_twelve(self):
        portfolio = empty_portfolio()
        portfolio = add_investment_lot(portfolio, "ppf", 5000, 1)
        portfolio = add_investment_lot(portfolio, "nps", 5000, 1)
        for month in range(2, 13):
            portfolio = process_investment_portfolio(portfolio, month, self.scenario)["portfolio"]
        self.assertGreater(portfolio_value(portfolio), 10000)
        self.assertGreater(portfolio["ppf"][0]["value"], 5000)
        self.assertGreater(portfolio["nps"][0]["value"], 5000)
        self.assertGreater(portfolio["ppf"][0]["maturity_month"], 12)
        self.assertGreater(portfolio["nps"][0]["maturity_month"], 12)

    def test_non_finite_lots_and_sales_are_rejected_or_ignored(self):
        portfolio = add_investment_lot(empty_portfolio(), "index_fund", 10000, 1)
        with self.assertRaisesRegex(ValueError, "finite"):
            add_investment_lot(portfolio, "index_fund", float("inf"), 2)
        with self.assertRaisesRegex(ValueError, "finite"):
            sell_investment(portfolio, "index_fund", float("nan"), 2)

    def test_partial_sale_applies_fee_and_reduces_principal_proportionally(self):
        portfolio = add_investment_lot(empty_portfolio(), "index_fund", 10000, 1)
        sold = sell_investment(portfolio, "index_fund", 4000, 2)
        self.assertAlmostEqual(sold["gross_sold"], 4000)
        self.assertAlmostEqual(sold["penalty"], 40)
        self.assertAlmostEqual(sold["cash_proceeds"], 3960)
        remaining = sold["portfolio"]["index_fund"][0]
        self.assertAlmostEqual(remaining["value"], 6000)
        self.assertAlmostEqual(remaining["principal"], 6000)

    def test_net_worth_and_risk_include_other_investments(self):
        portfolio = add_investment_lot(empty_portfolio(), "flexi_cap_fund", 30000, 1)
        worth = calculate_net_worth(10000, 0, 0, 5000, 2000, portfolio)
        self.assertAlmostEqual(worth, 43000)
        risk = calculate_risk_score({
            "cash": 10000, "stocks": 0, "gold": 0, "emergency_fund": 5000,
            "loans": 2000, "investment_portfolio": portfolio,
        })
        self.assertGreater(risk, calculate_risk_score({
            "cash": 10000, "stocks": 0, "gold": 0, "emergency_fund": 5000,
            "loans": 2000,
        }))


if __name__ == "__main__":
    unittest.main()
