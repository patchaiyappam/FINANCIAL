# =============================================================================
# GAME CONSTANTS — Single source of truth for all game parameters
# =============================================================================

# Monthly income every player receives
MONTHLY_INCOME = 100000

# Initial allocation budget (Month 1)
INITIAL_BUDGET = 100000

# Total game duration
TOTAL_MONTHS = 12

# ──── LIFESTYLE COSTS ────
LIFESTYLE_COSTS = {
    "city": {
        "rent": 44000,
        "food": 24000,
        "transport": 10000,
        "utilities": 10000,
        "total": 88000
    },
    "outer": {
        "rent": 28000,
        "food": 22000,
        "transport": 22000,
        "utilities": 10000,
        "total": 82000
    }
}
# Surplus after expenses: city Rs12,000/mo, outer Rs18,000/mo on a Rs1,00,000 salary.
# REBALANCE (2026-07-21): was city 40,000 / outer 25,000 total, leaving a Rs60-75k
# risk-free surplus every single month. With nothing able to lose money at that scale,
# every player finished rich and the leaderboard bunched at the top. Expenses now
# consume ~7/8 of income, so allocation decisions actually bind.
#
# SECOND PASS: an earlier attempt at 78k/72k (Rs22-28k surplus) still failed the
# balance sim — accumulated salary dominated every investment decision, the spread
# between the best and worst strategy was only 1.16x, and simply HOARDING CASH beat
# investing. A game that rewards passivity teaches the opposite of what this event
# is for. Surplus is now small enough that returns on capital, not payroll, decide
# the leaderboard.

# ──── ASSET GROWTH RATES (per month) ────
STOCK_BASE_GROWTH = 0.012       # 1.2% monthly base (~15%/yr) before volatility
GOLD_BASE_GROWTH = 0.006        # 0.6% monthly base (~7.5%/yr), stable
EMERGENCY_FUND_GROWTH = 0.005   # 0.5% monthly (~6%/yr savings interest)
# REBALANCE (2026-07-21): previously 8% / 4% / 2% PER MONTH, i.e. ~150%/yr on
# stocks. Compounded over 12 rounds that turned any stock allocation into a
# guaranteed win and made every other decision in the game irrelevant.

# ──── STOCK VOLATILITY RANGE ────
STOCK_VOLATILITY_MIN = -0.09    # Worst auto month: -7.8% net of base growth
STOCK_VOLATILITY_MAX = 0.09     # Best auto month: +10.2% net of base growth
# Symmetric so the volatility draw itself has zero expected value; all drift
# comes from STOCK_BASE_GROWTH. Was -0.15/+0.20, a +2.5%/mo free lunch on top
# of an already absurd 8% base.

# ──── LOAN PARAMETERS ────
# REBALANCE (2026-07-21): rate was 0.12 = 12% PER MONTH (~289%/yr), which is not a
# loan, it is a death sentence. Split into two rates so that borrowing on purpose is
# a real strategic option while being forced into debt still hurts.
LOAN_INTEREST_RATE = 0.012      # 1.2%/mo (~15%/yr) — player-initiated loans
AUTO_LOAN_INTEREST_RATE = 0.025 # 2.5%/mo (~34%/yr) — punitive; forced on cash crisis
LOAN_EMI_FRACTION = 0.10        # (legacy) flat-EMI fraction — kept for reference
LOAN_TERM_MONTHS = 6            # Default term; loans amortize to zero over this many months
LOAN_TERM_OPTIONS = [3, 6, 12]  # Terms a player may choose when borrowing
LOAN_MIN_AMOUNT = 10000
# Total outstanding debt is capped at this multiple of monthly income. Without a cap a
# player could borrow unbounded amounts, dump it all into stocks and leverage-farm the
# leaderboard — the exact failure ADR-008 was written to prevent.
MAX_TOTAL_DEBT_MULTIPLE = 3.0   # Rs3,00,000 ceiling at Rs1,00,000 income
# EMI affordability gate: total EMIs may not exceed this share of monthly income.
MAX_EMI_TO_INCOME = 0.40

# ──── BIKE PARAMETERS ────
BIKE_DOWN_PAYMENT = 10000
BIKE_EMI = 5000
BIKE_LOCK_IN_MONTHS = 3
BIKE_TRANSPORT_DISCOUNT = 0.50  # 50% discount on transport

