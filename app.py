import os
import random
import hashlib
from collections import defaultdict
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

url = os.environ.get("SUPABASE_URL", "")
key = os.environ.get("SUPABASE_SERVICE_KEY", "")
supabase: Client = create_client(url, key)

# ---------------------------------------------------------------------------
# FAIR PROBABILITY ENGINE
# Goal: user outcomes feel balanced across a cohort, not pure luck.
# Method: seed RNG from hash(user_id + month + choice_id) so the same
#         player+month+choice always yields the SAME result (reproducible),
#         while different players get independently varied outcomes.
# ---------------------------------------------------------------------------
def fair_roll(user_id: str, month: int, choice_id: int, probability: int) -> bool:
    """
    Returns True if the player wins the optional choice reward.
    Deterministic per (user, month, choice) — fair and auditable.
    """
    seed_str = f"{user_id}:{month}:{choice_id}"
    digest = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
    roll = (digest % 100) + 1   # 1 – 100, uniform distribution
    return roll <= probability

# ---------------------------------------------------------------------------
# RATE-LIMIT MAP  {user_id: set of choice_ids bought this month}
# Resets automatically when game advances (month counter changes).
# For a college event this in-process map is sufficient.
# ---------------------------------------------------------------------------
_rate_limit: dict = defaultdict(set)   # {"uid:month" -> set(choice_id)}

def _rl_key(user_id: str, month: int) -> str:
    return f"{user_id}:{month}"

def _already_bought(user_id: str, month: int, choice_id: int) -> bool:
    return choice_id in _rate_limit[_rl_key(user_id, month)]

def _mark_bought(user_id: str, month: int, choice_id: int):
    _rate_limit[_rl_key(user_id, month)].add(choice_id)

# ---------------------------------------------------------------------------
# RPC PAYLOAD VALIDATOR
# Catches any missing / wrong-typed fields BEFORE hitting Postgres.
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

def _validate_rpc_payload(
    updates_player_state, updates_loans, inserts_loans, inserts_logs
) -> str | None:
    """Returns an error string if invalid, else None."""
    for i, rec in enumerate(updates_player_state):
        missing = PLAYER_STATE_REQUIRED - set(rec.keys())
        if missing:
            return f"updates_player_state[{i}] missing fields: {missing}"
    for i, rec in enumerate(updates_loans):
        missing = LOAN_UPDATE_REQUIRED - set(rec.keys())
        if missing:
            return f"updates_loans[{i}] missing fields: {missing}"
    for i, rec in enumerate(inserts_loans):
        missing = LOAN_INSERT_REQUIRED - set(rec.keys())
        if missing:
            return f"inserts_loans[{i}] missing fields: {missing}"
    for i, rec in enumerate(inserts_logs):
        missing = LOG_REQUIRED - set(rec.keys())
        if missing:
            return f"inserts_logs[{i}] missing fields: {missing}"
    return None

def get_uid(req) -> str | None:
    """Extracts user_id from Bearer token via Supabase Auth."""
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        # Fallback for old clients or debugging - actually let's be strict
        return None
    
    token = auth_header.split(" ")[1]
    try:
        # This call verifies the JWT with Supabase
        user_res = supabase.auth.get_user(token)
        return user_res.user.id
    except Exception as e:
        print(f"Auth error: {e}")
        return None

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Backend running"})

@app.route('/', methods=['GET'])
def index():
    return "Backend is running successfully"

def get_game_state():
    res = supabase.table('game_control').select('*').limit(1).execute()
    return res.data[0] if res.data else None

def get_player(user_id):
    res = supabase.table('player_state').select('*').eq('user_id', user_id).execute()
    return res.data[0] if res.data else None

def get_total_loans(user_id):
    res = supabase.table('player_loans').select('current_amount').eq('user_id', user_id).eq('status', 'active').execute()
    return sum([float(r['current_amount']) for r in res.data])

@app.route('/game-status', methods=['GET'])
def get_status():
    game = get_game_state()
    return jsonify(game)

@app.route('/case-study', methods=['GET'])
def get_case_study():
    res = supabase.table('case_study').select('*').limit(1).execute()
    return jsonify(res.data[0] if res.data else {})

