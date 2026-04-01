# =============================================================================
# MONTHLY PROCESSOR
# Core engine that processes each month:
#   1. Income → 2. Expenses → 3. Investments → 4. Events → 5. Loans → 6. Safety net
# =============================================================================

from models.constants import (
    MONTHLY_INCOME, LIFESTYLE_COSTS, BIKE_EMI,
    LOAN_INTEREST_RATE, LOAN_EMI_FRACTION,
    INFLATION_RATE_PER_MONTH, INFLATION_START_MONTH
)
from engine.event_engine import generate_events_for_player, apply_event_to_state
from engine.market_engine import (
    calculate_investment_growth, calculate_inflation_adjustment,
    calculate_net_worth, calculate_risk_score
)


def process_month_for_player(player: dict, month: int,
                              admin_events: list = None,
                              active_loans: list = None,
                              pending_sales: list = None) -> dict:
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
    cash += MONTHLY_INCOME
    event_log.append(f"💰 Salary received: +₹{MONTHLY_INCOME:,}")

    # ════════════════════════════════════════════
    # STEP 2: DEDUCT LIFESTYLE EXPENSES (with inflation)
    # ════════════════════════════════════════════
    base_expense = LIFESTYLE_COSTS.get(lifestyle, LIFESTYLE_COSTS['city'])['total']
    adjusted_expense = calculate_inflation_adjustment(base_expense, month)
    
    # Bike discount on transport
    if bike_status:
        transport_base = LIFESTYLE_COSTS.get(lifestyle, LIFESTYLE_COSTS['city'])['transport']
        transport_saving = transport_base * 0.5
        adjusted_expense -= transport_saving
        event_log.append(f"🏍️ Bike saves ₹{transport_saving:,.0f} on transport")

    cash -= adjusted_expense
    if month >= INFLATION_START_MONTH:
        event_log.append(f"🏠 Living expenses: -₹{adjusted_expense:,.0f} (inflation-adjusted)")
    else:
        event_log.append(f"🏠 Living expenses: -₹{adjusted_expense:,.0f}")

    # ════════════════════════════════════════════
    # STEP 3: HANDLE PENDING ASSET SALE CREDITS
    # (This is handled in the route by querying player_sales)
    # ════════════════════════════════════════════

    # ════════════════════════════════════════════
    # STEP 4: INVESTMENT GROWTH
    # ════════════════════════════════════════════
    growth = calculate_investment_growth(player, month)
    stocks = growth['stocks']
    gold = growth['gold']
    emergency_fund = growth['emergency_fund']
    for g_log in growth['logs']:
        event_log.append(g_log)

    # ════════════════════════════════════════════
    # STEP 5: DYNAMIC EVENTS
    # ════════════════════════════════════════════
    # Build a temporary player state for event generation with current trust
    temp_player = {**player, 'cash': cash, 'stocks': stocks, 'gold': gold,
                   'emergency_fund': emergency_fund, 'trust_score': trust_score}
    events = generate_events_for_player(temp_player, month, admin_events)
    events_triggered = events

    for event in events:
        result = apply_event_to_state(
            event, cash, stocks, gold, emergency_fund, trust_score
        )
        cash = result['cash']
        stocks = result['stocks']
        gold = result['gold']
        emergency_fund = result['emergency_fund']
        trust_score = result['trust_score']
        event_log.append(result['log'])

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

            # Apply interest
            interest = current_amount * rate
            current_amount += interest

            # Pay EMI
            emi = principal * LOAN_EMI_FRACTION
            cash -= emi
            current_amount -= emi

            if current_amount <= 0:
                current_amount = 0
                status = 'paid'
                event_log.append(f"✅ Loan #{loan_id} fully paid off!")
            else:
                status = 'active'
                event_log.append(f"💳 Loan #{loan_id}: EMI ₹{emi:,.0f}, Interest ₹{interest:,.0f}")

            total_loan_outstanding += max(0, current_amount)
            loan_updates.append({
                "id": loan_id,
                "user_id": uid,
                "current_amount": round(current_amount, 2),
                "status": status
            })

    # ════════════════════════════════════════════
    # STEP 8: SAFETY NET — Emergency fund covers deficit
    # ════════════════════════════════════════════
    if cash < 0:
        deficit = abs(cash)
        if emergency_fund >= deficit:
            emergency_fund -= deficit
            cash = 0
            event_log.append(f"🛡️ Emergency fund covered deficit of ₹{deficit:,.0f}")
        else:
            # Use whatever emergency fund is available
            deficit -= emergency_fund
            emergency_fund = 0
            # Auto-loan for the remaining deficit
            new_loans.append({
                "user_id": uid,
                "principal": round(deficit, 2),
                "current_amount": round(deficit, 2),
                "interest_rate": LOAN_INTEREST_RATE,
                "month_taken": month,
                "status": "active"
            })
            total_loan_outstanding += deficit
            cash = 0
            event_log.append(f"⚠️ CRITICAL: Cash deficit! Emergency fund depleted. Auto-loan of ₹{deficit:,.0f} taken at {LOAN_INTEREST_RATE*100}% interest!")

    # ════════════════════════════════════════════
    # STEP 9: CALCULATE FINAL STATE
    # ════════════════════════════════════════════
    # Decrease bike lock-in
    if bike_lock > 0:
        bike_lock -= 1

    # Calculate risk level
    temp_state = {
        'cash': cash, 'stocks': stocks, 'gold': gold,
        'emergency_fund': emergency_fund, 'loans': total_loan_outstanding
    }
    risk_level = calculate_risk_score(temp_state)

    # Net worth
    net_worth = calculate_net_worth(cash, stocks, gold, emergency_fund, total_loan_outstanding)

    event_log.append(f"═══ Month {month} Net Worth: ₹{net_worth:,.0f} ═══")

    updated_state = {
        "user_id": uid,
        "month": month,
        "cash": round(cash, 2),
        "stocks": round(stocks, 2),
        "gold": round(gold, 2),
        "emergency_fund": round(emergency_fund, 2),
        "lifestyle_type": lifestyle,
        "bike_status": bike_status,
        "loans": round(total_loan_outstanding, 2),
        "pending_cash_next_month": 0,
        "bike_lock_in_months": bike_lock,
        "net_worth": round(net_worth, 2),
        "trust_score": round(trust_score, 2),
        "risk_level": risk_level,
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