# ──── SELL PENALTY ────
SELL_PENALTY_RATE = 0.10        # 10% penalty on selling assets

# ──── INFLATION ────
INFLATION_RATE_PER_MONTH = 0.005  # 0.5% monthly inflation on expenses
INFLATION_START_MONTH = 4          # Inflation kicks in from month 4

# ──── TRUST SCORE PARAMETERS ────
TRUST_HELP_AMOUNTS = {
    "none": 0,
    "medium": 2000,
    "high": 5000
}
TRUST_SCORE_GAIN = {
    "none": 0,
    "medium": 1,
    "high": 3
}
TRUST_IGNORE_PENALTY = -1  # Penalty for ignoring social events repeatedly

# ──── VALID RELATIVE TYPES (C-01) ────
# The BACKEND is authoritative for which relatives a player may help. Without an
# allow-list, /handle-relative accepted any string, so a player could mint a fresh
# idempotency key per invented name and bypass the "one help per relative per
# month" cap (farming trust, which shifts event probabilities). The relative-help
# UI panel is currently retired (see frontend/js/dashboard.js), so this endpoint is
# reachable only by direct API calls; this list keeps it bounded and fair. If the
# relative mechanic is revived from public.relative_events, source the set there.
VALID_RELATIVE_TYPES = {"parents", "sibling", "in_laws"}

# ──── EVENT PROBABILITY WEIGHTS ────
# Used by the dynamic event engine
EVENT_BASE_PROBABILITIES = {
    "financial_emergency": 0.25,
    "investment_opportunity": 0.30,
    "social_responsibility": 0.20,
    "market_fluctuation": 0.40,
    "windfall": 0.10,
    "expense_spike": 0.20
}

# ──── RISK LEVEL THRESHOLDS ────
RISK_LEVEL_THRESHOLDS = {
    "conservative": 0.20,   # < 20% in stocks
    "moderate": 0.50,       # 20-50% in stocks
    "aggressive": 1.0       # > 50% in stocks
}

# ──── FINANCIAL HEALTH SCORE WEIGHTS (ADR-008, ratified 2026-07-11) ────
# Composite leaderboard score. Formula is PUBLIC to players (ADR-000: player trust).
# Replaces net-worth-only ranking, which rewarded maximum-leverage gambling.
SCORE_WEIGHTS = {
    "net_worth": 0.40,        # Wealth built
    "liquidity": 0.15,        # Emergency fund adequacy (months of expenses)
    "debt_control": 0.15,     # Debt relative to assets
    "risk_protection": 0.15,  # Inverse of portfolio risk score
    "discipline": 0.15        # Consistency across rounds (no cash crises)
}

# Net worth component: normalized against total resources received so far
# (initial budget + salary months). Capped so extreme leverage can't dominate.
NW_NORMALIZATION_CAP = 1.25

# Liquidity component: emergency fund covering this many months of expenses = full marks
LIQUIDITY_TARGET_MONTHS = 6

# Monthly discipline grades (averaged across the game)
DISCIPLINE_CLEAN_MONTH = 100      # Met all obligations from cash flow
DISCIPLINE_EF_RESCUE = 40         # Emergency fund had to cover a cash deficit
DISCIPLINE_AUTO_LOAN = 0          # Cash crisis forced an auto-loan

# ──── MARRIAGE & COURTSHIP PARAMETERS (ADR-002) ────
# RETUNED 2026-07-24. The V2 rebalance cut the player's monthly surplus from
# ~Rs60,000 to ~Rs12,000 but these stat blocks were left at their old values, so
# a spouse earning Rs10-36k/mo went from a marginal boost to a 1.8-2.25x
# multiplier on everything the player did. marriage_ev_sim.py failed its own
# fairness gates: marrying beat staying single by +10.2% (tolerance +/-4%),
# making the marriage round a no-brainer rather than a decision.
#
# Values below were SOLVED by tools/marriage_tuner.py, not guessed. They pass
# all three gates in both market regimes:
#   spread 4.0%/5.5% (<=8) | single-gap +1.7%/+1.6% (+/-4) | dominance 0.4%/0.6% (<=2)
#
# The design intent survives: The Investor ranks ABOVE "stay single" when the
# market grows and BELOW it when the market is flat, so the spouse choice is a
# genuine read on the economy the admin authors, not a coin flip.
MARRIAGE_MONTH = 6
# Your personal share of the wedding AFTER family contributions and cash gifts —
# not the total cost of the event. Priced so it is a real dent (about 2 months of
# surplus) without being the liquidity landmine Rs88,000 had become.
WEDDING_COST = 25000
SPOUSE_BASE_EXPENSE = 9000

