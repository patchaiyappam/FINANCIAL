# =============================================================================
# MONTHLY PROCESSOR
# Core engine that processes each month:
#   1. Income → 2. Expenses → 3. Investments → 4. Events → 5. Loans → 6. Safety net
# =============================================================================

from models.constants import (
    MONTHLY_INCOME, LIFESTYLE_COSTS, BIKE_EMI,
    LOAN_INTEREST_RATE, AUTO_LOAN_INTEREST_RATE, LOAN_TERM_MONTHS,
    INFLATION_RATE_PER_MONTH, INFLATION_START_MONTH,
    ARCHETYPES, SPOUSE_BASE_EXPENSE, INSURANCE_PLANS, INSURABLE_CATEGORIES,
    SATISFACTION_START, satisfaction_expense_drift, MARRIAGE_MONTH
)


def _amortized_emi(principal: float, rate: float, term_months: int) -> float:
    """
    Fixed monthly payment that fully repays `principal` over `term_months`
    at monthly interest `rate` (standard amortization formula).
    Because it depends only on the loan's fixed principal/rate/term, it is the
    same every month and is guaranteed to be larger than the monthly interest,
    so the balance always shrinks to zero. This replaces the old flat EMI
    (fraction of principal) which was smaller than the interest and made loans
    grow forever.
    """
    if principal <= 0 or term_months <= 0:
        return 0.0
    if rate <= 0:
        return principal / term_months
    factor = (1 + rate) ** term_months
    return principal * rate * factor / (factor - 1)
from models.constants import (
    DISCIPLINE_CLEAN_MONTH, DISCIPLINE_EF_RESCUE, DISCIPLINE_AUTO_LOAN
)
from engine.event_engine import generate_events_for_player, apply_event_to_state
from engine.market_engine import (
    calculate_investment_growth, calculate_inflation_adjustment,
    calculate_net_worth, calculate_risk_score
)
from engine.investment_engine import process_investment_portfolio, portfolio_value
from engine.scoring import (
    calculate_financial_health_score, update_discipline_average, spouse_score_inputs
)


def household_expenses(player: dict, month: int) -> dict:
    """Current recurring living costs, shared with the dashboard."""
    living = LIFESTYLE_COSTS.get(player.get('lifestyle_type'), LIFESTYLE_COSTS['city'])
    base = living['total']
    inflated = calculate_inflation_adjustment(base, month)
    bike_saving = living['transport'] * 0.5 if player.get('bike_status') else 0
    arc = ARCHETYPES.get(player.get('spouse_archetype')) if month > MARRIAGE_MONTH else None
    spouse = SPOUSE_BASE_EXPENSE + arc['expense_mod'] if arc else 0
    satisfaction = player.get('spouse_satisfaction', SATISFACTION_START)
    satisfaction = SATISFACTION_START if satisfaction is None else float(satisfaction)
    drift = satisfaction_expense_drift(satisfaction) if arc else 0
    modifier = float(player.get('household_expense_modifier') or 0)
    return {'base': base, 'inflation': inflated - base, 'bike_saving': bike_saving,
            'adjusted_living': inflated - bike_saving, 'spouse': spouse,
            'relationship': drift, 'household_modifier': modifier,
            'current': inflated - bike_saving + spouse + drift + modifier}


