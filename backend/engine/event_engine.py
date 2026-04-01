# =============================================================================
# DYNAMIC EVENT ENGINE
# Generates probabilistic, context-aware financial events each month.
# Events are NEVER fixed or predictable — they depend on player state.
# =============================================================================

import random
import hashlib
from models.constants import EVENT_BASE_PROBABILITIES


def _seeded_random(user_id: str, month: int, salt: str = "") -> random.Random:
    """Create a seeded Random instance for deterministic-per-player-month randomness."""
    seed_str = f"{user_id}:{month}:{salt}"
    seed_val = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    rng = random.Random(seed_val)
    return rng


def _calculate_risk_level(player: dict) -> str:
    """Determine player's risk profile based on portfolio composition."""
    total = (
        float(player.get('cash', 0)) +
        float(player.get('stocks', 0)) +
        float(player.get('gold', 0)) +
        float(player.get('emergency_fund', 0))
    )
    if total <= 0:
        return "desperate"

    stock_ratio = float(player.get('stocks', 0)) / total
    emergency_ratio = float(player.get('emergency_fund', 0)) / total

    if stock_ratio > 0.50:
        return "aggressive"
    elif emergency_ratio < 0.05:
        return "risky"
    elif stock_ratio < 0.15:
        return "conservative"
    else:
        return "moderate"