@app.route('/allocate', methods=['POST'])
def allocate_month1():
    user_id = get_uid(request)
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    
    game = get_game_state()
    if game['game_status'] != 'active':
        return jsonify({"error": "Game is not currently active."}), 400

    data = request.json
    total = sum([
        float(data.get('rent', 0)),
        float(data.get('transport', 0)),
        float(data.get('food', 0)),
        float(data.get('family', 0)),
        float(data.get('stocks', 0)),
        float(data.get('gold', 0)),
        float(data.get('emergency_fund', 0)),
        float(data.get('misc', 0)),
        float(data.get('bike_down_payment', 0))
    ])
    
    if total != 100000:
        return jsonify({"error": f"Must allocate exactly ₹1,00,000. Current total: {total}"}), 400

    cash = float(data.get('misc', 0))
    bike_status = bool(data.get('bike_status', False))
    
    new_state = {
        "user_id": user_id,
        "month": 1,
        "cash": cash,
        "stocks": float(data.get('stocks', 0)),
        "gold": float(data.get('gold', 0)),
        "emergency_fund": float(data.get('emergency_fund', 0)),
        "lifestyle_type": data.get('lifestyle_type', 'city'),
        "bike_status": bike_status,
        "bike_lock_in_months": 3 if bike_status else 0,
        "loans": 0,
        "pending_cash_next_month": 0,
        "net_worth": 100000,
        "status": "waiting"
    }
    
    supabase.table('player_state').upsert(new_state).execute()
    
    supabase.table('player_month_log').insert({
        "user_id": user_id, "month": 1, "starting_cash": 100000, "ending_cash": cash,
        "net_worth": 100000, "summary": "Initial Allocation Completed."
    }).execute()
    
    return jsonify({"message": "Month 1 allocation confirmed. Turn locked."})

@app.route('/dashboard', methods=['GET'])
def get_dashboard():
    user_id = get_uid(request)
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    
    player = get_player(user_id)
    if not player: return jsonify({"error": "No player state found"}), 404
        
    player['loans'] = get_total_loans(user_id) # Realtime aggregate
    
    game = get_game_state()
    
    opts = supabase.table('optional_choices').select('*').eq('month', player['month']).execute()
    choices = opts.data if opts.data else []
    
    return jsonify({"player": player, "game": game, "choices": choices})

@app.route('/lock-turn', methods=['POST'])
def lock_turn():
    user_id = get_uid(request)
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    
    player = get_player(user_id)
    if not player: return jsonify({"error": "No player found"}), 404
    
    if player['status'] == 'waiting':
        return jsonify({"error": "Turn already locked."}), 400
        
    supabase.table('player_state').update({'status': 'waiting'}).eq('user_id', user_id).execute()
    return jsonify({"message": "Turn locked successfully."})

