# =============================================================================
# SCORING ENGINE (ADR-008)
# Composite Financial Health Score — the leaderboard ranking metric.
#
# Pure deterministic functions (ADR-007): no I/O, no randomness, no LLM.
# Identical inputs always produce identical scores.
# The formula is PUBLIC to players (ADR-000: player trust).
# =============================================================================

from models.constants import (
    SCORE_WEIGHTS, NW_NORMALIZATION_CAP, LIQUIDITY_TARGET_MONTHS,
    MONTHLY_INCOME, INITIAL_BUDGET, MARRIAGE_MONTH
)
from engine.investment_engine import portfolio_value


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def spouse_score_inputs(spouse_arch_id) -> tuple:
    """
    The three spouse-derived scoring inputs — (income, net asset injection,
    wedding cost) — for a married player, or (0, 0, 0) for single/unmarried.

    D-09: one source of truth for these inputs so EVERY scorer caller (monthly
    processor, marriage, admin correction) supplies the SAME contract. Previously
    the admin-correction path passed only spouse_income, so a corrected married
    player scored on the pre-D-03 normalization until the next month reprocessed.
    """
    from models.constants import ARCHETYPES, WEDDING_COST
    if spouse_arch_id and spouse_arch_id != 'single':
        arc = ARCHETYPES.get(spouse_arch_id)
        if arc:
            return (float(arc['income']),
                    float(arc['stocks'] + arc['gold'] + arc['ef'] - arc['loan']),
                    float(WEDDING_COST))
    return 0.0, 0.0, 0.0


def score_player_snapshot(player: dict) -> dict:
    """Refresh final standings after the last round's player actions."""
    from engine.market_engine import calculate_risk_score
    from engine.monthly_processor import household_expenses
    amounts = {key: float(player.get(key) or 0)
               for key in ('cash', 'stocks', 'gold', 'emergency_fund', 'loans')}
    portfolio = player.get('investment_portfolio') or {}
    portfolio_assets = portfolio_value(portfolio)
    assets = sum(amounts[key] for key in ('cash', 'stocks', 'gold', 'emergency_fund')) + portfolio_assets
    worth = assets - amounts['loans']
    risk = calculate_risk_score({**amounts, 'investment_portfolio': portfolio})
    month = int(player['month'])
    expense = household_expenses(player, month)['current']
    income, injected, wedding = spouse_score_inputs(player.get('spouse_archetype'))
    result = calculate_financial_health_score(
        net_worth=worth, month=month, emergency_fund=amounts['emergency_fund'],
        monthly_expense=expense, loans=amounts['loans'], total_assets=assets,
        risk_score=risk, discipline_avg=float(player.get('discipline_score', 100)),
        spouse_income=income, spouse_assets=injected, wedding_cost=wedding)
    return {'net_worth': round(worth, 2), 'risk_level': risk,
            'financial_health_score': result['score']}


def net_worth_component(net_worth: float, month: int, spouse_income: float = 0.0,
                        spouse_assets: float = 0.0, wedding_cost: float = 0.0) -> float:
    """
    Net worth normalized against the total resources the household actually had
    to work with, so the component measures how well those resources were GROWN —
    archetype-neutral by construction (ADR-000 fairness).

    Resources = initial budget + salaries + [ if married: spouse salaries
                + spouse's one-time net asset injection (brought stocks/gold/EF
                  net of any brought loan) − the wedding cost ].

    D-03 fix: previously only spouse INCOME entered the denominator. A spouse's
    brought ASSETS landed in the numerator (net worth) but not the denominator,
    so marrying an asset-heavy archetype (e.g. the Investor) inflated this score
    and an income-heavy one (the Earner) deflated it — for the same skill. Folding
    the injection − wedding into the denominator removes that bias.
    Capped at NW_NORMALIZATION_CAP so extreme leverage cannot dominate. 0-100.
    """
    expected_resources = INITIAL_BUDGET + MONTHLY_INCOME * max(month - 1, 0)
    # The one-time injection applies at marriage; salary starts next month.
    if month >= MARRIAGE_MONTH and spouse_income > 0:
        expected_resources += spouse_income * (month - MARRIAGE_MONTH)
        expected_resources += spouse_assets - wedding_cost
    if expected_resources <= 0:
        return 0.0
    ratio = max(net_worth, 0) / expected_resources
    return _clamp(ratio / NW_NORMALIZATION_CAP * 100)


def liquidity_component(emergency_fund: float, monthly_expense: float) -> float:
    """Months of expenses the emergency fund covers, vs. the target. 0-100."""
    if monthly_expense <= 0:
        return 100.0
    months_covered = emergency_fund / monthly_expense
    return _clamp(months_covered / LIQUIDITY_TARGET_MONTHS * 100)


def debt_control_component(loans: float, total_assets: float) -> float:
    """100 with no debt; falls as debt approaches/exceeds total assets. 0-100."""
    if loans <= 0:
        return 100.0
    if total_assets <= 0:
        return 0.0
    return _clamp((1 - loans / total_assets) * 100)


def risk_protection_component(risk_score: int) -> float:
    """Inverse of the 0-100 portfolio risk score."""
    return _clamp(100 - risk_score)


def calculate_financial_health_score(net_worth: float, month: int,
                                     emergency_fund: float, monthly_expense: float,
                                     loans: float, total_assets: float,
                                     risk_score: int, discipline_avg: float,
                                     spouse_income: float = 0.0,
                                     spouse_assets: float = 0.0,
                                     wedding_cost: float = 0.0) -> dict:
    """
    Composite Financial Health Score per ADR-008.
    Returns the composite and every component so the breakdown can be
    shown to players (public formula).
    """
    components = {
        "net_worth": round(net_worth_component(net_worth, month, spouse_income,
                                               spouse_assets, wedding_cost), 1),
        "liquidity": round(liquidity_component(emergency_fund, monthly_expense), 1),
        "debt_control": round(debt_control_component(loans, total_assets), 1),
        "risk_protection": round(risk_protection_component(risk_score), 1),
        "discipline": round(_clamp(discipline_avg), 1),
    }
    composite = sum(components[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)
    return {"score": round(composite, 2), "components": components}



def update_discipline_average(previous_avg: float, month: int, month_grade: float) -> float:
    """
    Running average of monthly discipline grades over months 1..month.
    Month 1 (allocation month) counts as clean; previous_avg starts at 100.
    Deterministic and order-independent given the same grade sequence.
    """
    m = max(month, 1)
    return round((previous_avg * (m - 1) + month_grade) / m, 2)
