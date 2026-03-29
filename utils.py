import hashlib
from collections import defaultdict
from supabase_client import supabase

# ---------------------------------------------------------------------------
# FAIR PROBABILITY ENGINE
# ---------------------------------------------------------------------------
def fair_roll(user_id: str, month: int, choice_id: int, probability: int) -> bool:
    """Deterministic RNG per player+month+choice for fairness."""
    seed_str = f"{user_id}:{month}:{choice_id}"
    digest = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    roll = (digest % 100) + 1
    return roll <= probability

# ---------------------------------------------------------------------------
# PURCHASE TRACKING (Rate-limiting in-process)
# ---------------------------------------------------------------------------
_rate_limit: dict = defaultdict(set)

def _rl_key(user_id: str, month: int) -> str:
    return f"{user_id}:{month}"

def _already_bought(user_id: str, month: int, choice_id: int) -> bool:
    return choice_id in _rate_limit[_rl_key(user_id, month)]

def _mark_bought(user_id: str, month: int, choice_id: int):
    _rate_limit[_rl_key(user_id, month)].add(choice_id)

# ---------------------------------------------------------------------------
# AUTH & HELPERS
# ---------------------------------------------------------------------------
def get_uid(req) -> str | None:
    """Extracts user_id from Bearer token via Supabase Auth."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header.split(" ")[1]
    try:
        user_res = supabase.auth.get_user(token)
        return user_res.user.id
    except Exception as e:
        print(f"Auth error: {e}")
        return None

def get_game_state():
    res = supabase.table('game_control').select('*').limit(1).execute()
    return res.data[0] if res.data else None

def get_player(user_id):
    res = supabase.table('player_state').select('*').eq('user_id', user_id).execute()
    return res.data[0] if res.data else None

def get_total_loans(user_id):
    res = supabase.table('player_loans').select('current_amount').eq('user_id', user_id).eq('status', 'active').execute()
    return sum([float(r['current_amount']) for r in res.data])

# ---------------------------------------------------------------------------
# RPC PAYLOAD VALIDATOR
# ---------------------------------------------------------------------------
PLAYER_STATE_REQUIRED = {
    'user_id', 'month', 'cash', 'stocks', 'gold',
    'emergency_fund', 'lifestyle_type', 'bike_status',
    'loans', 'pending_cash_next_month', 'bike_lock_in_months',
    'net_worth', 'status'
}
LOAN_UPDATE_REQUIRED = {'id', 'user_id', 'principal', 'current_amount', 'interest_rate', 'month_taken', 'status'}
LOAN_INSERT_REQUIRED = {'user_id', 'principal', 'current_amount', 'interest_rate', 'month_taken', 'status'}
LOG_REQUIRED = {'user_id', 'month', 'starting_cash', 'ending_cash', 'net_worth', 'summary'}

def validate_rpc_payload(
    updates_player_state, updates_loans, inserts_loans, inserts_logs
) -> str | None:
    for i, rec in enumerate(updates_player_state):
        missing = PLAYER_STATE_REQUIRED - set(rec.keys())
        if missing: return f"updates_player_state[{i}] missing fields: {missing}"
    for i, rec in enumerate(updates_loans):
        missing = LOAN_UPDATE_REQUIRED - set(rec.keys())
        if missing: return f"updates_loans[{i}] missing fields: {missing}"
    for i, rec in enumerate(inserts_loans):
        missing = LOAN_INSERT_REQUIRED - set(rec.keys())
        if missing: return f"inserts_loans[{i}] missing fields: {missing}"
    for i, rec in enumerate(inserts_logs):
        missing = LOG_REQUIRED - set(rec.keys())
        if missing: return f"inserts_logs[{i}] missing fields: {missing}"
    return None