def generate_events_for_player(player: dict, month: int, admin_events: list = None) -> list:
    """
    Generate a list of events for a specific player in a specific month.
    
    Events are context-aware:
    - Low emergency fund → higher chance of emergency
    - High stock investment → higher volatility
    - Low trust score → social penalties
    - High cash hoarding → opportunity events
    
    Returns list of event dicts with:
      {name, type, description, impact_target, value, severity}
    """
    user_id = player.get('user_id', 'unknown')
    rng = _seeded_random(user_id, month, "events")
    events = []
    risk_level = _calculate_risk_level(player)

    cash = float(player.get('cash', 0))
    stocks = float(player.get('stocks', 0))
    gold = float(player.get('gold', 0))
    emergency = float(player.get('emergency_fund', 0))
    loans = float(player.get('loans', 0))
    trust = float(player.get('trust_score', 0) or 0)

    # ──────────────────────────────────────────────
    # 1. FINANCIAL EMERGENCY
    # Higher chance if emergency fund is low
    # ──────────────────────────────────────────────
    emergency_prob = EVENT_BASE_PROBABILITIES["financial_emergency"]
    if emergency < 5000:
        emergency_prob += 0.20  # Much more likely if unprepared
    if loans > 0:
        emergency_prob += 0.10  # Debt increases vulnerability

    if rng.random() < emergency_prob:
        severity = rng.choice(["minor", "moderate", "severe"])
        emergencies = {
            "minor": [
                {"name": "Phone Repair", "value": -3000, "desc": "Your phone screen cracked. Repair costs ₹3,000."},
                {"name": "Medical Checkup", "value": -2500, "desc": "Routine medical tests cost ₹2,500."},
                {"name": "Appliance Failure", "value": -4000, "desc": "Your washing machine broke down. Replacement: ₹4,000."},
            ],
            "moderate": [
                {"name": "Health Emergency", "value": -12000, "desc": "Unexpected hospital visit costs ₹12,000."},
                {"name": "Vehicle Breakdown", "value": -8000, "desc": "Major vehicle repair needed: ₹8,000."},
                {"name": "Legal Fee", "value": -10000, "desc": "An unexpected legal consultation costs ₹10,000."},
            ],
            "severe": [
                {"name": "Family Medical Crisis", "value": -25000, "desc": "A family member needs urgent surgery. Cost: ₹25,000."},
                {"name": "Theft / Loss", "value": -15000, "desc": "Valuables stolen from your home. Loss: ₹15,000."},
                {"name": "Natural Disaster", "value": -20000, "desc": "Flooding damaged your belongings. Repair: ₹20,000."},
            ]
        }
        chosen = rng.choice(emergencies[severity])
        events.append({
            "name": chosen["name"],
            "type": "fixed",
            "description": chosen["desc"],
            "impact_target": "cash",
            "value": chosen["value"],
            "severity": severity,
            "category": "emergency"
        })

    # ──────────────────────────────────────────────
    # 2. INVESTMENT OPPORTUNITY
    # Higher chance if player has liquid cash
    # ──────────────────────────────────────────────
    opp_prob = EVENT_BASE_PROBABILITIES["investment_opportunity"]
    if cash > 50000:
        opp_prob += 0.15  # More opportunities if you have money
    if risk_level == "aggressive":
        opp_prob += 0.10

    if rng.random() < opp_prob:
        opportunities = [
            {"name": "Stock Tip", "desc": "A reliable tip pays off. Stocks gain 12%.", "target": "stocks", "value": 12, "type": "percentage"},
            {"name": "Gold Surge", "desc": "Gold prices spike unexpectedly. Gold gains 8%.", "target": "gold", "value": 8, "type": "percentage"},
            {"name": "Freelance Gig", "desc": "You landed a freelance project. Earned ₹15,000 extra.", "target": "cash", "value": 15000, "type": "fixed"},
            {"name": "Bonus at Work", "desc": "Performance bonus received: ₹10,000.", "target": "cash", "value": 10000, "type": "fixed"},
            {"name": "Dividend Payout", "desc": "Your stocks paid dividends. Received ₹5,000.", "target": "cash", "value": 5000, "type": "fixed"},
        ]
        chosen = rng.choice(opportunities)
        events.append({
            "name": chosen["name"],
            "type": chosen["type"],
            "description": chosen["desc"],
            "impact_target": chosen["target"],
            "value": chosen["value"],
            "severity": "positive",
            "category": "opportunity"
        })

    # ──────────────────────────────────────────────
    # 3. MARKET FLUCTUATION
    # Always possible, but intensity depends on portfolio
    # ──────────────────────────────────────────────
    if rng.random() < EVENT_BASE_PROBABILITIES["market_fluctuation"]:
        # Stock markets are volatile
        stock_change = rng.uniform(-12, 15)  # -12% to +15%
        direction = "rose" if stock_change > 0 else "dropped"
        events.append({
            "name": f"Market {direction.title()}",
            "type": "percentage",
            "description": f"Stock markets {direction} by {abs(stock_change):.1f}% this month.",
            "impact_target": "stocks",
            "value": round(stock_change, 2),
            "severity": "positive" if stock_change > 0 else "negative",
            "category": "market"
        })

        # Gold is more stable but occasionally moves
        if rng.random() < 0.3:
            gold_change = rng.uniform(-3, 5)
            events.append({
                "name": "Gold Price Movement",
                "type": "percentage",
                "description": f"Gold prices shifted by {gold_change:+.1f}% this month.",
                "impact_target": "gold",
                "value": round(gold_change, 2),
                "severity": "positive" if gold_change > 0 else "negative",
                "category": "market"
            })

    # ──────────────────────────────────────────────
    # 4. SOCIAL RESPONSIBILITY EVENT
    # Affects trust score — ignoring has future consequences
    # ──────────────────────────────────────────────
    if rng.random() < EVENT_BASE_PROBABILITIES["social_responsibility"]:
        social_events = [
            {"name": "Charity Drive", "desc": "A community charity drive asks for contributions. ₹3,000 donated.", "value": -3000},
            {"name": "Friend's Wedding", "desc": "A close friend's wedding. Gift cost: ₹5,000.", "value": -5000},
            {"name": "Community Festival", "desc": "Local festival participation costs ₹2,000.", "value": -2000},
            {"name": "Relative's Education Fund", "desc": "A relative needs education support. You contributed ₹4,000.", "value": -4000},
        ]
        chosen = rng.choice(social_events)
        events.append({
            "name": chosen["name"],
            "type": "fixed",
            "description": chosen["desc"] + " (Trust +2)",
            "impact_target": "cash",
            "value": chosen["value"],
            "severity": "social",
            "category": "social",
            "trust_change": 2
        })

    # ──────────────────────────────────────────────
    # 5. EXPENSE SPIKE
    # Random cost-of-living increases
    # ──────────────────────────────────────────────
    if rng.random() < EVENT_BASE_PROBABILITIES["expense_spike"]:
        spikes = [
            {"name": "Rent Increase", "desc": "Landlord increased rent temporarily. Extra ₹3,000 this month.", "value": -3000},
            {"name": "Fuel Price Hike", "desc": "Fuel prices spiked. Extra transport cost: ₹2,000.", "value": -2000},
            {"name": "Grocery Inflation", "desc": "Food prices rose sharply. Extra ₹2,500 on groceries.", "value": -2500},
            {"name": "Utility Bills Surge", "desc": "Electricity and water bills spiked: ₹3,500 extra.", "value": -3500},
        ]
        chosen = rng.choice(spikes)
        events.append({
            "name": chosen["name"],
            "type": "fixed",
            "description": chosen["desc"],
            "impact_target": "cash",
            "value": chosen["value"],
            "severity": "negative",
            "category": "expense"
        })

    # ──────────────────────────────────────────────
    # 6. WINDFALL (Rare positive surprise)
    # ──────────────────────────────────────────────
    windfall_prob = EVENT_BASE_PROBABILITIES["windfall"]
    if trust > 5:
        windfall_prob += 0.05  # High trust = better karma
    if month >= 9 and trust > 8:
        windfall_prob += 0.15  # Late-game trust payoff

    if rng.random() < windfall_prob:
        windfalls = [
            {"name": "Tax Refund", "desc": "Government tax refund received: ₹8,000.", "value": 8000},
            {"name": "Lucky Draw", "desc": "Won a lucky draw at a mall: ₹5,000.", "value": 5000},
            {"name": "Insurance Claim", "desc": "Old insurance claim settled: ₹12,000.", "value": 12000},
            {"name": "Inheritance", "desc": "A distant relative left you ₹20,000.", "value": 20000},
        ]
        chosen = rng.choice(windfalls)
        events.append({
            "name": chosen["name"],
            "type": "fixed",
            "description": chosen["desc"],
            "impact_target": "cash",
            "value": chosen["value"],
            "severity": "positive",
            "category": "windfall"
        })

    # ──────────────────────────────────────────────
    # 7. TRUST PENALTY (if trust is very low mid-game)
    # ──────────────────────────────────────────────
    if month >= 6 and trust < 2:
        if rng.random() < 0.4:
            events.append({
                "name": "Social Isolation Penalty",
                "type": "fixed",
                "description": "Your poor social standing led to missed opportunities. Lost ₹5,000 in potential connections.",
                "impact_target": "cash",
                "value": -5000,
                "severity": "negative",
                "category": "penalty",
                "trust_change": -1
            })

    # ──────────────────────────────────────────────
    # 8. INCLUDE ADMIN EVENTS (if any)
    # ──────────────────────────────────────────────
    if admin_events:
        for ev in admin_events:
            events.append({
                "name": ev.get('event_name', 'Admin Event'),
                "type": ev.get('event_type', 'fixed'),
                "description": ev.get('description', ''),
                "impact_target": ev.get('impact_target', 'cash'),
                "value": float(ev.get('value', 0)),
                "severity": "admin",
                "category": "admin"
            })

    return events


