# =============================================================================
# ADMIN ROUTES — Game control, month processing, event/choice management
# Uses the modular engine for all game logic.
# =============================================================================

import re
from flask import Blueprint, request, jsonify
from supabase_client import supabase
from services.auth_service import admin_required
from services.game_service import (
    get_game_state, get_all_players, get_active_loans, get_player,
    get_admin_events_for_month, get_pending_sales, validate_rpc_payload,
    get_market_scenario_row
)
from engine.monthly_processor import process_month_for_player
from engine.market_engine import calculate_risk_score, resolve_market_scenario
from models.constants import MARKET_REGIMES
from models.news_library import list_events, get_event, events_by_category
from engine.scoring import calculate_financial_health_score
from engine.investment_engine import portfolio_value
from models.constants import TOTAL_MONTHS

admin_bp = Blueprint('admin', __name__)


# ──────────────────────────────────────────────
# START / RESTART GAME
# ──────────────────────────────────────────────
@admin_bp.route('/start-game', methods=['POST'])
@admin_required
def start_game():
    """Reset all game data and start fresh."""
    try:
        supabase.table('game_control').update({
            'current_month': 1,
            'game_status': 'active',
            'marriage_round_active': False
        }).eq('id', 1).execute()

        # Wipe all player data
        dummy = '00000000-0000-0000-0000-000000000000'
        supabase.table('player_state').delete().neq('user_id', dummy).execute()
        supabase.table('player_loans').delete().neq('user_id', dummy).execute()
        supabase.table('player_sales').delete().neq('user_id', dummy).execute()
        supabase.table('player_relative_score').delete().neq('user_id', dummy).execute()
        supabase.table('player_relative_actions').delete().neq('user_id', dummy).execute()
        supabase.table('player_month_log').delete().neq('user_id', dummy).execute()
        supabase.table('player_month_actions').delete().neq('user_id', dummy).execute()
        supabase.table('player_spouse_reveals').delete().neq('user_id', dummy).execute()
        # ADR-014: negotiations are PLAYER data and must not survive a restart,
        # or the engine reads last game's rounds as already-settled for month N.
        supabase.table('player_negotiations').delete().neq('user_id', dummy).execute()
        # B-01: monthly allocation records are per-game player data too — wipe them
        # so a new game's dashboard never shows a previous game's allocation.
        supabase.table('player_month_allocations').delete().neq('user_id', dummy).execute()

        # ────────────────────────────────────────────────────────────────
        # AUTHORED CONTENT IS **NOT** WIPED.
        #
        # This previously ran:
        #     DELETE FROM events; DELETE FROM optional_choices;
        # which destroyed the entire 12-month content pack every time an admin
        # pressed "Start Game" — including on event day, seconds before play,
        # leaving every student with salary-minus-expenses and no narrative.
        # Discovered during the 2026-07-24 pre-deploy audit after it silently
        # deleted a verified 11-event pack.
        #
        # Player data above = wiped. Authored content (events, optional_choices,
        # market_scenarios, spouse_proposals, spouse_dialogue) = preserved.
        # Use the admin Events tab to remove content deliberately.
        # ────────────────────────────────────────────────────────────────

        return jsonify({
            "message": "Game restarted. Player data wiped; authored content kept."
        })
    except Exception as e:
        return jsonify({"error": f"Failed to start game: {e}"}), 500


