# =============================================================================
# GAME SERVICE — Database helpers for game state management
# =============================================================================

import hashlib
from supabase_client import supabase


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


def get_market_scenario_row(month: int) -> dict | None:
    """
    Fetch the admin-authored market scenario for a month, if one exists.
    Returns None when the month is unauthored, which is the signal for the engine
    to fall back to its auto-generated correlated regime.
    """
    try:
        res = (supabase.table('market_scenarios')
               .select('*')
               .eq('month', month)
               .limit(1)
               .execute())
        return res.data[0] if res.data else None
    except Exception:
        # Table missing (migration not applied) must not break the month roll.
        return None


def get_month_allocation(user_id: str, month: int) -> dict | None:
    """Fetch a player's recorded allocation for a month, if any."""
    try:
        res = (supabase.table('player_month_allocations')
               .select('*')
               .eq('user_id', user_id)
               .eq('month', month)
               .limit(1)
               .execute())
        return res.data[0] if res.data else None
    except Exception:
        return None


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
    """
    Fetch leaderboard ranked by Financial Health Score (ADR-008).
    Net worth is the tiebreaker and remains visible, but ranking rewards
    balanced financial management, not just wealth accumulation.
    """
    from engine.scoring import score_player_snapshot
    res = supabase.table('player_state').select('*, users(name)').execute()
    rows = res.data or []
    for row in rows:
        row.update(score_player_snapshot(row))
    rows.sort(key=lambda row: (float(row.get('financial_health_score') or 0),
                               float(row.get('net_worth') or 0)), reverse=True)
    return rows[:limit]


# ──── Fair Probability Engine ────
def fair_roll(user_id: str, month: int, choice_id: int, probability: int) -> bool:
    """Deterministic RNG per player+month+choice for fairness."""
    seed_str = f"{user_id}:{month}:{choice_id}"
    digest = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    roll = (digest % 100) + 1
    return roll <= probability


# ──── Per-month Action Idempotency (durable, DB-backed) ────
# Survives server restarts and is shared across all web workers, unlike the
# old in-memory dict. Backed by public.player_month_actions (see
# idempotency_migration.sql).
def action_done(user_id: str, month: int, action_key: str) -> bool:
    """True if this (user, month, action_key) has already been recorded."""
    res = (supabase.table('player_month_actions')
           .select('action_key')
           .eq('user_id', user_id)
           .eq('month', month)
           .eq('action_key', action_key)
           .limit(1)
           .execute())
    return bool(res.data)


def _is_unique_violation(exc: Exception) -> bool:
    """
    True only if `exc` is a Postgres unique-violation (duplicate primary key),
    i.e. this exact (user, month, action_key) was already claimed — as opposed
    to any other failure (missing table, transient network/DB error, denied
    permission). Robust across supabase-py/postgrest versions: some expose a
    `.code` attribute, others fold the SQLSTATE into the error message/dict.
    """
    code = getattr(exc, 'code', None)
    if code == '23505':
        return True
    text = (str(getattr(exc, 'message', '') or '') + ' ' + str(exc)).lower()
    return '23505' in text or 'duplicate key' in text or 'already exists' in text


def mark_action(user_id: str, month: int, action_key: str) -> bool:
    """
    Atomically CLAIM an action. Returns True if this call recorded it, False
    ONLY if it was already recorded — the PRIMARY KEY makes a duplicate insert
    raise a unique-violation, which is the atomic claim that closes the
    check-then-act race between concurrent requests.

    Any OTHER failure (missing `player_month_actions` table, transient DB/network
    error, permissions) is re-raised rather than swallowed. Previously every
    exception returned False, so a real outage was silently reported to the
    player as "you already did this", and a fresh deploy that forgot
    `idempotency_migration.sql` would permanently block EVERY buy-choice /
    relative-help with no error surfaced anywhere (see QA_REPORT_V1 F-03/F-02).
    Failing loud on non-duplicate errors makes that misconfiguration diagnosable.
    """
    try:
        supabase.table('player_month_actions').insert({
            'user_id': user_id,
            'month': month,
            'action_key': action_key
        }).execute()
        return True
    except Exception as e:
        if _is_unique_violation(e):
            return False
        raise


# ──── Monthly allocation gate ────
# The allocation for month N is claimed via player_month_actions, reusing the same
# atomic unique-violation claim that protects optional-choice purchases. That gives
# idempotency for free and needs no extra state on player_state.
def allocation_key(month: int) -> str:
    return f"alloc:{month}"


def allocation_done(user_id: str, month: int) -> bool:
    return action_done(user_id, month, allocation_key(month))


