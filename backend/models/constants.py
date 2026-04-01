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
        "rent": 25000,
        "food": 10000,
        "transport": 5000,
        "total": 40000
    },
    "outer": {
        "rent": 10000,
        "food": 10000,
        "transport": 5000,
        "total": 25000
    }
}

# ──── ASSET GROWTH RATES (per month) ────
STOCK_BASE_GROWTH = 0.08        # 8% monthly base (before volatility)
GOLD_BASE_GROWTH = 0.04         # 4% monthly base (stable)
EMERGENCY_FUND_GROWTH = 0.02    # 2% monthly (savings interest)

# ──── STOCK VOLATILITY RANGE ────
STOCK_VOLATILITY_MIN = -0.15    # Can drop 15%
STOCK_VOLATILITY_MAX = 0.20     # Can rise 20%

# ──── LOAN PARAMETERS ────
LOAN_INTEREST_RATE = 0.12       # 12% per month
LOAN_EMI_FRACTION = 0.10        # EMI = 10% of principal per month

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

# ──── LEADERBOARD SCORING WEIGHTS ────
LEADERBOARD_WEIGHTS = {
    "net_worth": 0.50,
    "stability": 0.30,      # Inverse of risk
    "trust_score": 0.20
}