def apply_event_to_state(event: dict, cash: float, stocks: float, gold: float,
                         emergency_fund: float, trust_score: float) -> dict:
    """
    Apply a single event to player financial state.
    Returns dict with updated values and a log message.
    """
    val = float(event['value'])
    target = event['impact_target']
    etype = event['type']
    log = f"⚡ {event['name']}: {event['description']}"

    if etype == 'percentage':
        if target == 'stocks':
            delta = stocks * (val / 100)
            stocks += delta
            log += f" (Stocks {'+' if delta >= 0 else ''}{delta:.0f})"
        elif target == 'gold':
            delta = gold * (val / 100)
            gold += delta
            log += f" (Gold {'+' if delta >= 0 else ''}{delta:.0f})"
        elif target == 'cash':
            delta = cash * (val / 100)
            cash += delta
            log += f" (Cash {'+' if delta >= 0 else ''}{delta:.0f})"
    elif etype == 'fixed':
        if target == 'cash':
            cash += val
            log += f" (Cash {'+' if val >= 0 else ''}{val:.0f})"
        elif target == 'stocks':
            stocks += val
        elif target == 'gold':
            gold += val
        elif target == 'expense_increase':
            cash -= abs(val)
            log += f" (Expense +{abs(val):.0f})"

    # Trust score changes
    trust_change = event.get('trust_change', 0)
    trust_score += trust_change
    trust_score = max(0, trust_score)  # Floor at 0

    return {
        "cash": cash,
        "stocks": max(0, stocks),
        "gold": max(0, gold),
        "emergency_fund": emergency_fund,
        "trust_score": trust_score,
        "log": log
    }