# ──────────────────────────────────────────────
# NEXT MONTH — Core monthly processing using engine
# ──────────────────────────────────────────────
@admin_bp.route('/next-month', methods=['POST'])
@admin_required
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
    auto_events = bool(game.get('auto_events', False))
    auto_market = bool(game.get('auto_market', False))

    # Race condition protection
    if exp_month is not None and int(exp_month) != curr_m:
        return jsonify({
            "error": f"Race condition blocked. System is on month {curr_m}."
        }), 409

    if game['game_status'] != 'active':
        return jsonify({"error": "Cannot advance — game is not active."}), 400

    next_m = curr_m + 1

    try:
        gate = supabase.rpc('begin_month_transition', {'p_expected_month': curr_m}).execute().data
    except Exception as e:
        return jsonify({'error': f'Cannot advance: {e}'}), 409
    if not gate.get('ready'):
        count = gate['unlocked_count']
        return jsonify({'error': f'Cannot advance: {count} player(s) have not completed and locked their turn.',
                        'unlocked_count': count,
                        'unallocated_count': gate.get('unallocated_count', 0)}), 409

    def _restore_active():
        supabase.table('game_control').update({'game_status': 'active'}).eq('id', 1).eq('current_month', curr_m).eq('game_status', 'processing').execute()

    try:
        # Fetch all data
        players = get_all_players()
        if not players:
            return jsonify({"error": "No players found to process."}), 400

        if curr_m == TOTAL_MONTHS:
            from engine.scoring import score_player_snapshot
            scores = [{'user_id': p['user_id'], **score_player_snapshot(p)} for p in players]
            supabase.rpc('finish_game_atomically', {'p_scores': scores}).execute()
            return jsonify({'message': f'Month {TOTAL_MONTHS} completed. Game officially ended!'})

        admin_events = get_admin_events_for_month(next_m)

        # ── Resolve the month's market scenario ONCE, for everyone ──
        # Admin-authored row wins; unauthored months fall back to the engine's
        # correlated auto regime (or a flat month when auto_market is off).
        scenario_row = get_market_scenario_row(next_m)
        market_scenario = resolve_market_scenario(next_m, scenario_row, auto_market)

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
                pending_sales=pending_sales,
                auto_events=auto_events,
                auto_market=auto_market,
                market_scenario=market_scenario
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
        except Exception as e:
            return jsonify({"error": f"Database processing failed: {e}"}), 500

        # The RPC has already advanced and reopened the game.
        return jsonify({
            "message": f"Success! Advanced to Month {next_m}.",
            "month": next_m,
            "market": market_scenario,
            "players_processed": len(players),
            "events_triggered": len(all_event_summaries),
            "event_details": all_event_summaries[:20]  # Limit for response size
        })
    except Exception as e:
        return jsonify({'error': f'Month processing failed: {e}'}), 500
    finally:
        _restore_active()



# ──────────────────────────────────────────────
# END GAME MANUALLY
# ──────────────────────────────────────────────
@admin_bp.route('/end-game', methods=['POST'])
@admin_required
def end_game():
    supabase.table('game_control').update({
        'game_status': 'ended'
    }).eq('id', 1).execute()
    return jsonify({"message": "Game has been ended manually."})


# ──────────────────────────────────────────────
# EVENT MANAGEMENT
# ──────────────────────────────────────────────
# QA-005: event_engine.apply_event_to_state only understands these
# type/target combinations — anything else silently no-ops (the engine
# just doesn't match a branch), so an admin typo previously vanished with
# no error. Validating here surfaces the mistake immediately instead.
_EVENT_TYPES = {'fixed', 'percentage'}
_EVENT_TARGETS = {'cash', 'stocks', 'gold', 'expense_increase'}
_PERCENTAGE_TARGETS = {'cash', 'stocks', 'gold'}  # expense_increase is fixed-only in the engine


@admin_bp.route('/event', methods=['POST'])
@admin_required
def add_event():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided."}), 400

    try:
        month = int(data.get('month'))
    except (TypeError, ValueError):
        return jsonify({"error": "month is required and must be an integer."}), 400

    event_type = data.get('event_type')
    if event_type not in _EVENT_TYPES:
        return jsonify({"error": f"event_type must be one of {sorted(_EVENT_TYPES)}."}), 400

    impact_target = data.get('impact_target')
    if impact_target not in _EVENT_TARGETS:
        return jsonify({"error": f"impact_target must be one of {sorted(_EVENT_TARGETS)}."}), 400
    if event_type == 'percentage' and impact_target not in _PERCENTAGE_TARGETS:
        return jsonify({"error": "expense_increase is only valid for event_type 'fixed'."}), 400

    try:
        value = float(data.get('value'))
    except (TypeError, ValueError):
        return jsonify({"error": "value is required and must be a number."}), 400

    record = {
        "month": month,
        "event_name": data.get('event_name', 'Admin Event'),
        "event_type": event_type,
        "category": data.get('category') or 'admin',
        "impact_target": impact_target,
        "value": value,
        "description": data.get('description', '')
    }
    supabase.table('events').insert(record).execute()
    return jsonify({"message": "Global event added successfully."})


