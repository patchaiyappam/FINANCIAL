# =============================================================================
# GAME SERVICE — Database helpers for game state management
# =============================================================================

import hashlib
from collections import defaultdict
from supabase_client import supabase


# ──── In-memory rate limiting for purchases ────
_rate_limit: dict = defaultdict(set)


def get_game_state() -> dict | None:
    """Fetch the current game control state."""
    res = supabase.table('game_control').select('*').limit(1).execute()
    return res.data[0] if res.data else None


def get_player(user_id: str) -> dict | None:
    """Fetch a player's current state."""
    res = supabase.table('player_state').select('*').eq('user_id', user_id).execute()
    return res.data[0] if res.data else None


def get_all_players() -> list:
    """Fetch all player states."""
    res = supabase.table('player_state').select('*').execute()
    return res.data if res.data else []


def get_active_loans(user_id: str) -> list:
    """Fetch all active loans for a player."""
    res = (supabase.table('player_loans')
           .select('*')
           .eq('user_id', user_id)
           .eq('status', 'active')
           .execute())
    return res.data if res.data else []


def get_total_loans(user_id: str) -> float:
    """Calculate total outstanding loan amount for a player."""
    loans = get_active_loans(user_id)
    return sum(float(r['current_amount']) for r in loans)


def get_pending_sales(user_id: str, month: int) -> list:
    """Fetch pending asset sales that should be credited this month."""
    res = (supabase.table('player_sales')
           .select('*')
           .eq('user_id', user_id)
           .eq('month_to_credit', month)
           .execute())
    return res.data if res.data else []


def get_player_event_log(user_id: str, month: int) -> list:
    """Fetch event logs for a specific month."""
    res = (supabase.table('player_month_log')
           .select('*')
           .eq('user_id', user_id)
           .eq('month', month)
           .execute())
    return res.data if res.data else []


def get_all_event_logs(user_id: str) -> list:
    """Fetch all event logs for a player, ordered by month."""
    res = (supabase.table('player_month_log')
           .select('*')
           .eq('user_id', user_id)
           .order('month')
           .execute())
    return res.data if res.data else []


def get_admin_events_for_month(month: int) -> list:
    """Fetch admin-created events for a specific month."""
    res = (supabase.table('events')
           .select('*')
           .eq('month', month)
           .execute())
    return res.data if res.data else []


def get_optional_choices(month: int) -> list:
    """Fetch optional choices available for a specific month."""
    res = (supabase.table('optional_choices')
           .select('*')
           .eq('month', month)
           .execute())
    return res.data if res.data else []


def get_trust_scores(user_id: str) -> list:
    """Fetch all trust scores for a player."""
    res = (supabase.table('player_relative_score')
           .select('*')
           .eq('user_id', user_id)
           .execute())
    return res.data if res.data else []


def get_leaderboard(limit: int = 50) -> list:
    """Fetch leaderboard ranked by net_worth."""
    res = (supabase.table('player_state')
           .select('user_id, net_worth, trust_score, risk_level, month, users(name)')
           .order('net_worth', desc=True)
           .limit(limit)
           .execute())
    return res.data if res.data else []


# ──── Fair Probability Engine ────
def fair_roll(user_id: str, month: int, choice_id: int, probability: int) -> bool:
    """Deterministic RNG per player+month+choice for fairness."""
    seed_str = f"{user_id}:{month}:{choice_id}"
    digest = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    roll = (digest % 100) + 1
    return roll <= probability


# ──── Purchase Rate Limiting ────
def already_bought(user_id: str, month: int, choice_id: int) -> bool:
    key = f"{user_id}:{month}"
    return choice_id in _rate_limit[key]


def mark_bought(user_id: str, month: int, choice_id: int):
    key = f"{user_id}:{month}"
    _rate_limit[key].add(choice_id)


# ──── RPC Payload Validator ────
PLAYER_STATE_REQUIRED = {
    'user_id', 'month', 'cash', 'stocks', 'gold',
    'emergency_fund', 'lifestyle_type', 'bike_status',
    'loans', 'pending_cash_next_month', 'bike_lock_in_months',
    'net_worth', 'status'
}
LOAN_UPDATE_REQUIRED = {'id', 'user_id', 'current_amount', 'status'}
LOAN_INSERT_REQUIRED = {'user_id', 'principal', 'current_amount', 'interest_rate', 'month_taken', 'status'}
LOG_REQUIRED = {'user_id', 'month', 'starting_cash', 'ending_cash', 'net_worth', 'summary'}


def validate_rpc_payload(updates_state, updates_loans, inserts_loans, inserts_logs) -> str | None:
    """Validate all payload fields before sending to RPC."""
    for i, rec in enumerate(updates_state):
        missing = PLAYER_STATE_REQUIRED - set(rec.keys())
        if missing:
            return f"updates_player_state[{i}] missing: {missing}"
    for i, rec in enumerate(updates_loans):
        missing = LOAN_UPDATE_REQUIRED - set(rec.keys())
        if missing:
            return f"updates_loans[{i}] missing: {missing}"
    for i, rec in enumerate(inserts_loans):
        missing = LOAN_INSERT_REQUIRED - set(rec.keys())
        if missing:
            return f"inserts_loans[{i}] missing: {missing}"
    for i, rec in enumerate(inserts_logs):
        missing = LOG_REQUIRED - set(rec.keys())
        if missing:
            return f"inserts_logs[{i}] missing: {missing}"
    return None