# Backwards-compatible wrappers for optional-choice purchases.
def already_bought(user_id: str, month: int, choice_id: int) -> bool:
    return action_done(user_id, month, f"choice:{choice_id}")


def mark_bought(user_id: str, month: int, choice_id: int) -> bool:
    return mark_action(user_id, month, f"choice:{choice_id}")


# ──── RPC Payload Validator ────
PLAYER_STATE_REQUIRED = {
    'user_id', 'month', 'cash', 'stocks', 'gold',
    'emergency_fund', 'lifestyle_type', 'bike_status',
    'loans', 'pending_cash_next_month', 'bike_lock_in_months',
    'net_worth', 'discipline_score', 'financial_health_score', 'status',
    'trust_score', 'risk_level', 'spouse_archetype', 'spouse_satisfaction',
    'household_expense_modifier', 'insurance_plan'
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


# ════════════════════════════════════════════════════════════════════════════
# A-01 — ATOMIC PLAYER MUTATION (row-serialised)
# One primitive for every cash-mutating route. Wraps public.player_apply_atomic,
# which locks the player row FOR UPDATE, re-checks affordability under the lock,
# and applies ADDITIVE deltas so concurrent different actions compose correctly.
# Economic formulas stay in the Python callers; this only serialises the apply.
# ════════════════════════════════════════════════════════════════════════════
_TXN_ERROR_KINDS = ('DUPLICATE_ACTION', 'INSUFFICIENT_CASH', 'PLAYER_NOT_FOUND',
                    'TURN_NOT_PLAYABLE', 'MARRIAGE_NOT_AVAILABLE',
                    'ALLOCATION_REQUIRED', 'MARRIAGE_DECISION_REQUIRED',
                    'NEGOTIATION_NOT_AVAILABLE', 'PENDING_NEGOTIATION_REQUIRED')


class PlayerTxnError(Exception):
    """Raised for an expected, mapped failure from player_apply_atomic."""
    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def _txn_error_kind(exc: Exception) -> str | None:
    text = (str(getattr(exc, 'message', '') or '') + ' ' + str(exc)).upper()
    for k in _TXN_ERROR_KINDS:
        if k in text:
            return k
    return None


def apply_player_txn(user_id: str, month: int, *, action_key: str | None = None,
                     require_cash: float | None = None, deltas: dict | None = None,
                     sets: dict | None = None, clamp_satisfaction: bool = False,
                     recompute_networth: bool = False,
                     loan_inserts: list | None = None,
                     loan_updates: list | None = None,
                     expected_investment_portfolio: dict | None = None) -> dict:
    """
    Apply an atomic, row-serialised mutation to a player. Returns the fresh
    player_state row (dict). Raises PlayerTxnError(kind) for the three expected
    failures (DUPLICATE_ACTION / INSUFFICIENT_CASH / PLAYER_NOT_FOUND); any other
    exception propagates unchanged.
    """
    try:
        res = supabase.rpc('player_apply_atomic', {
            'p_user_id': user_id,
            'p_month': int(month),
            'p_action_key': action_key,
            'p_require_cash': require_cash,
            'p_deltas': deltas or {},
            'p_sets': sets or {},
            'p_clamp_satisfaction': bool(clamp_satisfaction),
            'p_recompute_networth': bool(recompute_networth),
            'p_loan_inserts': loan_inserts or [],
            'p_loan_updates': loan_updates or [],
            'p_expected_investment_portfolio': expected_investment_portfolio,
        }).execute()
    except Exception as e:
        kind = _txn_error_kind(e)
        if kind:
            raise PlayerTxnError(kind)
        raise
    return res.data


# ════════════════════════════════════════════════════════════════════════════
# A-02 — ONE authoritative "may this player mutate now?" rule.
# A player may act only when the game is ACTIVE and their own turn is not locked
# ('waiting'). While a month is being processed the admin sets game_status to
# 'processing', which this rejects — so no player action can be silently
# overwritten by the monthly result.
# ════════════════════════════════════════════════════════════════════════════
def require_playable(user_id: str):
    """Returns (player, game, None) if the player may mutate, else (None, None, (msg, code))."""
    game = get_game_state()
    if not game:
        return None, None, ("Game control not found.", 500)
    gstatus = game.get('game_status')
    if gstatus == 'processing':
        return None, None, ("The month is being processed — try again in a moment.", 409)
    if gstatus != 'active':
        return None, None, ("Game is not currently active.", 400)
    player = get_player(user_id)
    if not player:
        return None, None, ("No player state found.", 404)
    if player.get('status') == 'waiting':
        return None, None, ("Your turn is locked. Wait for the next month.", 400)
    return player, game, None
