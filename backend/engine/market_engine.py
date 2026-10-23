# =============================================================================
# MARKET ENGINE
# Handles stock/gold price fluctuations, volatility calculations
# =============================================================================

import random
import hashlib
from engine.investment_engine import portfolio_value, portfolio_risk_exposure
from models.constants import (
    STOCK_BASE_GROWTH, GOLD_BASE_GROWTH, EMERGENCY_FUND_GROWTH,
    STOCK_VOLATILITY_MIN, STOCK_VOLATILITY_MAX,
    INFLATION_RATE_PER_MONTH, INFLATION_START_MONTH,
    MARKET_REGIMES, POST_SHOCK_REGIMES, SHOCK_REGIMES
)


def _seeded_rng(month: int) -> random.Random:
    """
    Seeded RNG for the GLOBAL market path (ADR-009).

    Markets are shared reality: every player faces the identical stock/gold
    returns in the same month. Seeding by month only (not user_id) guarantees
    fairness on the ranked leaderboard — skill is how you position against
    the market, not which market you were dealt.
    """
    seed = int(hashlib.sha256(f"GLOBAL:{month}:market".encode()).hexdigest(), 16)
    return random.Random(seed)


def _regime_rng(month: int) -> random.Random:
    """Separate seeded stream for regime SELECTION, so changing the magnitude
    draw never reshuffles which regime a month gets."""
    seed = int(hashlib.sha256(f"GLOBAL:{month}:regime".encode()).hexdigest(), 16)
    return random.Random(seed)


def _pick_regime(month: int, prev_regime: str | None) -> str:
    """
    Weighted pick of a market regime for `month`. If the previous month was a
    shock (war/crash), the pick is restricted to POST_SHOCK_REGIMES so the market
    has memory — a crash is followed by a recovery or a drift, not by a second
    independent crash. Without this the auto market is a memoryless coin flip and
    players correctly learn that reading it is pointless.
    """
    rng = _regime_rng(month)
    if prev_regime in SHOCK_REGIMES:
        pool = POST_SHOCK_REGIMES
    else:
        pool = list(MARKET_REGIMES.keys())
    weights = [MARKET_REGIMES[k]["weight"] for k in pool]
    return rng.choices(pool, weights=weights, k=1)[0]


def _regime_chain(month: int) -> str:
    """
    Deterministically walk regimes from month 1 to `month` and return the regime
    for `month`. Deterministic and player-independent (ADR-009): every player in a
    given month faces the identical regime, so the leaderboard measures how you
    positioned against the market, never which market you were dealt.
    """
    prev = None
    for m in range(1, month + 1):
        prev = _pick_regime(m, prev)
    return prev


def resolve_market_scenario(month: int, authored: dict | None = None,
                            auto_market: bool = True) -> dict:
    """
    Resolve THE scenario for a month. Single source of truth for how stocks and
    gold move, and why.

    Precedence:
      1. `authored` — an admin-written row from public.market_scenarios. Always wins.
      2. auto_market=True — a correlated regime generated from the seeded chain.
      3. auto_market=False and nothing authored — flat month, prices hold.

    Returns: {name, reason, stock_pct, gold_pct, source, regime}
    """
    if authored:
        return {
            "name": authored.get("name") or "Market Update",
            "reason": authored.get("reason") or "",
            "stock_pct": float(authored.get("stock_pct") or 0.0),
            "gold_pct": float(authored.get("gold_pct") or 0.0),
            "source": "admin",
            "regime": authored.get("regime") or "authored"
        }

    if not auto_market:
        return {
            "name": "Quiet Market",
            "reason": "No significant market movement this month.",
            "stock_pct": 0.0,
            "gold_pct": 0.0,
            "source": "flat",
            "regime": "flat"
        }

    regime_key = _regime_chain(month)
    regime = MARKET_REGIMES[regime_key]
    rng = _seeded_rng(month)
    # Draw both magnitudes unconditionally, stocks first then gold, so the shared
    # per-month stream advances identically for every player (ADR-009 / QA-014).
    stock_pct = rng.uniform(*regime["stock"])
    gold_pct = rng.uniform(*regime["gold"])
    # Base drift on top of the regime move, damped so the regime dominates.
    stock_pct += STOCK_BASE_GROWTH
    gold_pct += GOLD_BASE_GROWTH
    return {
        "name": regime["name"],
        "reason": regime["reason"],
        "stock_pct": round(stock_pct, 4),
        "gold_pct": round(gold_pct, 4),
        "source": "auto",
        "regime": regime_key
    }


