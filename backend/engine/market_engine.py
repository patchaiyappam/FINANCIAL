# =============================================================================
# MARKET ENGINE
# Handles stock/gold price fluctuations, volatility calculations
# =============================================================================

import random
import hashlib
from models.constants import (
    STOCK_BASE_GROWTH, GOLD_BASE_GROWTH, EMERGENCY_FUND_GROWTH,
    STOCK_VOLATILITY_MIN, STOCK_VOLATILITY_MAX,
    INFLATION_RATE_PER_MONTH, INFLATION_START_MONTH
)


def _seeded_rng(user_id: str, month: int) -> random.Random:
    """Seeded RNG for per-player-per-month reproducible market calculations."""
    seed = int(hashlib.sha256(f"{user_id}:{month}:market".encode()).hexdigest(), 16)
    return random.Random(seed)


def calculate_investment_growth(player: dict, month: int) -> dict:
    """
    Calculate monthly investment growth with volatility.
    
    Stocks: Base growth + random volatility based on risk
    Gold: Stable growth with minor fluctuation
    Emergency Fund: Small savings interest
    
    Returns updated values and log messages.
    """
    user_id = player.get('user_id', 'unknown')
    rng = _seeded_rng(user_id, month)

    stocks = float(player.get('stocks', 0))
    gold = float(player.get('gold', 0))
    emergency = float(player.get('emergency_fund', 0))
    logs = []

    # ──── STOCKS (Volatile) ────
    if stocks > 0:
        # Base growth + random volatility
        volatility = rng.uniform(STOCK_VOLATILITY_MIN, STOCK_VOLATILITY_MAX)
        stock_growth_rate = STOCK_BASE_GROWTH + volatility
        stock_delta = stocks * stock_growth_rate
        stocks += stock_delta
        stocks = max(0, stocks)
        direction = "📈" if stock_delta >= 0 else "📉"
        logs.append(f"{direction} Stocks: {stock_growth_rate*100:+.1f}% (₹{stock_delta:+,.0f})")

    # ──── GOLD (Stable) ────
    if gold > 0:
        gold_fluctuation = rng.uniform(-0.02, 0.03)  # Small range
        gold_growth_rate = GOLD_BASE_GROWTH + gold_fluctuation
        gold_delta = gold * gold_growth_rate
        gold += gold_delta
        gold = max(0, gold)
        logs.append(f"🥇 Gold: {gold_growth_rate*100:+.1f}% (₹{gold_delta:+,.0f})")

    # ──── EMERGENCY FUND (Savings Interest) ────
    if emergency > 0:
        ef_delta = emergency * EMERGENCY_FUND_GROWTH
        emergency += ef_delta
        logs.append(f"🏦 Emergency Fund Interest: +₹{ef_delta:,.0f}")

    return {
        "stocks": round(stocks, 2),
        "gold": round(gold, 2),
        "emergency_fund": round(emergency, 2),
        "logs": logs
    }


def calculate_inflation_adjustment(base_expense: float, month: int) -> float:
    """
    Apply inflation to monthly expenses starting from INFLATION_START_MONTH.
    Returns the inflated expense amount.
    """
    if month < INFLATION_START_MONTH:
        return base_expense
    
    months_of_inflation = month - INFLATION_START_MONTH + 1
    inflation_multiplier = (1 + INFLATION_RATE_PER_MONTH) ** months_of_inflation
    return round(base_expense * inflation_multiplier, 2)


def calculate_net_worth(cash: float, stocks: float, gold: float,
                         emergency_fund: float, loans: float) -> float:
    """Calculate total net worth = assets - liabilities."""
    return round(cash + stocks + gold + emergency_fund - loans, 2)


def calculate_risk_score(player: dict) -> int:
    """
    Calculate a 0-100 risk score based on portfolio composition.
    Higher = riskier.
    """
    total_assets = (
        float(player.get('cash', 0)) +
        float(player.get('stocks', 0)) +
        float(player.get('gold', 0)) +
        float(player.get('emergency_fund', 0))
    )
    if total_assets <= 0:
        return 100  # Maximum risk if no assets

    stock_ratio = float(player.get('stocks', 0)) / total_assets
    emergency_ratio = float(player.get('emergency_fund', 0)) / total_assets
    loan_ratio = float(player.get('loans', 0)) / max(total_assets, 1)

    # Higher stock ratio = higher risk
    risk = int(stock_ratio * 60)
    # Low emergency fund = higher risk
    risk += int((1 - min(emergency_ratio * 5, 1)) * 20)
    # Loans increase risk
    risk += int(min(loan_ratio * 20, 20))

    return min(100, max(0, risk))