ARCHETYPES = {
    "saver": {
        "name": "The Saver",
        "income": 5000,
        "expense_mod": -2500,
        "stocks": 0,
        "gold": 12000,
        "ef": 23000,
        "loan": 0,
        "description": "Runs the household lean and brings gold and savings. Low income, but she cuts your monthly costs and hands you a cushion."
    },
    "earner": {
        "name": "The Earner",
        "income": 16000,
        "expense_mod": 4500,
        "stocks": 0,
        "gold": 0,
        "ef": 5000,
        "loan": 0,
        "description": "The strongest second income by far, but a bigger lifestyle to match. Steady cash every month, almost nothing up front."
    },
    "investor": {
        "name": "The Investor",
        "income": 4000,
        "expense_mod": -1500,
        "stocks": 35000,
        "gold": 16000,
        "ef": 4000,
        "loan": 0,
        "description": "Brings a built portfolio rather than a salary. Worth the most if the market rises, the least if it stalls — a bet on the economy."
    },
    "anchor": {
        "name": "The Anchor",
        "income": 7000,
        "expense_mod": -500,
        "stocks": 5000,
        "gold": 0,
        "ef": 35000,
        "loan": 0,
        "description": "A large emergency fund and dependable income. Boring on paper; the reason you survive a bad month."
    }
}

# ──── MONTH-6 FAMILY FESTIVAL (Stage 2) + SPOUSE CHARACTER TRAITS (Phase 3A) ────
# The festival is ONE instance of the existing proposal mechanic: a seeded,
# deterministic ask handed to the UNCHANGED negotiation engine. The ask is the
# only thing character traits touch in Phase 3A. Floors, counteroffers,
# satisfaction and rounds all remain archetype-based (negotiation_service).
FESTIVAL_EVENT = {
    "id": "family_function_m7",
    "month": MARRIAGE_MONTH + 1,   # Function follows the family marriage decision.
    "title": "The family function: agree on a budget",
    "description": ("Next month has arrived and your spouse has planned a big family function. Both families will attend, "
                    "and she wants the household to host it properly — outfits, food, "
                    "gifts and the function itself."),
    "kind": "festival",            # no financial return, like 'lifestyle' — that is the lesson
    "base_k": 1.50,                 # Stage-3A approved Model C calibration: 0.50x Monthly Surplus anchor
    "importance": 1.08,            # Stage-2 calibration: per-event social weight
    "ev_note": "Pure consumption — nothing comes back financially. What matters is "
               "what you protect while honouring it.",
}

# Posture: how the spouse's economic spend-lean (expense_mod) scales her ask.
POSTURE_SCALE = 30000
POSTURE_MIN, POSTURE_MAX = 0.85, 1.20

# Stage-2 guardrails on the final ask, as ratios of household income (HHI).
# Dormant at current values — safety rails against extreme future CharAdj.
FESTIVAL_MIN_RATIO = 0.25
FESTIVAL_CAP_RATIO = 1.50

# ── Phase 3A character traits (0–100) ──
# PRU financial prudence · STA status sensitivity · FAM family/tradition weight ·
# FLX flexibility. FLX is RESERVED for Phase 3B negotiation and deliberately does
# NOT enter CharAdj. Frugality is not a trait — the economic archetype
# (income/expense_mod) already carries it; duplicating it would double-count.
CHARACTER_PROFILES = {
    "saver":    {"PRU": 70, "STA": 30, "FAM": 85, "FLX": 55},
    "earner":   {"PRU": 35, "STA": 90, "FAM": 55, "FLX": 40},
    "investor": {"PRU": 90, "STA": 40, "FAM": 35, "FLX": 65},
    "anchor":   {"PRU": 60, "STA": 45, "FAM": 80, "FLX": 50},
}