@admin_bp.route('/event/<int:id>', methods=['DELETE'])
@admin_required
def del_event(id):
    supabase.table('events').delete().eq('id', id).execute()
    return jsonify({"message": "Event deleted."})


# ──────────────────────────────────────────────
# OPTIONAL CHOICE MANAGEMENT
# ──────────────────────────────────────────────
# QA-005: this is a financial mutation path — choice_service.execute_choice
# deducts `cost` and grants `reward_value` against these rows every time a
# player buys the choice. An unvalidated negative cost would pay players to
# "buy" it; an out-of-range probability would break fair_roll's semantics.
_REWARD_TYPES = {'cash', 'stocks', 'gold', 'emergency_fund'}


@admin_bp.route('/choice-admin', methods=['POST'])
@admin_required
def add_choice():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided."}), 400

    try:
        month = int(data.get('month'))
    except (TypeError, ValueError):
        return jsonify({"error": "month is required and must be an integer."}), 400

    try:
        cost = float(data.get('cost'))
    except (TypeError, ValueError):
        return jsonify({"error": "cost is required and must be a number."}), 400
    if cost < 0:
        return jsonify({"error": "cost cannot be negative."}), 400

    reward_type = data.get('reward_type')
    if reward_type not in _REWARD_TYPES:
        return jsonify({"error": f"reward_type must be one of {sorted(_REWARD_TYPES)}."}), 400

    try:
        reward_value = float(data.get('reward_value'))
    except (TypeError, ValueError):
        return jsonify({"error": "reward_value is required and must be a number."}), 400
    if reward_value < 0:
        return jsonify({"error": "reward_value cannot be negative."}), 400

    try:
        probability = int(data.get('probability'))
    except (TypeError, ValueError):
        return jsonify({"error": "probability is required and must be an integer 0-100."}), 400
    if not (0 <= probability <= 100):
        return jsonify({"error": "probability must be between 0 and 100."}), 400

    record = {
        "month": month,
        "name": data.get('name', 'Optional Choice'),
        "cost": cost,
        "risk_type": data.get('risk_type', ''),
        "reward_type": reward_type,
        "reward_value": reward_value,
        "probability": probability
    }
    supabase.table('optional_choices').insert(record).execute()
    return jsonify({"message": "Optional choice added for players."})


# ──────────────────────────────────────────────
# ADMIN DASHBOARD DATA
# ──────────────────────────────────────────────
@admin_bp.route('/admin/me', methods=['GET'])
@admin_required
def admin_me():
    """Lightweight check the admin login page uses to confirm admin rights."""
    return jsonify({"ok": True})


@admin_bp.route('/admin/players', methods=['GET'])
@admin_required
def admin_players():
    """All players with their name/email, ranked by Financial Health Score (ADR-008)."""
    res = supabase.table('player_state').select('*, users(name, email)').execute()
    from engine.scoring import score_player_snapshot
    players = res.data or []
    for player in players:
        player.update(score_player_snapshot(player))
    players.sort(key=lambda p: (float(p.get('financial_health_score') or 0),
                                float(p.get('net_worth') or 0)), reverse=True)
    game = get_game_state()
    return jsonify({"players": players, "game": game})


# ──────────────────────────────────────────────
# PLAYER DETAIL — manual edit (admin correction) + reset
# Every edit is written to player_month_log for audit.
# ──────────────────────────────────────────────
_EDITABLE = ['cash', 'stocks', 'gold', 'emergency_fund', 'loans', 'status', 'spouse_archetype']
_NUMERIC = ['cash', 'stocks', 'gold', 'emergency_fund', 'loans']