@app.route('/choice', methods=['POST'])
def make_choice():
    user_id = get_uid(request)
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    
    game = get_game_state()
    if game['game_status'] != 'active':
         return jsonify({"error": "Game is not active."}), 400
         
    player = get_player(user_id)
    if not player: return jsonify({"error": "Player not found"}), 404
    if player['status'] == 'waiting': return jsonify({"error": "Your turn is locked."}), 400
         
    data = request.json
    c_type = data.get('type')
    current_m = player['month']

    if c_type == 'sell_asset':
        asset = data.get('asset')
        amount = float(data.get('amount', 0))
        
        if asset not in ['stocks', 'gold']: return jsonify({"error": "Invalid asset"}), 400
        if player[asset] < amount: return jsonify({"error": f"Not enough {asset}"}), 400
             
        penalty = amount * 0.05
        net_cash = amount - penalty
        
        supabase.table('player_sales').insert({
             "user_id": user_id, "asset_type": asset, "amount_sold": amount,
             "penalty": penalty, "cash_to_receive": net_cash,
             "month_sold_in": current_m, "month_to_credit": current_m + 1
        }).execute()
        
        new_asset = player[asset] - amount
        new_pend = player['pending_cash_next_month'] + net_cash
        
        supabase.table('player_state').update({asset: new_asset, 'pending_cash_next_month': new_pend}).eq('user_id', user_id).execute()
        return jsonify({"message": f"Sold ₹{amount} of {asset}. ₹{net_cash} drops NEXT month."})
        
    elif c_type == 'relative':
        rel_type = data.get('relative_type')
        action = data.get('action') 
        spent = 0; trust_gained = 0
        
        if action == 'medium': spent = 2000; trust_gained = 5
        elif action == 'high': spent = 5000; trust_gained = 10
            
        supabase.table('player_relative_actions').insert({
             "user_id": user_id, "month": current_m, "relative_type": rel_type,
             "action_taken": action, "amount_spent": spent
        }).execute()
             
        if spent > 0:
             cash = player['cash']
             if cash >= spent:
                 cash -= spent
             else:
                 shortfall = spent - cash
                 supabase.table('player_loans').insert({
                     "user_id": user_id, "principal": shortfall, "current_amount": shortfall,
                     "interest_rate": 0.12, "month_taken": current_m
                 }).execute()
                 cash = 0
                 
             s_res = supabase.table('player_relative_score').select('*').eq('user_id', user_id).eq('relative_type', rel_type).execute()
             if s_res.data:
                 new_trust = s_res.data[0]['trust_score'] + trust_gained
                 new_total = float(s_res.data[0]['total_spent']) + spent
                 supabase.table('player_relative_score').update({'trust_score': new_trust, 'total_spent': new_total}).eq('user_id', user_id).eq('relative_type', rel_type).execute()
             else:
                 supabase.table('player_relative_score').insert({'user_id': user_id, 'relative_type': rel_type, 'trust_score': trust_gained, 'total_spent': spent}).execute()
                 
             supabase.table('player_state').update({'cash': cash}).eq('user_id', user_id).execute()
             
        return jsonify({"message": f"Tracked ({rel_type}) interaction."})
        
    elif c_type == 'optional':
        choice_id = data.get('id')
        if not choice_id:
            return jsonify({"error": "Missing choice id"}), 400
        choice_id = int(choice_id)

        # --- RATE LIMIT: one purchase per choice per month ---
        if _already_bought(user_id, current_m, choice_id):
            return jsonify({"error": "You already purchased this choice this month."}), 429

        opt_res = supabase.table('optional_choices').select('*').eq('id', choice_id).execute()
        if not opt_res.data: return jsonify({"error": "Choice not found"}), 404

        opt = opt_res.data[0]
        cost = float(opt['cost'])

        cash = player['cash']
        if cash >= cost:
            cash -= cost
        else:
            shortfall = cost - cash
            supabase.table('player_loans').insert({
                 "user_id": user_id, "principal": shortfall, "current_amount": shortfall,
                 "interest_rate": 0.12, "month_taken": current_m
            }).execute()
            cash = 0

        # --- FAIR PROBABILITY ENGINE (deterministic, auditable) ---
        msg = f"Purchased {opt['name']} for ₹{cost}."
        if fair_roll(user_id, current_m, choice_id, int(opt['probability'])):
            val = float(opt['reward_value'])
            tgt = opt['reward_type']
            if tgt == 'cash':
                cash += val
            elif tgt == 'stocks':
                supabase.table('player_state').update(
                    {'stocks': player['stocks'] + val}
                ).eq('user_id', user_id).execute()
            elif tgt == 'gold':
                supabase.table('player_state').update(
                    {'gold': player['gold'] + val}
                ).eq('user_id', user_id).execute()
            msg += f" 🎉 Reward Triggered! Gained ₹{val} in {tgt}."
        else:
            msg += " No reward this time. Better luck next opportunity!"

        # Mark bought AFTER all DB writes succeed
        supabase.table('player_state').update({'cash': cash}).eq('user_id', user_id).execute()
        _mark_bought(user_id, current_m, choice_id)
        return jsonify({"message": msg})
        
    return jsonify({"error": "Invalid Choice"}), 400

@app.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    res = supabase.table('player_state').select('user_id, net_worth, users(name)').order('net_worth', desc=True).limit(50).execute()
    return jsonify(res.data)

# --- ADMIN ENDPOINTS ---

@app.route('/start-game', methods=['POST'])
def start_game():
    supabase.table('game_control').update({'current_month': 1, 'game_status': 'active'}).eq('id', 1).execute()
    supabase.table('player_state').update({'status': 'active'}).neq('user_id', '00000000-0000-0000-0000-000000000000').execute()
    return jsonify({"message": "Game active. Go!"})

