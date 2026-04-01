-- ============================================================================
-- MIGRATION: Add trust_score and risk_level to player_state
-- Run this if you already have the old schema deployed.
-- ============================================================================

-- Add trust_score column (default 0, numeric for decimal precision)
ALTER TABLE public.player_state
  ADD COLUMN IF NOT EXISTS trust_score NUMERIC DEFAULT 0;

-- Add risk_level column (0–100 integer score)
ALTER TABLE public.player_state
  ADD COLUMN IF NOT EXISTS risk_level INTEGER DEFAULT 50;

-- ============================================================================
-- REPLACE THE ATOMIC RPC FUNCTION
-- Updated to handle trust_score and risk_level in player state updates.
-- Uses json_array_elements for reliable JSON parsing.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.process_month_atomically(
    p_updates_player_state JSON,
    p_updates_loans JSON,
    p_inserts_loans JSON,
    p_inserts_logs JSON,
    p_next_month INT
) RETURNS BOOLEAN AS $$
DECLARE
    current_m INT;
BEGIN
    -- Lock game control row
    SELECT current_month INTO current_m
    FROM public.game_control
    WHERE id = 1
    FOR UPDATE;

    -- Validate month transition
    IF p_next_month != current_m + 1 THEN
        RAISE EXCEPTION 'Invalid month transition: expected %, got %', current_m + 1, p_next_month;
    END IF;

    -- Idempotency check
    IF EXISTS (
        SELECT 1 FROM public.player_month_log
        WHERE month = p_next_month
    ) THEN
        RAISE EXCEPTION 'Month % already processed', p_next_month;
    END IF;

    -- Lock all player rows
    PERFORM 1 FROM public.player_state FOR UPDATE;

    -- ✅ UPDATE PLAYER STATE
    UPDATE public.player_state ps
    SET
        month                   = (data->>'month')::int,
        cash                    = (data->>'cash')::numeric,
        stocks                  = (data->>'stocks')::numeric,
        gold                    = (data->>'gold')::numeric,
        emergency_fund          = (data->>'emergency_fund')::numeric,
        lifestyle_type          = data->>'lifestyle_type',
        bike_status             = (data->>'bike_status')::boolean,
        loans                   = (data->>'loans')::numeric,
        pending_cash_next_month = (data->>'pending_cash_next_month')::numeric,
        bike_lock_in_months     = (data->>'bike_lock_in_months')::int,
        net_worth               = (data->>'net_worth')::numeric,
        trust_score             = COALESCE((data->>'trust_score')::numeric, ps.trust_score),
        risk_level              = COALESCE((data->>'risk_level')::int, ps.risk_level),
        status                  = data->>'status'
    FROM json_array_elements(p_updates_player_state) AS data
    WHERE ps.user_id = (data->>'user_id')::uuid;

    -- ✅ UPDATE LOANS
    UPDATE public.player_loans pl
    SET
        current_amount = (data->>'current_amount')::numeric,
        status         = data->>'status'
    FROM json_array_elements(p_updates_loans) AS data
    WHERE pl.id = (data->>'id')::int;

    -- ✅ INSERT NEW LOANS
    INSERT INTO public.player_loans (
        user_id, principal, current_amount, interest_rate, month_taken, status
    )
    SELECT
        (data->>'user_id')::uuid,
        (data->>'principal')::numeric,
        (data->>'current_amount')::numeric,
        (data->>'interest_rate')::numeric,
        (data->>'month_taken')::int,
        data->>'status'
    FROM json_array_elements(p_inserts_loans) AS data;

    -- ✅ INSERT LOGS
    INSERT INTO public.player_month_log (
        user_id, month, starting_cash, ending_cash, net_worth, summary
    )
    SELECT
        (data->>'user_id')::uuid,
        (data->>'month')::int,
        (data->>'starting_cash')::numeric,
        (data->>'ending_cash')::numeric,
        (data->>'net_worth')::numeric,
        data->>'summary'
    FROM json_array_elements(p_inserts_logs) AS data;

    -- ✅ ADVANCE GAME MONTH
    UPDATE public.game_control
    SET
        current_month = p_next_month,
        game_status   = 'active'
    WHERE id = 1;

    RETURN TRUE;

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- Leaderboard read policy (allow all players to read others' net worth)
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'player_state'
          AND policyname = 'Enable all for leaderboard read'
    ) THEN
        CREATE POLICY "Enable all for leaderboard read"
        ON public.player_state FOR SELECT USING (true);
    END IF;
END $$;