@admin_bp.route('/admin/update-player', methods=['POST'])
@admin_required
def update_player():
    data = request.json or {}
    uid = data.get('user_id')
    if not uid:
        return jsonify({"error": "user_id is required."}), 400

    current = get_player(uid)
    if not current:
        return jsonify({"error": "Player not found."}), 404

    fields = {}
    for k in _EDITABLE:
        if k in data and data[k] is not None and data[k] != '':
            fields[k] = data[k]
    try:
        for k in _NUMERIC:
            if k in fields:
                fields[k] = float(fields[k])
    except (ValueError, TypeError):
        return jsonify({"error": "Financial values must be numbers."}), 400

    if not fields:
        return jsonify({"error": "Nothing to update."}), 400

    # Net worth is always recomputed from components — never trust a typed value.
    merged = {**current, **fields}
    investment_assets = portfolio_value(merged.get('investment_portfolio') or {})
    net_worth = (float(merged['cash']) + float(merged['stocks']) + float(merged['gold'])
                 + float(merged['emergency_fund']) + investment_assets - float(merged['loans']))
    fields['net_worth'] = net_worth

    # QA-004 fix: net worth was already recomputed above, but the leaderboard
    # actually ranks by financial_health_score (ADR-008), and risk_level feeds
    # its risk_protection component. Both were previously left stale after a
    # correction, so a fixed data-entry mistake could still show a wrong rank
    # until the next month reprocessed it. Recompute both the same way
    # allocate_month1 does — discipline_score is left untouched (a correction
    # fixes financial figures, not the player's discipline history).
    risk_state = {
        "cash": float(merged['cash']), "stocks": float(merged['stocks']),
        "gold": float(merged['gold']), "emergency_fund": float(merged['emergency_fund']),
        "investment_portfolio": merged.get('investment_portfolio') or {},
        "loans": float(merged['loans'])
    }
    risk_level = calculate_risk_score(risk_state)
    month = int(merged.get('month', 1) or 1)
    from engine.monthly_processor import household_expenses
    monthly_expense = household_expenses(merged, month)['current']
    discipline_avg = float(merged.get('discipline_score', 100) or 100)
    total_assets = (risk_state['cash'] + risk_state['stocks']
                     + risk_state['gold'] + risk_state['emergency_fund'] + investment_assets)
    # D-09: same scorer contract as the engine — income + injected assets + wedding.
    from engine.scoring import spouse_score_inputs
    spouse_income, spouse_assets, wedding_cost = spouse_score_inputs(merged.get('spouse_archetype'))

    score_result = calculate_financial_health_score(
        net_worth=net_worth, month=month,
        emergency_fund=risk_state['emergency_fund'], monthly_expense=monthly_expense,
        loans=risk_state['loans'], total_assets=total_assets,
        risk_score=risk_level, discipline_avg=discipline_avg,
        spouse_income=spouse_income,
        spouse_assets=spouse_assets, wedding_cost=wedding_cost
    )
    fields['risk_level'] = risk_level
    fields['financial_health_score'] = score_result['score']

    try:
        supabase.table('player_state').update(fields).eq('user_id', uid).execute()
        # Audit trail — records the correction without touching prior month logs.
        supabase.table('player_month_log').insert({
            "user_id": uid,
            "month": int(merged.get('month', 1)),
            "starting_cash": float(current.get('cash', 0)),
            "ending_cash": float(merged['cash']),
            "net_worth": net_worth,
            "summary": "🛠️ Admin manual adjustment"
        }).execute()
    except Exception as e:
        return jsonify({"error": f"Update failed: {e}"}), 500

    return jsonify({
        "message": "Player updated.",
        "net_worth": net_worth,
        "risk_level": risk_level,
        "financial_health_score": score_result['score']
    })


# --------------------------------------------------
# GAME CONTROL SETTINGS - admin toggles the automatic layer.
# auto_events  = engine invents random emergencies/opportunities each month.
# auto_market  = stocks/gold move automatically each month.
# Both default OFF (manual control); admin flips them here. Emergency-fund
# interest and salary/expenses/loans are the fixed baseline, always on.
# --------------------------------------------------
@admin_bp.route('/admin/market', methods=['GET'])
@admin_required
def list_market_scenarios():
    """All authored scenarios + the preset regimes the admin can start from."""
    try:
        rows = supabase.table('market_scenarios').select('*').order('month').execute().data or []
    except Exception as e:
        return jsonify({"error": f"market_scenarios table missing? {e}"}), 500

    presets = [{
        "key": k,
        "name": v["name"],
        "reason": v["reason"],
        "stock_pct_range": v["stock"],
        "gold_pct_range": v["gold"],
        # Midpoint is what the admin gets if they click the preset.
        "stock_pct": round(sum(v["stock"]) / 2, 4),
        "gold_pct": round(sum(v["gold"]) / 2, 4)
    } for k, v in MARKET_REGIMES.items()]

    return jsonify({"scenarios": rows, "presets": presets})


