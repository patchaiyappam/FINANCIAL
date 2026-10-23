"""Investment instruments used by the Money Master 12-month simulation.

All rates are game-balance assumptions, not live rates or financial advice.
Portfolio lots live in player_state.investment_portfolio as JSON so monthly
processing can update market-linked assets and locked products in one batch.
"""
from __future__ import annotations
from copy import deepcopy
import math
from typing import Any

# annual_rate values are illustrative game settings. A game month is one
# simulated month; long-term products remain locked beyond the 12-month round.
INVESTMENT_PRODUCTS: dict[str, dict[str, Any]] = {
    "bank_fd_3m": {
        "name": "Bank Fixed Deposit · 3 months", "kind": "fixed", "annual_rate": 0.064,
        "maturity_months": 3, "early_exit_penalty": 0.02, "risk_weight": 0.03,
        "liquidity": "Matures after 3 game months", "risk": "Low", "fee_text": "2% early-exit penalty",
    },
    "treasury_bill_6m": {
        "name": "Treasury Bill · 6 months", "kind": "fixed", "annual_rate": 0.063,
        "maturity_months": 6, "early_exit_penalty": 0.01, "risk_weight": 0.02,
        "liquidity": "Matures after 6 game months", "risk": "Low", "fee_text": "1% early-exit penalty",
    },
    "liquid_fund": {
        "name": "Liquid Mutual Fund", "kind": "liquid", "annual_rate": 0.054,
        "maturity_months": None, "early_exit_penalty": 0.0, "risk_weight": 0.06,
        "liquidity": "Available any month", "risk": "Low–moderate", "fee_text": "No game exit fee; NAV can fluctuate",
    },
    "arbitrage_fund": {
        "name": "Arbitrage Mutual Fund", "kind": "arbitrage", "annual_rate": 0.057,
        "monthly_fee": 0.0002, "maturity_months": None, "early_exit_penalty": 0.0025,
        "risk_weight": 0.10, "liquidity": "Available any month", "risk": "Low–moderate",
        "fee_text": "Small game fee; 0.25% exit fee during first 3 months",
    },
    "gold_etf": {
        "name": "Gold ETF", "kind": "gold_etf", "maturity_months": None,
        "early_exit_penalty": 0.0, "monthly_fee": 0.0005, "risk_weight": 0.25,
        "liquidity": "Available any month", "risk": "Moderate", "fee_text": "Tracks gold movement less a game fee",
    },
    "business_venture": {
        "name": "Small Business / Resale Venture", "kind": "venture", "maturity_months": 6,
        "early_exit_penalty": 0.05, "monthly_fee": 0.003, "risk_weight": 0.85,
        "liquidity": "6-month target lock; early exit costs 5%", "risk": "Very high",
        "fee_text": "Demand-driven return; 0.3% monthly operating cost; 5% early exit",
    },
    "index_fund": {
        "name": "Nifty 50 Index Fund", "kind": "equity", "market_factor": 1.0,
        "monthly_fee": 0.0004, "maturity_months": None, "early_exit_penalty": 0.01,
        "risk_weight": 1.0, "liquidity": "Available any month", "risk": "High", "fee_text": "0.04% monthly game fee; 1% early exit fee under 3 months",
    },
    "flexi_cap_fund": {
        "name": "Flexi-cap Equity Fund", "kind": "equity", "market_factor": 1.25,
        "monthly_fee": 0.0009, "maturity_months": None, "early_exit_penalty": 0.01,
        "risk_weight": 1.15, "liquidity": "Available any month", "risk": "High", "fee_text": "0.09% monthly game fee; 1% early exit fee under 6 months",
    },
    "balanced_advantage_fund": {
        "name": "Balanced Advantage Fund", "kind": "balanced", "equity_weight": 0.55,
        "gold_weight": 0.15, "debt_weight": 0.30, "monthly_fee": 0.0007,
        "maturity_months": None, "early_exit_penalty": 0.01, "risk_weight": 0.55,
        "liquidity": "Available any month", "risk": "Moderate–high", "fee_text": "0.07% monthly game fee; 1% early exit fee under 3 months",
    },
    "ppf": {
        "name": "Public Provident Fund (PPF)", "kind": "fixed", "annual_rate": 0.071,
        "maturity_months": 180, "early_exit_penalty": None, "risk_weight": 0.02,
        "liquidity": "Locked for the 12-month game; real PPF has a 15-year initial term", "risk": "Low", "fee_text": "No early withdrawal in this game",
    },
    "nps": {
        "name": "National Pension System (NPS)", "kind": "pension", "equity_weight": 0.50,
        "gold_weight": 0.15, "debt_weight": 0.35, "monthly_fee": 0.0005,
        "maturity_months": 361, "early_exit_penalty": None, "risk_weight": 0.58,
        "liquidity": "Locked for the 12-month game; real NPS has retirement exit rules", "risk": "Market-linked", "fee_text": "0.05% monthly game fee; early withdrawal disabled",
    },
}


def empty_portfolio() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in INVESTMENT_PRODUCTS}


