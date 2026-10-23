-- Run in the SQL Editor of the Supabase project used by the backend.
-- Installs the initial-allocation RPC without resetting existing player data.
BEGIN;

CREATE TABLE IF NOT EXISTS public.player_month_actions (
    user_id     UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    month       INTEGER NOT NULL,
    action_key  TEXT NOT NULL,   -- e.g. 'choice:12' or 'relative:parent'
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    PRIMARY KEY (user_id, month, action_key)
);
ALTER TABLE public.player_month_actions ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.initialize_player(p_state JSONB)
RETURNS JSON AS $$
DECLARE g public.game_control%ROWTYPE; v public.player_state%ROWTYPE;
BEGIN
    SELECT * INTO g FROM public.game_control WHERE id = 1 FOR SHARE;
    IF g.game_status != 'active' OR g.current_month != 1 THEN RAISE EXCEPTION 'TURN_NOT_PLAYABLE'; END IF;
    INSERT INTO public.player_month_actions(user_id, month, action_key)
        VALUES ((p_state->>'user_id')::uuid, 1, 'alloc:1');
    INSERT INTO public.player_state
        (user_id, month, cash, stocks, gold, emergency_fund, investment_portfolio, lifestyle_type, bike_status,
         bike_lock_in_months, net_worth, risk_level, discipline_score, financial_health_score, status)
    VALUES ((p_state->>'user_id')::uuid, 1, (p_state->>'cash')::numeric,
        (p_state->>'stocks')::numeric, (p_state->>'gold')::numeric,
        (p_state->>'emergency_fund')::numeric, COALESCE(p_state->'investment_portfolio', '{}'::jsonb), p_state->>'lifestyle_type',
        (p_state->>'bike_status')::boolean, (p_state->>'bike_lock_in_months')::int,
        (p_state->>'net_worth')::numeric, (p_state->>'risk_level')::int, 100,
        (p_state->>'financial_health_score')::numeric, 'waiting') RETURNING * INTO v;
    INSERT INTO public.player_month_log(user_id, month, starting_cash, ending_cash, net_worth, summary)
        VALUES (v.user_id, 1, 100000, v.cash, v.net_worth, 'Initial allocation completed.');
    RETURN row_to_json(v);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;
REVOKE ALL ON FUNCTION public.initialize_player(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.initialize_player(JSONB) TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;

SELECT to_regprocedure('public.initialize_player(jsonb)') AS installed_function;