def process_month_for_player(player: dict, month: int,
                              admin_events: list = None,
                              active_loans: list = None,
                              pending_sales: list = None,
                              auto_events: bool = True,
                              auto_market: bool = True,
                              market_scenario: dict = None) -> dict:
    """
    Process a single month for a single player.
    
    This is the CORE GAME LOOP executed on the backend.
    
    Returns:
        {
            "updated_state": dict,
            "loan_updates": list,
            "new_loans": list,
            "event_log": list[str],
            "events_triggered": list[dict],
            "starting_cash": float,
            "ending_cash": float,
            "net_worth": float
        }
    """
    uid = player['user_id']
    cash = float(player.get('cash', 0))
    stocks = float(player.get('stocks', 0))
    gold = float(player.get('gold', 0))
    emergency_fund = float(player.get('emergency_fund', 0))
    investment_portfolio = player.get('investment_portfolio') or {}
    trust_score = float(player.get('trust_score', 0) or 0)
    risk_level = int(player.get('risk_level', 50) or 50)
    lifestyle = player.get('lifestyle_type', 'city')
    bike_status = player.get('bike_status', False)
    bike_lock = int(player.get('bike_lock_in_months', 0) or 0)

    event_log = [f"═══ Month {month} Report ═══"]
    events_triggered = []
    loan_updates = []
    new_loans = []

    # ════════════════════════════════════════════
    # STEP 0: CREDIT PENDING ASSET SALES
    # Engine owns this — not the route
    # ════════════════════════════════════════════
    if pending_sales:
        for sale in pending_sales:
            credit = float(sale['cash_to_receive'])
            cash += credit
            event_log.append(
                f"💵 Sale credit ({sale['asset_type']}): +₹{credit:,.0f}"
            )

    starting_cash = cash

    # ════════════════════════════════════════════
    # STEP 1: ADD MONTHLY INCOME
    # ════════════════════════════════════════════
    spouse_income = 0
    spouse_arch_id = player.get('spouse_archetype')
    if spouse_arch_id and spouse_arch_id != 'single':
        arc = ARCHETYPES.get(spouse_arch_id)
        if arc:
            spouse_income = arc['income']

    cash += MONTHLY_INCOME + spouse_income
    if spouse_income > 0:
        event_log.append(f"💰 Salary received: +₹{MONTHLY_INCOME:,} (Spouse: +₹{spouse_income:,})")
    else:
        event_log.append(f"💰 Salary received: +₹{MONTHLY_INCOME:,}")

    # ════════════════════════════════════════════
    # STEP 2: DEDUCT LIFESTYLE EXPENSES (with inflation)
    # ════════════════════════════════════════════
    expense_details = household_expenses(player, month)
    adjusted_expense = expense_details['adjusted_living']
    
    # Bike discount on transport
    if bike_status:
        transport_base = LIFESTYLE_COSTS.get(lifestyle, LIFESTYLE_COSTS['city'])['transport']
        transport_saving = transport_base * 0.5
        event_log.append(f"🏍️ Bike saves ₹{transport_saving:,.0f} on transport")

    spouse_expense = 0
    if spouse_arch_id and spouse_arch_id != 'single':
        arc = ARCHETYPES.get(spouse_arch_id)
        if arc:
            spouse_expense = SPOUSE_BASE_EXPENSE + arc['expense_mod']

    # ── ADR-014: relationship + permanent household modifiers ──
    # satisfaction drift is bounded to +/-Rs3,000; the modifier is whatever the
    # player has permanently negotiated (e.g. the Saver's budget restructure).
    satisfaction = player.get('spouse_satisfaction', SATISFACTION_START)
    satisfaction = SATISFACTION_START if satisfaction is None else float(satisfaction)
    relationship_drift = 0.0
    if spouse_arch_id and spouse_arch_id != 'single':
        relationship_drift = satisfaction_expense_drift(satisfaction)
        if abs(relationship_drift) >= 1:
            mood = "tense" if relationship_drift > 0 else "settled"
            event_log.append(
                f"💞 Household is {mood} (satisfaction {satisfaction:.0f}/100): "
                f"{relationship_drift:+,.0f} to monthly costs"
            )
    permanent_mod = float(player.get('household_expense_modifier', 0) or 0)
    if abs(permanent_mod) >= 1:
        event_log.append(f"📉 Negotiated household savings: {permanent_mod:+,.0f}/month")

    total_expense = expense_details['current']
    cash -= total_expense
    
    exp_desc = f"₹{adjusted_expense:,.0f}"
    if month >= INFLATION_START_MONTH:
        exp_desc += " (inflation-adjusted)"
        
    if spouse_expense > 0:
        event_log.append(f"🏠 Living expenses: -{exp_desc} (Spouse expenses: -₹{spouse_expense:,.0f})")
    else:
        event_log.append(f"🏠 Living expenses: -{exp_desc}")

    # ════════════════════════════════════════════
    # STEP 2b: INSURANCE PREMIUM
    # A guaranteed small monthly loss bought against an uncertain large one.
    # ════════════════════════════════════════════
    plan_id = player.get('insurance_plan') or 'none'
    plan = INSURANCE_PLANS.get(plan_id, INSURANCE_PLANS['none'])
    if plan['premium'] > 0:
        cash -= plan['premium']
        event_log.append(f"🛡️ Insurance premium ({plan['name']}): -₹{plan['premium']:,}")

    # ════════════════════════════════════════════
    # STEP 3: PENDING ASSET SALE CREDITS
    # (Already credited in STEP 0 above — the route passes pending_sales to the
    #  engine, which applies them before salary/expenses. This header is kept
    #  only to preserve the documented step numbering.)
    # ════════════════════════════════════════════

    # ════════════════════════════════════════════
    # STEP 4: INVESTMENT GROWTH
    # ════════════════════════════════════════════
    # The scenario is resolved ONCE per month by the caller and passed to every
    # player, so all players provably experience the identical market (ADR-009).
    growth = calculate_investment_growth(player, month, auto_market, market_scenario)
    stocks = growth['stocks']
    gold = growth['gold']
    emergency_fund = growth['emergency_fund']
    for g_log in growth['logs']:
        event_log.append(g_log)

    # New investment instruments use the SAME market scenario for every player.
    # Locked products mature back into cash; otherwise they remain in the portfolio.
    portfolio_growth = process_investment_portfolio(
        investment_portfolio, month, growth['scenario']
    )
    investment_portfolio = portfolio_growth['portfolio']
    if portfolio_growth['cash_credit']:
        cash += portfolio_growth['cash_credit']
    event_log.extend(portfolio_growth['logs'])

    # ════════════════════════════════════════════
    # STEP 5: DYNAMIC EVENTS
    # ════════════════════════════════════════════
    # Build a temporary player state for event generation with current trust
    temp_player = {**player, 'cash': cash, 'stocks': stocks, 'gold': gold,
                   'emergency_fund': emergency_fund, 'investment_portfolio': investment_portfolio,
                   'trust_score': trust_score}
    events = generate_events_for_player(temp_player, month, admin_events, auto_events)
    events_triggered = events

    coverage = plan['emergency_coverage']
    for event in events:
        cash_before = cash
        result = apply_event_to_state(
            event, cash, stocks, gold, emergency_fund, trust_score
        )
        cash = result['cash']
        stocks = result['stocks']
        gold = result['gold']
        emergency_fund = result['emergency_fund']
        trust_score = result['trust_score']
        event_log.append(result['log'])

        # ── INSURANCE PAYOUT ──
        # Reimburses a share of CASH losses from insurable categories only.
        # Market moves are deliberately uninsurable: you cannot buy protection
        # from your own portfolio decisions, only from misfortune.
        if coverage > 0 and event.get('category') in INSURABLE_CATEGORIES:
            loss = cash_before - cash
            if loss > 0:
                payout = round(loss * coverage, 2)
                cash += payout
                event_log.append(
                    f"🛡️ Insurance paid out ₹{payout:,.0f} "
                    f"({int(coverage*100)}% of ₹{loss:,.0f})"
                )

    # ════════════════════════════════════════════
    # STEP 6: BIKE EMI
    # ════════════════════════════════════════════
    if bike_status:
        cash -= BIKE_EMI
        event_log.append(f"🏍️ Bike EMI: -₹{BIKE_EMI:,}")

    # ════════════════════════════════════════════
    # STEP 7: LOAN EMI + INTEREST
    # ════════════════════════════════════════════
    total_loan_outstanding = 0
    if active_loans:
        for loan in active_loans:
            loan_id = loan['id']
            principal = float(loan['principal'])
            current_amount = float(loan['current_amount'])
            rate = float(loan.get('interest_rate', LOAN_INTEREST_RATE))

            # Apply interest on the outstanding balance
            interest = current_amount * rate
            current_amount += interest

            # Amortized EMI (fixed for the loan; always exceeds interest so the
            # balance shrinks to zero over LOAN_TERM_MONTHS). Never pay more than
            # what's owed on the final installment.
            term = int(loan.get('term_months') or LOAN_TERM_MONTHS)
            emi = float(loan.get('emi') or 0) or _amortized_emi(principal, rate, term)
            payment = min(emi, current_amount)
            cash -= payment
            current_amount -= payment

            if current_amount <= 0.01:
                current_amount = 0
                status = 'paid'
                event_log.append(f"✅ Loan #{loan_id} fully paid off!")
            else:
                status = 'active'
                event_log.append(f"💳 Loan #{loan_id}: EMI ₹{payment:,.0f}, Interest ₹{interest:,.0f}")

            total_loan_outstanding += max(0, current_amount)
            loan_updates.append({
                "id": loan_id,
                "user_id": uid,
                "current_amount": round(current_amount, 2),
                "status": status
            })

    # ════════════════════════════════════════════
    # STEP 8: SAFETY NET — Emergency fund covers deficit
    # Also grades this month's financial discipline (ADR-008)
    # ════════════════════════════════════════════
    month_discipline = DISCIPLINE_CLEAN_MONTH
    if cash < 0:
        deficit = abs(cash)
        if emergency_fund >= deficit:
            emergency_fund -= deficit
            cash = 0
            month_discipline = DISCIPLINE_EF_RESCUE
            event_log.append(f"🛡️ Emergency fund covered deficit of ₹{deficit:,.0f}")
        else:
            # Use whatever emergency fund is available
            deficit -= emergency_fund
            emergency_fund = 0
            # Auto-loan for the remaining deficit
            # Forced borrowing is punished with the higher AUTO rate — running out
            # of cash should cost more than borrowing deliberately and on plan.
            auto_emi = _amortized_emi(deficit, AUTO_LOAN_INTEREST_RATE, LOAN_TERM_MONTHS)
            new_loans.append({
                "user_id": uid,
                "principal": round(deficit, 2),
                "current_amount": round(deficit, 2),
                "interest_rate": AUTO_LOAN_INTEREST_RATE,
                "month_taken": month,
                "term_months": LOAN_TERM_MONTHS,
                "loan_type": "auto",
                "emi": round(auto_emi, 2),
                "status": "active"
            })
            total_loan_outstanding += deficit
            cash = 0
            month_discipline = DISCIPLINE_AUTO_LOAN
            event_log.append(f"⚠️ CRITICAL: Cash deficit! Emergency fund depleted. Auto-loan of ₹{deficit:,.0f} taken at {AUTO_LOAN_INTEREST_RATE*100:.1f}%/mo penalty interest!")

    # ════════════════════════════════════════════
    # STEP 9: CALCULATE FINAL STATE
    # ════════════════════════════════════════════
    # Decrease bike lock-in
    if bike_lock > 0:
        bike_lock -= 1

    # Calculate risk level
    temp_state = {
        'cash': cash, 'stocks': stocks, 'gold': gold,
        'emergency_fund': emergency_fund, 'investment_portfolio': investment_portfolio,
        'loans': total_loan_outstanding
    }
    risk_level = calculate_risk_score(temp_state)

    # Net worth
    net_worth = calculate_net_worth(
        cash, stocks, gold, emergency_fund, total_loan_outstanding, investment_portfolio
    )

    # ════════════════════════════════════════════
    # STEP 10: FINANCIAL HEALTH SCORE (ADR-008)
    # Composite leaderboard metric — formula is public to players
    # ════════════════════════════════════════════
    prev_discipline = float(player.get('discipline_score', 100) or 100)
    discipline_avg = update_discipline_average(prev_discipline, month, month_discipline)
    total_assets = cash + stocks + gold + emergency_fund + portfolio_value(investment_portfolio)
    
    # D-09: one shared contract for the spouse scoring inputs (income + injected
    # assets + wedding cost); D-03 folds them into the net-worth normalization.
    spouse_income, spouse_assets, wedding_cost = spouse_score_inputs(spouse_arch_id)

    score_result = calculate_financial_health_score(
        net_worth=net_worth, month=month,
        emergency_fund=emergency_fund, monthly_expense=expense_details['current'],
        loans=total_loan_outstanding, total_assets=total_assets,
        risk_score=risk_level, discipline_avg=discipline_avg,
        spouse_income=spouse_income,
        spouse_assets=spouse_assets, wedding_cost=wedding_cost
    )
    c = score_result['components']
    event_log.append(
        f"📊 Financial Health Score: {score_result['score']:.1f} "
        f"(NW {c['net_worth']:.0f} | Liquidity {c['liquidity']:.0f} | "
        f"Debt {c['debt_control']:.0f} | Protection {c['risk_protection']:.0f} | "
        f"Discipline {c['discipline']:.0f})"
    )

    event_log.append(f"═══ Month {month} Net Worth: ₹{net_worth:,.0f} ═══")

    updated_state = {
        "user_id": uid,
        "month": month,
        "cash": round(cash, 2),
        "stocks": round(stocks, 2),
        "gold": round(gold, 2),
        "emergency_fund": round(emergency_fund, 2),
        "investment_portfolio": investment_portfolio,
        "lifestyle_type": lifestyle,
        "bike_status": bike_status,
        "loans": round(total_loan_outstanding, 2),
        "pending_cash_next_month": 0,
        "bike_lock_in_months": bike_lock,
        "net_worth": round(net_worth, 2),
        "trust_score": round(trust_score, 2),
        "risk_level": risk_level,
        "discipline_score": discipline_avg,
        "financial_health_score": score_result['score'],
        "spouse_archetype": spouse_arch_id,
        "spouse_satisfaction": int(satisfaction),
        "household_expense_modifier": round(permanent_mod, 2),
        "insurance_plan": plan_id,
        "status": "active"
    }

    return {
        "updated_state": updated_state,
        "loan_updates": loan_updates,
        "new_loans": new_loans,
        "event_log": event_log,
        "events_triggered": events_triggered,
        "starting_cash": starting_cash,
        "ending_cash": round(cash, 2),
        "net_worth": round(net_worth, 2)
    }