def normalize_portfolio(portfolio: Any) -> dict[str, list[dict[str, Any]]]:
    """Return a safe JSON-serialisable portfolio, dropping unknown/malformed lots."""
    result = empty_portfolio()
    if not isinstance(portfolio, dict):
        return result
    for key, lots in portfolio.items():
        if key not in INVESTMENT_PRODUCTS or not isinstance(lots, list):
            continue
        for lot in lots:
            if not isinstance(lot, dict):
                continue
            try:
                value = max(0.0, float(lot.get("value", 0)))
                principal = max(0.0, float(lot.get("principal", value)))
                purchase_month = max(1, int(lot.get("purchase_month", 1)))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value) or not math.isfinite(principal) or value <= 0:
                continue
            try:
                maturity_month = int(lot["maturity_month"]) if lot.get("maturity_month") is not None else None
            except (TypeError, ValueError):
                maturity_month = None
            result[key].append({
                "value": round(value, 2),
                "principal": round(principal, 2),
                "purchase_month": purchase_month,
                "maturity_month": maturity_month,
            })
    return result


def add_investment_lot(portfolio: Any, product_key: str, amount: float, month: int) -> dict:
    if product_key not in INVESTMENT_PRODUCTS:
        raise ValueError(f"Unknown investment product: {product_key}")
    amount = float(amount)
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("Investment amount must be a finite, nonnegative number")
    updated = normalize_portfolio(portfolio)
    if amount <= 0:
        return updated
    definition = INVESTMENT_PRODUCTS[product_key]
    maturity_months = definition.get("maturity_months")
    # PPF/NPS are not treated as maturing in the 12-month game; retaining their
    # full-term metadata communicates the opportunity cost and keeps this model
    # extensible if the simulation horizon is expanded later.
    maturity = int(month) + int(maturity_months) if maturity_months else None
    updated[product_key].append({
        "value": round(amount, 2), "principal": round(amount, 2),
        "purchase_month": int(month), "maturity_month": maturity,
    })
    return updated


def portfolio_value(portfolio: Any) -> float:
    normalized = normalize_portfolio(portfolio)
    return round(sum(lot["value"] for lots in normalized.values() for lot in lots), 2)


def portfolio_equity_exposure(portfolio: Any) -> float:
    """Estimate only direct/embedded equity exposure, not generic product risk."""
    normalized = normalize_portfolio(portfolio)
    total = 0.0
    for key, lots in normalized.items():
        product = INVESTMENT_PRODUCTS[key]
        equity_weight = float(product.get("equity_weight", 1.0 if product["kind"] == "equity" else 0.0))
        total += sum(lot["value"] for lot in lots) * equity_weight
    return round(total, 2)


def portfolio_risk_exposure(portfolio: Any) -> float:
    """Risk-weighted asset exposure used by the game's risk-score heuristic."""
    normalized = normalize_portfolio(portfolio)
    total = 0.0
    for key, lots in normalized.items():
        weight = max(0.0, min(1.0, float(INVESTMENT_PRODUCTS[key].get("risk_weight", 0.0))))
        total += sum(lot["value"] for lot in lots) * weight
    return round(total, 2)


def portfolio_locked_value(portfolio: Any, month: int) -> float:
    normalized = normalize_portfolio(portfolio)
    locked = 0.0
    for key, lots in normalized.items():
        product = INVESTMENT_PRODUCTS[key]
        if key in ("ppf", "nps"):
            locked += sum(lot["value"] for lot in lots)
        elif product.get("maturity_months"):
            locked += sum(lot["value"] for lot in lots if lot.get("maturity_month") and lot["maturity_month"] > month)
    return round(locked, 2)


def _monthly_fixed_rate(annual_rate: float) -> float:
    return (1.0 + float(annual_rate)) ** (1.0 / 12.0) - 1.0


def _monthly_return(product_key: str, scenario: dict) -> float:
    product = INVESTMENT_PRODUCTS[product_key]
    kind = product["kind"]
    stock = float(scenario.get("stock_pct", 0.0))
    gold = float(scenario.get("gold_pct", 0.0))
    debt_rate = _monthly_fixed_rate(0.052)
    if kind == "fixed":
        return _monthly_fixed_rate(float(product["annual_rate"]))
    if kind == "liquid":
        # Near-cash return is stable; it is not treated as a bank deposit.
        # A very small shared fluctuation prevents this instrument from being
        # mistaken for a guaranteed balance.
        return _monthly_fixed_rate(float(product["annual_rate"])) + max(-0.001, min(0.001, stock * 0.01))
    if kind == "arbitrage":
        # An educational approximation of arbitrage-fund behaviour: a modest
        # base return with very small shared stock/gold-spread sensitivity.
        spread = max(-0.0015, min(0.0015, (stock - gold) * 0.015))
        return _monthly_fixed_rate(float(product["annual_rate"])) + spread - float(product["monthly_fee"])
    if kind == "gold_etf":
        return gold - float(product["monthly_fee"])
    if kind == "venture":
        # A shared business-cycle proxy creates a genuine risk/reward dilemma.
        # This is explicitly a game mechanic, not a forecast of real businesses.
        regime = str(scenario.get("regime", "authored"))
        base_by_regime = {
            "war": -0.025, "crash": -0.040, "rate_hike": -0.015,
            "inflation_spike": 0.010, "steady": 0.012, "boom": 0.020,
            "recovery": 0.018, "correction": -0.010, "flat": 0.005,
        }
        base = base_by_regime.get(regime, 0.005 + stock * 0.10 + gold * 0.05)
        return max(-0.20, min(0.12, base + stock * 0.25 - float(product["monthly_fee"])))
    if kind == "equity":
        return stock * float(product["market_factor"]) - float(product["monthly_fee"])
    if kind in ("balanced", "pension"):
        return (stock * float(product.get("equity_weight", 0.0))
                + gold * float(product.get("gold_weight", 0.0))
                + debt_rate * float(product.get("debt_weight", 0.0))
                - float(product.get("monthly_fee", 0.0)))
    return 0.0