@admin_bp.route('/admin/news', methods=['GET'])
@admin_required
def list_news():
    """
    The curated real-world news library, grouped by category, for the admin picker.
    Each entry carries the real headline, real date, the actual historical impact,
    and the lesson it teaches — so a round can be framed as a case study rather
    than as an arbitrary percentage.
    """
    return jsonify({
        "events": list_events(),
        "by_category": events_by_category()
    })


@admin_bp.route('/admin/news/apply', methods=['POST'])
@admin_required
def apply_news():
    """
    Apply a library news event to a month. This writes a normal market_scenarios
    row, so the engine path is identical whether the admin used the library, a
    preset, or hand-typed numbers — one code path, one source of truth.
    """
    d = request.json or {}
    key = d.get('key')
    try:
        month = int(d.get('month'))
    except (TypeError, ValueError):
        return jsonify({"error": "month is required."}), 400

    ev = get_event(key)
    if not ev:
        return jsonify({"error": f"Unknown news event '{key}'."}), 400
    if not (1 <= month <= TOTAL_MONTHS):
        return jsonify({"error": f"month must be 1-{TOTAL_MONTHS}."}), 400

    # The player-facing reason bundles the real context with the real historical
    # outcome, which is what makes this a case study instead of a random shock.
    reason = f"{ev['context']}\n\nWhat actually happened: {ev['real_note']}"

    row = {
        "month": month,
        "name": f"{ev['headline']} ({ev['date']})",
        "reason": reason,
        "stock_pct": ev['stock_pct'],
        "gold_pct": ev['gold_pct'],
        "regime": f"news:{key}"
    }
    try:
        supabase.table('market_scenarios').upsert(row, on_conflict='month').execute()
    except Exception as e:
        return jsonify({"error": f"Save failed: {e}"}), 500

    return jsonify({
        "message": f"Month {month}: {ev['headline']}",
        "scenario": row,
        "lesson": ev['lesson']
    })


@admin_bp.route('/admin/market', methods=['POST'])
@admin_required
def set_market_scenario():
    """
    Author (or overwrite) the market scenario for a month. One scenario drives BOTH
    stocks and gold plus the reason shown to players, so 'war broke out, gold up,
    stocks down' is a single authored row rather than two unrelated numbers.
    """
    d = request.json or {}
    try:
        month = int(d.get('month'))
        stock_pct = float(d.get('stock_pct'))
        gold_pct = float(d.get('gold_pct'))
    except (TypeError, ValueError):
        return jsonify({"error": "month, stock_pct and gold_pct are required numbers."}), 400

    if not (1 <= month <= TOTAL_MONTHS):
        return jsonify({"error": f"month must be 1-{TOTAL_MONTHS}."}), 400

    name = (d.get('name') or '').strip()
    if not name:
        return jsonify({"error": "Scenario name is required."}), 400
    reason = (d.get('reason') or '').strip()
    if not reason:
        return jsonify({"error": "A reason is required — players must be told WHY the market moved."}), 400

    # Sanity bound. A -95% month is almost always a misplaced decimal, and it would
    # make the round unrecoverable for every player at once.
    for label, v in (("stock_pct", stock_pct), ("gold_pct", gold_pct)):
        if not (-0.60 <= v <= 0.60):
            return jsonify({"error": f"{label} must be between -0.60 and 0.60 (i.e. -60% to +60%)."}), 400

    row = {
        "month": month, "name": name, "reason": reason,
        "stock_pct": stock_pct, "gold_pct": gold_pct,
        "regime": d.get('regime') or 'authored'
    }
    try:
        supabase.table('market_scenarios').upsert(row, on_conflict='month').execute()
    except Exception as e:
        return jsonify({"error": f"Save failed: {e}"}), 500

    return jsonify({"message": f"Month {month} market scenario saved.", "scenario": row})


