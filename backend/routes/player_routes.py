# =============================================================================
# PLAYER ROUTES — All player-facing API endpoints
# =============================================================================

from flask import Blueprint, request, jsonify
from supabase_client import supabase
from services.auth_service import get_user_id
from services.game_service import (
    get_game_state, get_player, get_total_loans,
    get_optional_choices, get_trust_scores, get_all_event_logs,
    get_pending_sales, fair_roll, already_bought, mark_bought
)
from models.constants import (
    INITIAL_BUDGET, SELL_PENALTY_RATE, TRUST_HELP_AMOUNTS, TRUST_SCORE_GAIN
)

player_bp = Blueprint('player', __name__)


# ──────────────────────────────────────────────
# GAME STATUS
# ──────────────────────────────────────────────
@player_bp.route('/game-status', methods=['GET'])
def get_status():
    game = get_game_state()
    return jsonify(game)


# ──────────────────────────────────────────────
# CASE STUDY
# ──────────────────────────────────────────────
@player_bp.route('/case-study', methods=['GET'])
def get_case_study():
    res = supabase.table('case_study').select('*').limit(1).execute()
    return jsonify(res.data[0] if res.data else {})


# ──────────────────────────────────────────────
# MONTH 1 ALLOCATION
# Backend validates total = ₹1,00,000
# ──────────────────────────────────────────────
@player_bp.route('/allocate', methods=['POST'])
def allocate_month1():
    user_id = get_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    game = get_game_state()
    if not game or game['game_status'] != 'active':
        return jsonify({"error": "Game is not currently active."}), 400

    # Check if player already allocated
    existing = get_player(user_id)
    if existing:
        return jsonify({"error": "You have already allocated for this game."}), 400

    data = request.json
    try:
        fields = ['rent', 'transport', 'food', 'family', 'stocks',
                   'gold', 'emergency_fund', 'misc', 'bike_down_payment']
        total = sum(float(data.get(f, 0)) for f in fields)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numerical data."}), 400

    if abs(total - INITIAL_BUDGET) > 0.1:
        return jsonify({
            "error": f"Must allocate exactly ₹{INITIAL_BUDGET:,}. Current total: ₹{total:,.0f}"
        }), 400

    cash = float(data.get('misc', 0))
    bike_status = bool(data.get('bike_status', False))
    lifestyle = data.get('lifestyle_type', 'city')

    if lifestyle not in ('city', 'outer'):
        return jsonify({"error": "Invalid lifestyle type. Must be 'city' or 'outer'."}), 400

    stocks = float(data.get('stocks', 0))
    gold_val = float(data.get('gold', 0))
    emergency = float(data.get('emergency_fund', 0))

    # Validate no negative values
    if any(v < 0 for v in [cash, stocks, gold_val, emergency]):
        return jsonify({"error": "Allocation values cannot be negative."}), 400

    new_state = {
        "user_id": user_id,
        "month": 1,
        "cash": cash,
        "stocks": stocks,
        "gold": gold_val,
        "emergency_fund": emergency,
        "lifestyle_type": lifestyle,
        "bike_status": bike_status,
        "bike_lock_in_months": 3 if bike_status else 0,
        "loans": 0,
        "pending_cash_next_month": 0,
        "net_worth": INITIAL_BUDGET,
        "trust_score": 0,
        "risk_level": 50,
        "status": "waiting"
    }

    supabase.table('player_state').upsert(new_state).execute()
    supabase.table('player_month_log').insert({
        "user_id": user_id,
        "month": 1,
        "starting_cash": INITIAL_BUDGET,
        "ending_cash": cash,
        "net_worth": INITIAL_BUDGET,
        "summary": "💼 Initial Allocation Completed. Your financial journey begins!"
    }).execute()

    return jsonify({
        "message": "Month 1 allocation confirmed. Your turn is locked.",
        "state": new_state
    })


# ──────────────────────────────────────────────
# DASHBOARD — Full player state + event history
# ──────────────────────────────────────────────
@player_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    user_id = get_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    player = get_player(user_id)
    if not player:
        return jsonify({"error": "No player state found"}), 404

    player['loans'] = get_total_loans(user_id)
    game = get_game_state()
    choices = get_optional_choices(player['month'])
    trust_scores = get_trust_scores(user_id)
    event_logs = get_all_event_logs(user_id)

    return jsonify({
        "player": player,
        "game": game,
        "choices": choices,
        "trust_scores": trust_scores,
        "event_logs": event_logs
    })


# ──────────────────────────────────────────────
# LOCK TURN — Player confirms they're done
# ──────────────────────────────────────────────
@player_bp.route('/lock-turn', methods=['POST'])
def lock_turn():
    user_id = get_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    supabase.table('player_state').update({
        'status': 'waiting'
    }).eq('user_id', user_id).execute()

    return jsonify({"message": "Turn confirmed. Waiting for next month to be processed."})