def calculate_investment_growth(player: dict, month: int, auto_market: bool = True,
                                scenario: dict | None = None) -> dict:
    """
    Apply the month's market scenario to a player's holdings.

    Stocks and gold move TOGETHER according to one resolved scenario, with a stated
    cause, rather than from two independent RNG draws. `scenario` may be passed in
    (already resolved by the caller, e.g. from an admin-authored row); if omitted it
    is resolved here.
    """
    if scenario is None:
        scenario = resolve_market_scenario(month, None, auto_market)

    stocks = float(player.get('stocks', 0))
    gold = float(player.get('gold', 0))
    emergency = float(player.get('emergency_fund', 0))
    logs = []

    stock_rate = scenario['stock_pct']
    gold_rate = scenario['gold_pct']

    # ──── MARKET HEADLINE ────
    if scenario['source'] != 'flat':
        logs.append(f"📰 {scenario['name']} — {scenario['reason']}")
        logs.append(
            f"   Market this month: Stocks {stock_rate*100:+.1f}% | Gold {gold_rate*100:+.1f}%"
        )

    # ──── STOCKS ────
    if stocks > 0 and stock_rate != 0:
        stock_delta = stocks * stock_rate
        stocks = max(0, stocks + stock_delta)
        direction = "📈" if stock_delta >= 0 else "📉"
        logs.append(f"{direction} Your stocks: {stock_rate*100:+.1f}% (₹{stock_delta:+,.0f})")

    # ──── GOLD ────
    if gold > 0 and gold_rate != 0:
        gold_delta = gold * gold_rate
        gold = max(0, gold + gold_delta)
        direction = "📈" if gold_delta >= 0 else "📉"
        logs.append(f"{direction} Your gold: {gold_rate*100:+.1f}% (₹{gold_delta:+,.0f})")

    # ──── EMERGENCY FUND (savings interest — unaffected by market) ────
    if emergency > 0:
        ef_delta = emergency * EMERGENCY_FUND_GROWTH
        emergency += ef_delta
        logs.append(f"🏦 Emergency Fund Interest: +₹{ef_delta:,.0f}")

    return {
        "stocks": round(stocks, 2),
        "gold": round(gold, 2),
        "emergency_fund": round(emergency, 2),
        "scenario": scenario,
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
                         emergency_fund: float, loans: float,
                         investment_portfolio: dict | None = None) -> float:
    """Calculate net worth = liquid assets + market assets + investment portfolio - debt."""
    return round(cash + stocks + gold + emergency_fund + portfolio_value(investment_portfolio) - loans, 2)


def calculate_risk_score(player: dict) -> int:
    """
    Calculate a 0-100 risk score based on portfolio composition.
    Higher = riskier.
    """
    portfolio = player.get('investment_portfolio') or {}
    portfolio_total = portfolio_value(portfolio)
    risk_exposure = portfolio_risk_exposure(portfolio)
    total_assets = (
        float(player.get('cash', 0)) +
        float(player.get('stocks', 0)) +
        float(player.get('gold', 0)) +
        float(player.get('emergency_fund', 0)) + portfolio_total
    )
    if total_assets <= 0:
        return 100  # Maximum risk if no assets

    stock_ratio = (float(player.get('stocks', 0)) + risk_exposure) / total_assets
    emergency_ratio = float(player.get('emergency_fund', 0)) / total_assets
    loan_ratio = float(player.get('loans', 0)) / max(total_assets, 1)

    # Higher risky-asset exposure = higher risk. Product risk weights are game heuristics.
    risk = int(stock_ratio * 60)
    # Low emergency fund = higher risk
    risk += int((1 - min(emergency_ratio * 5, 1)) * 20)
    # Loans increase risk
    risk += int(min(loan_ratio * 20, 20))

    return min(100, max(0, risk))