@admin_bp.route('/admin/market/<int:month>', methods=['DELETE'])
@admin_required
def del_market_scenario(month):
    """Remove an authored scenario; the month reverts to the auto regime."""
    try:
        supabase.table('market_scenarios').delete().eq('month', month).execute()
    except Exception as e:
        return jsonify({"error": f"Delete failed: {e}"}), 500
    return jsonify({"message": f"Month {month} scenario removed — falls back to auto."})


@admin_bp.route('/admin/market/preview', methods=['GET'])
@admin_required
def preview_market():
    """
    Show the resolved 12-month market path exactly as the engine will run it,
    so the admin can see the arc before the event instead of discovering it live.
    """
    game = get_game_state() or {}
    auto_market = bool(game.get('auto_market', False))
    out = []
    for m in range(1, TOTAL_MONTHS + 1):
        row = get_market_scenario_row(m)
        out.append({"month": m, **resolve_market_scenario(m, row, auto_market)})
    return jsonify({"auto_market": auto_market, "path": out})


@admin_bp.route('/admin/proposals', methods=['GET'])
@admin_required
def list_proposals():
    """Authored spouse proposals + the built-in defaults they override."""
    try:
        rows = supabase.table('spouse_proposals').select('*').order('id').execute().data or []
    except Exception as e:
        return jsonify({"error": f"spouse_proposals table missing? {e}"}), 500
    from services.negotiation_service import DEFAULT_PROPOSALS
    return jsonify({"proposals": rows,
                    "defaults": [{"archetype_id": k, **v} for k, v in DEFAULT_PROPOSALS.items()]})


@admin_bp.route('/admin/proposals', methods=['POST'])
@admin_required
def add_proposal():
    d = request.json or {}
    required = ("archetype_id", "kind", "title", "description", "amount_min", "amount_max")
    missing = [f for f in required if not d.get(f)]
    if missing:
        return jsonify({"error": f"Missing: {missing}"}), 400
    if d['kind'] not in ("lifestyle", "investment", "saving", "protection"):
        return jsonify({"error": "kind must be lifestyle, investment, saving or protection."}), 400
    try:
        lo, hi = float(d['amount_min']), float(d['amount_max'])
    except (TypeError, ValueError):
        return jsonify({"error": "amount_min/amount_max must be numbers."}), 400
    if lo > hi:
        return jsonify({"error": "amount_min cannot exceed amount_max."}), 400

    row = {"archetype_id": d['archetype_id'], "month": d.get('month') or None,
           "kind": d['kind'], "title": d['title'], "description": d['description'],
           "amount_min": lo, "amount_max": hi,
           "floor_ratio": float(d.get('floor_ratio') or 0.6),
           "ev_note": d.get('ev_note', '')}
    try:
        supabase.table('spouse_proposals').insert(row).execute()
    except Exception as e:
        return jsonify({"error": f"Save failed: {e}"}), 500
    return jsonify({"message": "Proposal added.", "proposal": row})


@admin_bp.route('/admin/proposals/<int:pid>', methods=['DELETE'])
@admin_required
def del_proposal(pid):
    try:
        supabase.table('spouse_proposals').delete().eq('id', pid).execute()
    except Exception as e:
        return jsonify({"error": f"Delete failed: {e}"}), 500
    return jsonify({"message": f"Proposal {pid} removed."})


@admin_bp.route('/admin/settings', methods=['POST'])
@admin_required
def update_settings():
    data = request.json or {}
    fields = {}
    if 'auto_events' in data:
        fields['auto_events'] = bool(data['auto_events'])
    if 'auto_market' in data:
        fields['auto_market'] = bool(data['auto_market'])
    if 'marriage_round_active' in data:
        fields['marriage_round_active'] = bool(data['marriage_round_active'])
    if 'negotiation_enabled' in data:
        # ADR-014 kill switch. Off = the marriage system behaves exactly as it
        # did before negotiation existed. Flipping this off mid-event is the
        # documented rollback path.
        fields['negotiation_enabled'] = bool(data['negotiation_enabled'])
    if not fields:
        return jsonify({"error": "Nothing to update."}), 400
    supabase.table('game_control').update(fields).eq('id', 1).execute()
    return jsonify({"message": "Settings updated.", **fields})