# ──────────────────────────────────────────────
# SELL ASSET
# 10% penalty, cash credited next month
# ──────────────────────────────────────────────
@player_bp.route('/sell', methods=['POST'])
def sell_asset():
    user_id = get_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    asset_type = data.get('asset')
    amount_to_sell = float(data.get('amount', 0))

    if asset_type not in ('stocks', 'gold', 'emergency_fund'):
        return jsonify({"error": "Invalid asset type. Must be stocks, gold, or emergency_fund."}), 400

    if amount_to_sell <= 0:
        return jsonify({"error": "Amount must be positive."}), 400

    player = get_player(user_id)
    if not player:
        return jsonify({"error": "Player state not found"}), 404

    if player.get('status') == 'waiting':
        return jsonify({"error": "Your turn is locked. Wait for next month."}), 400

    current_val = float(player.get(asset_type, 0))
    if amount_to_sell > current_val:
        return jsonify({"error": f"Insufficient {asset_type} balance. You have ₹{current_val:,.0f}"}), 400

    # Bike lock-in check
    if asset_type == 'emergency_fund' and player.get('bike_lock_in_months', 0) > 0:
        # Allow but warn
        pass

    penalty = amount_to_sell * SELL_PENALTY_RATE
    receive_val = amount_to_sell - penalty

    new_val = current_val - amount_to_sell
    supabase.table('player_state').update({
        asset_type: new_val
    }).eq('user_id', user_id).execute()

    supabase.table('player_sales').insert({
        "user_id": user_id,
        "asset_type": asset_type,
        "amount_sold": amount_to_sell,
        "penalty": penalty,
        "cash_to_receive": receive_val,
        "month_sold_in": player['month'],
        "month_to_credit": player['month'] + 1
    }).execute()

    return jsonify({
        "message": f"Sold ₹{amount_to_sell:,.0f} of {asset_type}. After {SELL_PENALTY_RATE*100:.0f}% penalty, ₹{receive_val:,.0f} will be credited next month.",
        "penalty": penalty,
        "credited_next_month": receive_val
    })


# ──────────────────────────────────────────────
# BUY OPTIONAL CHOICE
# ──────────────────────────────────────────────
@player_bp.route('/buy-choice', methods=['POST'])
def buy_choice():
    user_id = get_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    player = get_player(user_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    if player.get('status') == 'waiting':
        return jsonify({"error": "Your turn is locked. Wait for next month."}), 400

    from services.choice_service import execute_choice
    result = execute_choice(player, request.json.get('choice_id'))

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ──────────────────────────────────────────────
# HANDLE RELATIVE / SOCIAL EVENT
# ──────────────────────────────────────────────
@player_bp.route('/handle-relative', methods=['POST'])
def handle_relative():
    user_id = get_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    relative_type = data.get('relative_type')
    action = data.get('action', 'none')

    if action not in ('none', 'medium', 'high'):
        return jsonify({"error": "Invalid action."}), 400

    player = get_player(user_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    if player.get('status') == 'waiting':
        return jsonify({"error": "Your turn is locked."}), 400

    cost = TRUST_HELP_AMOUNTS.get(action, 0)
    trust_gain = TRUST_SCORE_GAIN.get(action, 0)

    cash = float(player['cash'])
    if cost > 0 and cash < cost:
        return jsonify({"error": f"Not enough cash. Need ₹{cost:,} but have ₹{cash:,.0f}"}), 400

    if cost > 0:
        cash -= cost
        supabase.table('player_state').update({'cash': cash}).eq('user_id', user_id).execute()

    # Update relative trust score
    existing = supabase.table('player_relative_score').select('*').eq('user_id', user_id).eq('relative_type', relative_type).execute()
    if existing.data:
        current_trust = int(existing.data[0].get('trust_score', 0))
        current_spent = float(existing.data[0].get('total_spent', 0))
        supabase.table('player_relative_score').update({
            'trust_score': current_trust + trust_gain,
            'total_spent': current_spent + cost
        }).eq('user_id', user_id).eq('relative_type', relative_type).execute()
    else:
        supabase.table('player_relative_score').insert({
            'user_id': user_id,
            'relative_type': relative_type,
            'trust_score': trust_gain,
            'total_spent': cost
        }).execute()

    # Log the action
    supabase.table('player_relative_actions').insert({
        'user_id': user_id,
        'month': player['month'],
        'relative_type': relative_type,
        'action_taken': action,
        'amount_spent': cost
    }).execute()

    # Update overall trust score in player state
    all_trust = supabase.table('player_relative_score').select('trust_score').eq('user_id', user_id).execute()
    total_trust = sum(int(t.get('trust_score', 0)) for t in (all_trust.data or []))
    supabase.table('player_state').update({'trust_score': total_trust}).eq('user_id', user_id).execute()

    if action == 'none':
        return jsonify({"message": f"You chose not to help. No trust gained.", "trust_change": 0})
    else:
        return jsonify({
            "message": f"Helped {relative_type} relative ({action}). Spent ₹{cost:,}. Trust +{trust_gain}.",
            "trust_change": trust_gain,
            "amount_spent": cost
        })


# ──────────────────────────────────────────────
# LEADERBOARD
# ──────────────────────────────────────────────
@player_bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    from services.game_service import get_leaderboard
    data = get_leaderboard()
    return jsonify(data)


# ──────────────────────────────────────────────
# EVENT HISTORY — Get all logs for the player
# ──────────────────────────────────────────────
@player_bp.route('/event-history', methods=['GET'])
def event_history():
    user_id = get_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    logs = get_all_event_logs(user_id)
    return jsonify({"logs": logs})