# CharAdj clamp (Stage-3 approved): keeps character influence bounded.
CHAR_ADJ_MIN, CHAR_ADJ_MAX = 0.85, 1.25

# ──── MARKET SCENARIO REGIMES (2026-07-21) ────
# Stocks and gold are no longer drawn independently. Each month resolves to ONE
# scenario that moves both together with a stated cause, because that correlation IS
# the lesson: in a geopolitical shock capital flees equities into gold, so a
# diversified player survives a month that wipes out an all-in-stocks player.
#
# Each regime: (stock_pct_range, gold_pct_range, weight, name, reason template)
MARKET_REGIMES = {
    "war": {
        "name": "Geopolitical Conflict",
        "reason": "War has broken out. Investors are fleeing equities for safe havens, "
                  "and gold is being bid up hard.",
        "stock": (-0.18, -0.08),
        "gold": (0.06, 0.14),
        "weight": 10
    },
    "crash": {
        "name": "Market Crash",
        "reason": "A banking failure has triggered a broad sell-off. Equities are down "
                  "sharply; gold is catching the flight to safety.",
        "stock": (-0.25, -0.12),
        "gold": (0.04, 0.10),
        "weight": 8
    },
    "rate_hike": {
        "name": "Central Bank Rate Hike",
        "reason": "The RBI has raised rates to fight inflation. Borrowing costs are up, "
                  "equities are under pressure, and gold is less attractive than yield.",
        "stock": (-0.09, -0.03),
        "gold": (-0.05, -0.01),
        "weight": 12
    },
    "inflation_spike": {
        "name": "Inflation Spike",
        "reason": "Fuel and food prices have surged. Equities are flat to soft while "
                  "gold rallies as an inflation hedge.",
        "stock": (-0.03, 0.02),
        "gold": (0.04, 0.08),
        "weight": 12
    },
    "steady": {
        "name": "Steady Growth",
        "reason": "No major shocks. Corporate earnings are in line and markets are "
                  "grinding quietly higher.",
        "stock": (0.01, 0.04),
        "gold": (0.00, 0.02),
        "weight": 25
    },
    "boom": {
        "name": "Bull Run",
        "reason": "Strong GDP numbers and heavy foreign inflows. Equities are running; "
                  "money is rotating out of gold into risk.",
        "stock": (0.06, 0.12),
        "gold": (-0.03, 0.01),
        "weight": 15
    },
    "recovery": {
        "name": "Post-Crisis Recovery",
        "reason": "Confidence is returning after the shock. Equities are rebounding and "
                  "the safe-haven premium on gold is unwinding.",
        "stock": (0.04, 0.09),
        "gold": (-0.04, 0.00),
        "weight": 12
    },
    "correction": {
        "name": "Technical Correction",
        "reason": "Markets got ahead of fundamentals and are giving some back. An "
                  "ordinary pullback, not a crisis.",
        "stock": (-0.07, -0.02),
        "gold": (0.00, 0.03),
        "weight": 15
    }
}

# Regime that follows a shock is biased toward recovery, so the market has memory
# instead of being a fresh coin flip each month.
POST_SHOCK_REGIMES = ["recovery", "steady", "correction"]
SHOCK_REGIMES = ["war", "crash"]


# ──── INSURANCE (replaces Social Investment / trust, 2026-07-21) ────
# Trust score was removed from the player UI: it cost real money, fed almost
# nothing into the ADR-008 leaderboard score, and taught no financial lesson.
# Insurance replaces it because it is in the PRD, it is a genuine risk-management
# decision, and it gives the risk_protection score component a lever the player
# can actually pull.
#
# The trade is deliberately uncomfortable: premiums are a GUARANTEED small loss
# every month against an UNCERTAIN large loss. A player who buys cover and is
# never hit has "wasted" money — and that is exactly the lesson.
INSURANCE_PLANS = {
    "none": {
        "name": "No Cover",
        "premium": 0,
        "emergency_coverage": 0.0,
        "description": "No premium. You absorb the full cost of any emergency."
    },
    "basic": {
        "name": "Basic Health Cover",
        "premium": 2500,
        "emergency_coverage": 0.50,
        "description": "Rs2,500/month. Covers 50% of any medical or emergency event."
    },
    "comprehensive": {
        "name": "Comprehensive Health + Life",
        "premium": 6000,
        "emergency_coverage": 0.80,
        "description": "Rs6,000/month. Covers 80% of any medical or emergency event."
    }
}