# --------------------------------------------------
# PLAYER ROSTER - every provisioned login, and whether they have started.
# public.users has a row per created account (via the signup trigger). A
# player only gets a player_state row once they do their month-1 allocation,
# so "played" distinguishes started vs. waiting. Admins (public.admins) excluded.
# --------------------------------------------------
@admin_bp.route('/admin/roster', methods=['GET'])
@admin_required
def admin_roster():
    users = supabase.table('users').select('id, name, email').execute().data or []
    admin_rows = supabase.table('admins').select('user_id').execute().data or []
    played_rows = supabase.table('player_state').select('user_id').execute().data or []
    admin_ids = {r['user_id'] for r in admin_rows}
    played_ids = {r['user_id'] for r in played_rows}
    absent_rows = supabase.table('player_month_actions').select('user_id').eq('month', 0).eq('action_key', 'absent').execute().data or []
    absent_ids = {r['user_id'] for r in absent_rows}
    roster = []
    for u in users:
        if u['id'] in admin_ids:
            continue
        email = u.get('email') or ''
        username = email.split('@')[0] if '@' in email else email
        roster.append({
            'user_id': u['id'],
            'username': username,
            'name': u.get('name') or username,
            'played': u['id'] in played_ids,
            'absent': u['id'] in absent_ids and u['id'] not in played_ids,
        })
    roster.sort(key=lambda r: r['username'])
    return jsonify({'roster': roster})


# --------------------------------------------------
# CREATE PLAYER - admin provisions a login (username + password).
# Uses the service_role admin API to create the auth user; the
# on_auth_user_created trigger then creates the public.users profile row.
# Players log in with just a username; the real email is username@event.local.
# --------------------------------------------------
PLAYER_EMAIL_DOMAIN = 'event.local'
_USERNAME_RE = re.compile(r'^[a-z0-9_.-]{3,32}$')


@admin_bp.route('/admin/create-player', methods=['POST'])
@admin_required
def create_player():
    data = request.json or {}
    username = str(data.get('username', '')).strip().lower()
    password = str(data.get('password', ''))
    name = str(data.get('name', '')).strip() or username

    if not _USERNAME_RE.match(username):
        return jsonify({"error": "Username must be 3-32 chars: letters, numbers, . _ - only."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    email = f"{username}@{PLAYER_EMAIL_DOMAIN}"
    try:
        supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"name": name},
        })
    except Exception as e:
        msg = str(e)
        if 'already' in msg.lower() or 'registered' in msg.lower() or 'exists' in msg.lower():
            return jsonify({"error": f"Username '{username}' already exists."}), 409
        return jsonify({"error": f"Could not create player: {msg}"}), 500

    return jsonify({"message": f"Player '{username}' created. They can log in now.", "username": username})


@admin_bp.route('/admin/reset-player', methods=['POST'])
@admin_required
def reset_player():
    data = request.json or {}
    uid = data.get('user_id')
    if not uid:
        return jsonify({"error": "user_id is required."}), 400
    try:
        # B-01: complete reset contract — every per-game, player-scoped table.
        # Previously player_negotiations and player_month_allocations were omitted,
        # so a reset player could not negotiate (old rounds read as 'already
        # settled') and saw stale allocation records on the dashboard.
        for table in ['player_state', 'player_loans', 'player_sales',
                      'player_relative_score', 'player_relative_actions',
                      'player_month_log', 'player_month_actions', 'player_spouse_reveals',
                      'player_negotiations', 'player_month_allocations']:
            supabase.table(table).delete().eq('user_id', uid).execute()
    except Exception as e:
        return jsonify({"error": f"Reset failed: {e}"}), 500
    return jsonify({"message": "Player reset — they can allocate again."})
