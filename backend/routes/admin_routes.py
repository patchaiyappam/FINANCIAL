# =============================================================================
# ADMIN ROUTES — Game control, month processing, event/choice management
# Uses the modular engine for all game logic.
# =============================================================================

from flask import Blueprint, request, jsonify
from supabase_client import supabase
from services.game_service import (
    get_game_state, get_all_players, get_active_loans,
    get_admin_events_for_month, get_pending_sales, validate_rpc_payload
)
from engine.monthly_processor import process_month_for_player
from models.constants import TOTAL_MONTHS

admin_bp = Blueprint('admin', __name__)


# ──────────────────────────────────────────────
# START / RESTART GAME
# ──────────────────────────────────────────────
@admin_bp.route('/start-game', methods=['POST'])
def start_game():
    """Reset all game data and start fresh."""
    try:
        supabase.table('game_control').update({
            'current_month': 1,
            'game_status': 'active'
        }).eq('id', 1).execute()

        # Wipe all player data
        dummy = '00000000-0000-0000-0000-000000000000'
        supabase.table('player_state').delete().neq('user_id', dummy).execute()
        supabase.table('player_loans').delete().neq('user_id', dummy).execute()
        supabase.table('player_sales').delete().neq('user_id', dummy).execute()
        supabase.table('player_relative_score').delete().neq('user_id', dummy).execute()
        supabase.table('player_relative_actions').delete().neq('user_id', dummy).execute()
        supabase.table('player_month_log').delete().neq('user_id', dummy).execute()

        # Wipe events and choices
        supabase.table('events').delete().neq('id', 0).execute()
        supabase.table('optional_choices').delete().neq('id', 0).execute()

        return jsonify({"message": "Game restarted. All data wiped!"})
    except Exception as e:
        return jsonify({"error": f"Failed to start game: {e}"}), 500


# ──────────────────────────────────────────────
# NEXT MONTH — Core monthly processing using engine
# ──────────────────────────────────────────────
@admin_bp.route('/next-month', methods=['POST'])
def next_month():
    """
    Process next month for ALL players using the modular engine.
    This is the backbone of the game loop.
    """
    req = request.json or {}
    exp_month = req.get('expected_month')
    game = get_game_state()

    if not game:
        return jsonify({"error": "Game control not found."}), 500

    curr_m = game['current_month']

    # Race condition protection
    if exp_month is not None and int(exp_month) != curr_m:
        return jsonify({
            "error": f"Race condition blocked. System is on month {curr_m}."
        }), 409

    if game['game_status'] != 'active':
        return jsonify({"error": "Cannot advance — game is not active."}), 400

    next_m = curr_m + 1

    # End game after 12 months
    if curr_m >= TOTAL_MONTHS:
        supabase.table('game_control').update({
            'game_status': 'ended'
        }).eq('id', 1).execute()
        return jsonify({
            "message": f"Month {TOTAL_MONTHS} completed. Game officially ended!"
        })

    # Fetch all data
    players = get_all_players()
    if not players:
        return jsonify({"error": "No players found to process."}), 400

    admin_events = get_admin_events_for_month(next_m)

    # Accumulate batch operations
    updates_state = []
    updates_loans = []
    inserts_loans = []
    inserts_logs = []
    all_event_summaries = []

    for player in players:
        uid = player['user_id']

        # Fetch player-specific data — engine handles everything else
        active_loans = get_active_loans(uid)
        pending_sales = get_pending_sales(uid, next_m)

        # ── RUN THE ENGINE — route passes data, engine decides what to do ──
        result = process_month_for_player(
            player=player,
            month=next_m,
            admin_events=admin_events,
            active_loans=active_loans,
            pending_sales=pending_sales
        )

        # Collect batch data
        updates_state.append(result['updated_state'])

        for lu in result['loan_updates']:
            # Ensure all required fields for loan updates
            matching_loan = next((l for l in active_loans if l['id'] == lu['id']), {})
            updates_loans.append({
                "id": lu['id'],
                "user_id": uid,
                "principal": float(matching_loan.get('principal', 0)),
                "current_amount": lu['current_amount'],
                "interest_rate": float(matching_loan.get('interest_rate', 0.12)),
                "month_taken": int(matching_loan.get('month_taken', next_m)),
                "status": lu['status']
            })

        inserts_loans.extend(result['new_loans'])

        # Build log entry
        summary = " | ".join(result['event_log'])
        inserts_logs.append({
            "user_id": uid,
            "month": next_m,
            "starting_cash": result['starting_cash'],
            "ending_cash": result['ending_cash'],
            "net_worth": result['net_worth'],
            "summary": summary
        })

        # Collect event summaries for response
        for ev in result.get('events_triggered', []):
            all_event_summaries.append({
                "player": uid[:8],
                "event": ev['name'],
                "category": ev.get('category', 'unknown'),
                "value": ev['value']
            })

    # Validate the batch payload
    err = validate_rpc_payload(updates_state, updates_loans, inserts_loans, inserts_logs)
    if err:
        return jsonify({"error": f"Validation failed: {err}"}), 500

    # Execute atomically via RPC
    payload = {
        "p_updates_player_state": updates_state,
        "p_updates_loans": updates_loans,
        "p_inserts_loans": inserts_loans,
        "p_inserts_logs": inserts_logs,
        "p_next_month": next_m
    }

    try:
        supabase.rpc('process_month_atomically', payload).execute()
        return jsonify({
            "message": f"Success! Advanced to Month {next_m}.",
            "month": next_m,
            "players_processed": len(players),
            "events_triggered": len(all_event_summaries),
            "event_details": all_event_summaries[:20]  # Limit for response size
        })
    except Exception as e:
        return jsonify({"error": f"Database processing failed: {e}"}), 500


# ──────────────────────────────────────────────
# END GAME MANUALLY
# ──────────────────────────────────────────────
@admin_bp.route('/end-game', methods=['POST'])
def end_game():
    supabase.table('game_control').update({
        'game_status': 'ended'
    }).eq('id', 1).execute()
    return jsonify({"message": "Game has been ended manually."})


# ──────────────────────────────────────────────
# EVENT MANAGEMENT
# ──────────────────────────────────────────────
@admin_bp.route('/event', methods=['POST'])
def add_event():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided."}), 400
    supabase.table('events').insert(data).execute()
    return jsonify({"message": "Global event added successfully."})


@admin_bp.route('/event/<int:id>', methods=['DELETE'])
def del_event(id):
    supabase.table('events').delete().eq('id', id).execute()
    return jsonify({"message": "Event deleted."})


# ──────────────────────────────────────────────
# OPTIONAL CHOICE MANAGEMENT
# ──────────────────────────────────────────────
@admin_bp.route('/choice-admin', methods=['POST'])
def add_choice():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided."}), 400
    supabase.table('optional_choices').insert(data).execute()
    return jsonify({"message": "Optional choice added for players."})


# ──────────────────────────────────────────────
# ADMIN DASHBOARD DATA
# ──────────────────────────────────────────────
@admin_bp.route('/admin/players', methods=['GET'])
def admin_players():
    """Get all player states for admin overview."""
    players = get_all_players()
    game = get_game_state()
    return jsonify({"players": players, "game": game})
