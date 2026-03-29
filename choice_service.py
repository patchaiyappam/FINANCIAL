# =============================================================================
# CHOICE SERVICE — Handles player optional choice purchases
# Routes call this. No business logic lives in the route.
# =============================================================================

from supabase_client import supabase
from services.game_service import fair_roll, already_bought, mark_bought


def execute_choice(player: dict, choice_id: int) -> dict:
    """
    Execute an optional choice purchase for a player.

    This is the ONLY place that handles:
    - cash deduction
    - fair roll
    - reward distribution
    - error validation

    Returns: {success, message, error (if any)}
    """
    user_id = player['user_id']
    current_m = player['month']
    cash = float(player['cash'])

    # Idempotency guard
    if already_bought(user_id, current_m, choice_id):
        return {"error": "You already made this choice this month!"}

    # Fetch choice definition
    res = supabase.table('optional_choices').select('*').eq('id', choice_id).execute()
    if not res.data:
        return {"error": "Choice not found"}

    choice = res.data[0]
    cost = float(choice['cost'])

    if cash < cost:
        return {"error": f"Not enough cash! You need ₹{cost:,.0f} but have ₹{cash:,.0f}"}

    # Deduct cost
    cash -= cost

    # Probabilistic outcome — seeded per player+month+choice
    did_win = fair_roll(user_id, current_m, choice_id, choice['probability'])

    reward_updates = {'cash': cash}

    if did_win:
        reward_type = choice['reward_type']
        reward_val = float(choice['reward_value'])
        if reward_type == 'cash':
            cash += reward_val
            reward_updates['cash'] = cash
        elif reward_type in ['stocks', 'gold', 'emergency_fund']:
            current = float(player.get(reward_type, 0))
            reward_updates[reward_type] = current + reward_val
        message = f"SUCCESS! {choice['name']} paid off. Gained ₹{reward_val:,.0f} in {reward_type}."
    else:
        message = f"{choice['name']} didn't work out. Lost ₹{cost:,.0f}."

    # Single DB write with all changes
    supabase.table('player_state').update(reward_updates).eq('user_id', user_id).execute()
    mark_bought(user_id, current_m, choice_id)

    return {"success": did_win, "message": message}