@app.route('/next-month', methods=['POST'])
def next_month():
    req = request.json or {}
    exp_month = req.get('expected_month')
    
    game = get_game_state()
    curr_m = game['current_month']
    
    if exp_month is not None and int(exp_month) != curr_m:
         return jsonify({"error": f"Race Condition Blocked. System is on month {curr_m}."}), 409
    if game['game_status'] != 'active':
         return jsonify({"error": f"Game is '{game['game_status']}'. Processing locked."}), 409

    # Transaction Lock
    lock = supabase.table('game_control').update({'game_status': 'processing'}).eq('id', 1).eq('game_status', 'active').execute()
    if len(lock.data) == 0:
         return jsonify({"error": "Failed to acquire transition lock. Already processing."}), 409
         
    if curr_m >= 12:
         supabase.table('game_control').update({'game_status': 'ended'}).eq('id', 1).execute()
         return jsonify({"message": "Month 12 completed. Game is officially ended."})
         
    next_m = curr_m + 1
    
    # ---------------------------------------------------------
    # 1. BULK FETCH (O(1) Queries) - Eliminating N+1 timeouts
    # ---------------------------------------------------------
    players_res = supabase.table('player_state').select('*').execute()
    case_study = supabase.table('case_study').select('*').limit(1).execute().data[0]
    events = supabase.table('events').select('*').eq('month', next_m).execute().data
    
    sales_res = supabase.table('player_sales').select('*').eq('month_to_credit', next_m).execute()
    loans_res = supabase.table('player_loans').select('*').eq('status', 'active').execute()
    
    rels_data = []
    if curr_m == 8 and next_m == 9: # Only needed for Month 9 Return Phase
         rels_res = supabase.table('player_relative_score').select('*').execute()
         rels_data = rels_res.data
         
    # Grouping into dictionaries
    sales_dict = {}; loans_dict = {}; rels_dict = {}
    for s in sales_res.data:
        sales_dict.setdefault(s['user_id'], []).append(s)
    for l in loans_res.data:
        loans_dict.setdefault(l['user_id'], []).append(l)
    for r in rels_data:
        rels_dict.setdefault(r['user_id'], []).append(r)

    base_rent = float(case_study.get('rent', 0))
    base_food = float(case_study.get('food', 0))
    base_trans = float(case_study.get('transport', 0))
    base_fam = float(case_study.get('family', 0))
    monthly_income = 100000

    # ---------------------------------------------------------
    # 2. IN-MEMORY COMPUTATION (Zero Network Calls)
    # ---------------------------------------------------------
    updates_player_state = []
    updates_loans = []
    inserts_loans = []
    inserts_logs = []

    for p in players_res.data:
         uid = p['user_id']
         cash = float(p['cash'])
         start_cash = cash
         stocks = float(p['stocks'])
         gold = float(p['gold'])
         emergency = float(p['emergency_fund'])
         
         summary_logs = []
         
         cash += monthly_income
         summary_logs.append(f"+{monthly_income} Monthly Income.")
         
         # Expenses
         lifestyle = p['lifestyle_type']
         r = 25000 if lifestyle == 'city' else 10000
         t = 2000 if lifestyle == 'city' else 10000
         
         expenses = base_food + base_fam + r
         bike_m = p['bike_lock_in_months']
         if p['bike_status']:
             expenses += 5000
             t *= 0.5
             if bike_m > 0: bike_m -= 1
         expenses += t
         cash -= expenses
         summary_logs.append(f"-{expenses} Living Expenses.")
         
         # Sales credits
         user_sales = sales_dict.get(uid, [])
         total_sales = sum([float(s['cash_to_receive']) for s in user_sales])
         if total_sales > 0:
             cash += total_sales
             summary_logs.append(f"+{total_sales} from Sales.")
             
         # Global Events
         for ev in events:
             val = float(ev['value'])
             tgt = ev['impact_target']
             etype = ev['event_type']
             if etype == 'percentage':
                 mult = 1.0 + (val/100.0)
                 if tgt == 'stocks': stocks *= mult
                 elif tgt == 'gold': gold *= mult
                 elif tgt == 'cash': cash *= mult
             elif etype == 'fixed':
                 if tgt == 'cash': cash += val
                 elif tgt == 'stocks': stocks += val
                 elif tgt == 'gold': gold += val
                 elif tgt == 'expense_increase': cash -= val
             summary_logs.append(f"Global Event '{ev['event_name']}' applied.")
                 
         # Month 9 Return Phase
         if curr_m == 8 and next_m == 9:
             user_rels = rels_dict.get(uid, [])
             total_ret = 0
             for r_data in user_rels:
                 tst = int(r_data['trust_score'])
                 if tst > 0:
                     spent = float(r_data['total_spent'])
                     rtype = r_data['relative_type']
                     # Provide a balanced pseudo-random return
                     if rtype == 'poor': ret = spent * random.uniform(1.2, 1.8)
                     elif rtype == 'rich': ret = spent * random.uniform(0.2, 0.6)
                     else: ret = spent * 1.0
                     total_ret += ret
             if total_ret > 0:
                 cash += total_ret
                 summary_logs.append(f"+{total_ret:.2f} Relative Trust Return.")
                 
         # Process Proper Loan Tracking Defaults
         user_loans = loans_dict.get(uid, [])
         player_total_loan_balance = 0
         
         for l in user_loans:
             c_amt = float(l['current_amount'])
             int_rate = float(l['interest_rate'])
             c_amt = c_amt * (1.0 + int_rate) # Add monthly interest
             
             new_status = 'active'
             if cash >= c_amt:
                 cash -= c_amt
                 c_amt = 0; new_status = 'paid'
             elif cash > 0:
                 c_amt -= cash
                 cash = 0
                 
             updates_loans.append({
                 'id': l['id'], 'user_id': uid, 'principal': l['principal'],
                 'current_amount': c_amt, 'interest_rate': int_rate,
                 'month_taken': l['month_taken'], 'status': new_status
             })
             player_total_loan_balance += c_amt
         
         # Fallback negative cash check
         if cash < 0:
             shortfall = abs(cash)
             inserts_loans.append({
                 "user_id": uid, "principal": shortfall, "current_amount": shortfall,
                 "interest_rate": 0.12, "month_taken": next_m, "status": 'active'
             })
             summary_logs.append(f"Negative balance shifted to instant loan: {shortfall}.")
             player_total_loan_balance += shortfall
             cash = 0
             
         nw = cash + stocks + gold + emergency - player_total_loan_balance
         
         updates_player_state.append({
             'user_id': uid, 'month': next_m, 'cash': cash, 'stocks': stocks, 'gold': gold,
             'emergency_fund': emergency, 'lifestyle_type': lifestyle,
             'bike_status': p['bike_status'], 'loans': 0, 'pending_cash_next_month': 0, 
             'bike_lock_in_months': bike_m, 'net_worth': nw, 'status': 'active'
         })
         
         inserts_logs.append({
             "user_id": uid, "month": next_m, "starting_cash": start_cash, "ending_cash": cash,
             "net_worth": nw, "summary": " | ".join(summary_logs)
         })

    # ---------------------------------------------------------
    # 3. VALIDATE PAYLOAD (before any DB write)
    # ---------------------------------------------------------
    validation_error = _validate_rpc_payload(
        updates_player_state, updates_loans, inserts_loans, inserts_logs
    )
    if validation_error:
        # Safe to unlock — nothing was written yet
        supabase.table('game_control').update({'game_status': 'active'}).eq('id', 1).execute()
        return jsonify({"error": f"Payload validation failed: {validation_error}"}), 422

    # ---------------------------------------------------------
    # 4. SINGLE ATOMIC RPC CALL (True Postgres Transaction)
    # ---------------------------------------------------------
    try:
        rpc_payload = {
            "p_updates_player_state": updates_player_state,
            "p_updates_loans": updates_loans,
            "p_inserts_loans": inserts_loans,
            "p_inserts_logs": inserts_logs,
            "p_next_month": next_m
        }
        supabase.rpc('process_month_atomically', rpc_payload).execute()
        return jsonify({"message": f"✅ Month {next_m} processed atomically for all players."})
    except Exception as e:
        # RPC raised → Postgres already rolled back. Just unlock game_control.
        supabase.table('game_control').update({'game_status': 'active'}).eq('id', 1).execute()
        error_msg = str(e)
        if 'Month already processed' in error_msg:
            return jsonify({"error": "Idempotency block: Month already processed. No changes made."}), 409
        if 'Invalid month transition' in error_msg:
            return jsonify({"error": "Month transition mismatch detected. Reload admin panel."}), 409
        return jsonify({"error": f"Transaction rolled back by Postgres: {error_msg}"}), 500

@app.route('/event', methods=['POST'])
def create_event():
    data = request.json
    res = supabase.table('events').insert(data).execute()
    return jsonify(res.data)

@app.route('/event/<int:id>', methods=['PUT', 'DELETE'])
def manage_event(id):
    if request.method == 'PUT':
        data = request.json
        res = supabase.table('events').update(data).eq('id', id).execute()
        return jsonify(res.data)
    elif request.method == 'DELETE':
        res = supabase.table('events').delete().eq('id', id).execute()
        return jsonify({"message": "Deleted"})

@app.route('/choice-admin', methods=['POST'])
def create_choice_admin():
    data = request.json
    res = supabase.table('optional_choices').insert(data).execute()
    return jsonify(res.data)

if __name__ == '__main__':
    app.run(debug=True, port=10000)