# Which event categories insurance pays out against. Market losses are NOT
# insurable — a player cannot buy protection from their own portfolio choices.
INSURABLE_CATEGORIES = {"emergency", "medical"}


# ──── SPOUSE NEGOTIATION (ADR-014, 2026-07-24) ────
# She raises one proposal per month; the player negotiates in natural language.
# EVERY rupee here is decided by services/negotiation_service.py. The AI layer
# only extracts intent and voices her replies (ADR-003).

NEGOTIATION_MAX_ROUNDS = 3
# Round 1 is NEVER an auto-accept, however generous the offer. Persuasion is not
# a single click — this is the "don't allow immediately" requirement in code.
NEGOTIATION_MIN_ROUND_TO_ACCEPT = 2

SATISFACTION_START = 60
SATISFACTION_MIN = 0
SATISFACTION_MAX = 100

# Satisfaction deltas by outcome.
SATISFACTION_DELTA = {
    "accepted_full": 6,      # took her ask without haggling
    "accepted_counter": 2,   # met in the middle
    "auto_resolved": -8,     # ran out of rounds; she went ahead anyway
    "refused": -15,          # flat no
    "delayed": -4,           # pushed it to a later month
}

# Bounded financial teeth. Deliberately small: the relationship colours the game,
# it does not decide it. Symmetric around satisfaction 50.
#   satisfaction 0   -> +Rs3,000/month (a tense household costs more)
#   satisfaction 50  ->  Rs0
#   satisfaction 100 -> -Rs3,000/month (a happy one runs cheaper)
SATISFACTION_EXPENSE_SWING = 3000

# Lowest share of her ask each wife will ever settle for, at maximum satisfaction.
# Below this she will not go at any satisfaction level.
NEGOTIATION_FLOOR_RATIO = {
    "earner": 0.70,     # it is her lifestyle; she holds firm
    "investor": 0.60,
    "anchor": 0.55,
    "saver": 0.50,      # frugal by nature; most willing to trim
}

# How much UNhappiness stiffens her. At satisfaction 100 the required offer is the
# floor; at 0 it rises toward the full ask by this fraction of the gap.
NEGOTIATION_HARDNESS = 0.8


def negotiation_min_ratio(archetype_id: str, satisfaction: float) -> float:
    """
    Minimum share of her ask she will accept, given her archetype and how happy
    she is. MONOTONIC: higher satisfaction never raises the required offer.
    """
    floor = NEGOTIATION_FLOOR_RATIO.get(archetype_id, 0.6)
    sat = max(SATISFACTION_MIN, min(SATISFACTION_MAX, float(satisfaction)))
    unhappiness = 1.0 - (sat / 100.0)
    return floor + (1.0 - floor) * unhappiness * NEGOTIATION_HARDNESS


def satisfaction_expense_drift(satisfaction: float) -> float:
    """Monthly household expense adjustment from the relationship. Bounded."""
    sat = max(SATISFACTION_MIN, min(SATISFACTION_MAX, float(satisfaction)))
    return round((50.0 - sat) / 50.0 * SATISFACTION_EXPENSE_SWING, 2)

# Additional fictional spouse profiles; figures are game values, not salary data.
ARCHETYPES.update({
    "teacher": {"name": "The Teacher", "income": 6000, "expense_mod": -1500,
                "stocks": 2500, "gold": 6000, "ef": 29000, "loan": 0,
                "description": "Steady teaching income, modest living costs and a savings buffer. Values a thoughtful family gathering over an expensive venue."},
    "healthcare": {"name": "The Healthcare Professional", "income": 11500, "expense_mod": 2000,
                   "stocks": 2500, "gold": 0, "ef": 20000, "loan": 0,
                   "description": "Higher income with higher everyday costs. Wants the family function to feel special, but will discuss a practical budget."},
})
CHARACTER_PROFILES.update({
    "teacher": {"PRU": 65, "STA": 38, "FAM": 82, "FLX": 60},
    "healthcare": {"PRU": 48, "STA": 67, "FAM": 68, "FLX": 48},
})
NEGOTIATION_FLOOR_RATIO.update({"teacher": 0.52, "healthcare": 0.63})