def process_investment_portfolio(portfolio: Any, month: int, scenario: dict) -> dict:
    """Grow each lot and transfer matured fixed-term products to cash.

    Returns updated portfolio, maturity cash credit, and player-facing log lines.
    The same resolved market scenario is used for every player in a given month.
    """
    updated = normalize_portfolio(portfolio)
    cash_credit = 0.0
    logs: list[str] = []
    for key in list(updated.keys()):
        kept_lots: list[dict[str, Any]] = []
        for lot in updated[key]:
            rate = _monthly_return(key, scenario)
            old_value = float(lot["value"])
            new_value = max(0.0, old_value * (1.0 + rate))
            lot["value"] = round(new_value, 2)
            delta = lot["value"] - old_value
            if abs(delta) >= 1:
                logs.append(f"📊 {INVESTMENT_PRODUCTS[key]['name']}: {rate*100:+.2f}% (₹{delta:+,.0f})")
            maturity = lot.get("maturity_month")
            # PPF/NPS have long-term game maturity metadata and intentionally do
            # not mature during the standard 12-month event.
            if key not in ("ppf", "nps") and maturity is not None and int(maturity) <= int(month):
                cash_credit += lot["value"]
                logs.append(f"🔓 {INVESTMENT_PRODUCTS[key]['name']} matured: +₹{lot['value']:,.0f} returned to cash")
            else:
                kept_lots.append(lot)
        updated[key] = kept_lots
    return {"portfolio": updated, "cash_credit": round(cash_credit, 2), "logs": logs}


def sell_investment(portfolio: Any, product_key: str, amount: float, month: int) -> dict:
    """Create a post-sale portfolio snapshot using FIFO lots and game exit rules."""
    if product_key not in INVESTMENT_PRODUCTS:
        raise ValueError("Unknown investment product")
    definition = INVESTMENT_PRODUCTS[product_key]
    if definition.get("early_exit_penalty") is None:
        raise ValueError(f"{definition['name']} cannot be withdrawn during the 12-month game")
    amount = float(amount)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Amount must be a finite, positive number")
    updated = normalize_portfolio(portfolio)
    lots = sorted(updated[product_key], key=lambda x: x["purchase_month"])
    available = sum(float(lot["value"]) for lot in lots)
    if amount > available + 0.01:
        raise ValueError(f"Insufficient {definition['name']} balance. Available: ₹{available:,.0f}")
    remaining = min(amount, available)
    proceeds_before_fee = 0.0
    penalty = 0.0
    kept: list[dict[str, Any]] = []
    for lot in lots:
        value = float(lot["value"])
        if remaining <= 0.005:
            kept.append(lot)
            continue
        take = min(value, remaining)
        early = (lot.get("maturity_month") is not None and int(month) < int(lot["maturity_month"]))
        # Equity-fund exit fees apply only for the product-specific initial period.
        hold_months = int(month) - int(lot["purchase_month"])
        if product_key == "index_fund": early = hold_months < 3
        elif product_key == "flexi_cap_fund": early = hold_months < 6
        elif product_key == "balanced_advantage_fund": early = hold_months < 3
        elif product_key == "arbitrage_fund": early = hold_months < 3
        fee_rate = float(definition.get("early_exit_penalty") or 0.0) if early else 0.0
        lot_fee = take * fee_rate
        penalty += lot_fee
        proceeds_before_fee += take
        remaining -= take
        remainder = value - take
        if remainder > 0.005:
            new_lot = dict(lot)
            new_lot["value"] = round(remainder, 2)
            original_principal = float(lot.get("principal", value))
            new_lot["principal"] = round(original_principal * remainder / value, 2) if value > 0 else 0.0
            kept.append(new_lot)
    updated[product_key] = kept
    proceeds = round(max(0.0, proceeds_before_fee - penalty), 2)
    return {"portfolio": updated, "gross_sold": round(proceeds_before_fee, 2),
            "penalty": round(penalty, 2), "cash_proceeds": proceeds}
