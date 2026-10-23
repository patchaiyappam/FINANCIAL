-- Repair backend RPCs on an existing Money Master database.
-- Run the entire file in the same Supabase project used by the backend.
-- This replaces function definitions only: no game reset or player deletion.
BEGIN;

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

CREATE OR REPLACE FUNCTION public.begin_month_transition(p_expected_month INT)
RETURNS JSON AS $$
DECLARE g public.game_control%ROWTYPE; unlocked INT; missing INT;
BEGIN
    SELECT * INTO g FROM public.game_control WHERE id = 1 FOR UPDATE;
    IF g.current_month != p_expected_month OR g.game_status != 'active' THEN
        RAISE EXCEPTION 'INVALID_TRANSITION';
    END IF;
    PERFORM 1 FROM public.player_state ORDER BY user_id FOR UPDATE;
    SELECT count(*) INTO missing FROM public.users u
        WHERE NOT EXISTS (SELECT 1 FROM public.admins a WHERE a.user_id = u.id)
          AND NOT EXISTS (SELECT 1 FROM public.player_month_actions a
              WHERE a.user_id = u.id AND a.month = 0 AND a.action_key = 'absent')
          AND NOT EXISTS (SELECT 1 FROM public.player_state p WHERE p.user_id = u.id);
    SELECT count(*) INTO unlocked FROM public.player_state
        WHERE status != 'waiting' OR month != g.current_month
          OR (month >= 2 AND cash > 0.5 AND NOT EXISTS (
              SELECT 1 FROM public.player_month_actions a WHERE a.user_id = player_state.user_id
              AND a.month = player_state.month AND a.action_key = 'alloc:' || player_state.month))
          OR (month = 4 AND g.marriage_round_active AND spouse_archetype IS NULL);
    IF unlocked + missing > 0 THEN
        RETURN json_build_object('ready', false, 'unlocked_count', unlocked + missing,
                                  'unallocated_count', missing);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.player_state) THEN RAISE EXCEPTION 'NO_PLAYERS'; END IF;
    UPDATE public.game_control SET game_status = 'processing' WHERE id = 1;
    RETURN json_build_object('ready', true, 'month', g.current_month);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;
REVOKE ALL ON FUNCTION public.begin_month_transition(INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.begin_month_transition(INT) TO service_role;

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

    IF (SELECT game_status FROM public.game_control WHERE id = 1) != 'processing'
       OR p_next_month > 12 THEN RAISE EXCEPTION 'INVALID_TRANSITION'; END IF;
    IF EXISTS (SELECT 1 FROM public.player_state WHERE status != 'waiting' OR month != current_m)
       THEN RAISE EXCEPTION 'UNLOCKED_PLAYERS'; END IF;
    IF json_array_length(p_updates_player_state) != (SELECT count(*) FROM public.player_state)
       OR (SELECT count(DISTINCT x->>'user_id') FROM json_array_elements(p_updates_player_state) x)
          != (SELECT count(*) FROM public.player_state)
       OR EXISTS (SELECT 1 FROM json_array_elements(p_updates_player_state) x
                  WHERE (x->>'month')::int != p_next_month
                     OR NOT EXISTS (SELECT 1 FROM public.player_state WHERE user_id = (x->>'user_id')::uuid))
       THEN RAISE EXCEPTION 'INCOMPLETE_PLAYER_BATCH'; END IF;

    -- Update all current engine state fields.
    UPDATE public.player_state ps
    SET
        month = (data->>'month')::int,
        cash = (data->>'cash')::numeric,
        stocks = (data->>'stocks')::numeric,
        gold = (data->>'gold')::numeric,
        emergency_fund = (data->>'emergency_fund')::numeric,
        investment_portfolio = COALESCE((data->'investment_portfolio')::jsonb, ps.investment_portfolio),
        lifestyle_type = data->>'lifestyle_type',
        bike_status = (data->>'bike_status')::boolean,
        loans = (data->>'loans')::numeric,
        pending_cash_next_month = (data->>'pending_cash_next_month')::numeric,
        bike_lock_in_months = (data->>'bike_lock_in_months')::int,
        net_worth = (data->>'net_worth')::numeric,
        trust_score = COALESCE((data->>'trust_score')::numeric, ps.trust_score),
        risk_level = COALESCE((data->>'risk_level')::int, ps.risk_level),
        discipline_score = COALESCE((data->>'discipline_score')::numeric, ps.discipline_score),
        financial_health_score = COALESCE((data->>'financial_health_score')::numeric, ps.financial_health_score),
        spouse_archetype = data->>'spouse_archetype',
        spouse_satisfaction = (data->>'spouse_satisfaction')::numeric,
        household_expense_modifier = (data->>'household_expense_modifier')::numeric,
        insurance_plan = data->>'insurance_plan',
        status = data->>'status'
    FROM json_array_elements(p_updates_player_state) AS data
    WHERE ps.user_id = (data->>'user_id')::uuid;

    -- ✅ UPDATE LOANS
    UPDATE public.player_loans pl
    SET
        current_amount = (data->>'current_amount')::numeric,
        status = data->>'status'
    FROM json_array_elements(p_updates_loans) AS data
    WHERE pl.id = (data->>'id')::int AND pl.user_id = (data->>'user_id')::uuid;

    -- ✅ INSERT NEW LOANS
    INSERT INTO public.player_loans (
        user_id, principal, current_amount, interest_rate, month_taken, status, term_months, loan_type, emi
    )
    SELECT
        (data->>'user_id')::uuid,
        (data->>'principal')::numeric,
        (data->>'current_amount')::numeric,
        (data->>'interest_rate')::numeric,
        (data->>'month_taken')::int,
        data->>'status',
        COALESCE((data->>'term_months')::int, 6),
        COALESCE(data->>'loan_type', 'auto'),
        COALESCE((data->>'emi')::numeric, 0)
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
        game_status = 'active'
    WHERE id = 1;

    RETURN TRUE;

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;
REVOKE EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) FROM anon;
REVOKE EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) TO service_role;

CREATE OR REPLACE FUNCTION public.finish_game_atomically(p_scores JSONB)
RETURNS BOOLEAN AS $$
DECLARE g public.game_control%ROWTYPE;
BEGIN
    SELECT * INTO g FROM public.game_control WHERE id = 1 FOR UPDATE;
    IF g.current_month != 12 OR g.game_status != 'processing' THEN
        RAISE EXCEPTION 'INVALID_TRANSITION'; END IF;
    PERFORM 1 FROM public.player_state FOR UPDATE;
    IF EXISTS (SELECT 1 FROM public.player_state WHERE month != 12 OR status != 'waiting')
        THEN RAISE EXCEPTION 'UNLOCKED_PLAYERS'; END IF;
    IF jsonb_array_length(p_scores) != (SELECT count(*) FROM public.player_state)
       OR (SELECT count(DISTINCT x->>'user_id') FROM jsonb_array_elements(p_scores) x)
          != (SELECT count(*) FROM public.player_state)
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_scores) x WHERE NOT EXISTS
           (SELECT 1 FROM public.player_state WHERE user_id = (x->>'user_id')::uuid))
       THEN RAISE EXCEPTION 'INCOMPLETE_PLAYER_BATCH'; END IF;
    UPDATE public.player_state p SET net_worth = (x->>'net_worth')::numeric,
        risk_level = (x->>'risk_level')::int,
        financial_health_score = (x->>'financial_health_score')::numeric
        FROM jsonb_array_elements(p_scores) x WHERE p.user_id = (x->>'user_id')::uuid;
    UPDATE public.game_control SET game_status = 'ended' WHERE id = 1;
    RETURN true;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;
REVOKE ALL ON FUNCTION public.finish_game_atomically(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finish_game_atomically(JSONB) TO service_role;

CREATE OR REPLACE FUNCTION public.player_apply_atomic(
    p_user_id             UUID,
    p_month               INT,
    p_action_key          TEXT,     -- NULL => no idempotency claim
    p_require_cash        NUMERIC,  -- NULL => no floor; else require cash >= this BEFORE deltas
    p_deltas              JSONB,    -- additive to numeric columns
    p_sets                JSONB,    -- absolute overrides (whitelisted columns only)
    p_clamp_satisfaction  BOOLEAN,
    p_recompute_networth  BOOLEAN,
    p_loan_inserts        JSONB,    -- array of loan rows to INSERT
    p_loan_updates        JSONB     -- array of {id, current_amount, status} to UPDATE
) RETURNS JSON AS $$
DECLARE
    v            public.player_state%ROWTYPE;
    d            JSONB := COALESCE(p_deltas, '{}'::jsonb);
    s            JSONB := COALESCE(p_sets,   '{}'::jsonb);
    v_cash       NUMERIC;
    v_stocks     NUMERIC;
    v_gold       NUMERIC;
    v_ef         NUMERIC;
    v_loans      NUMERIC;
    v_trust      NUMERIC;
    v_sat        NUMERIC;
    v_hmod       NUMERIC;
    v_nw         NUMERIC;
    li           JSONB;
    lu           JSONB;
    reveal_cost NUMERIC := 0;
    n JSONB := s->'negotiation';
    g public.game_control%ROWTYPE;
BEGIN
    -- Same lock order as the month transition: game first, then player.
    SELECT * INTO g FROM public.game_control WHERE id = 1 FOR SHARE;
    IF g.game_status != 'active' OR g.current_month != p_month THEN
        RAISE EXCEPTION 'TURN_NOT_PLAYABLE';
    END IF;
    SELECT * INTO v FROM public.player_state WHERE user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'PLAYER_NOT_FOUND'; END IF;
    IF v.month != p_month OR v.status != 'active' THEN RAISE EXCEPTION 'TURN_NOT_PLAYABLE'; END IF;
    IF s ? 'spouse_archetype' OR s ? 'reveal' THEN
        IF NOT g.marriage_round_active OR p_month != 4 OR v.spouse_archetype IS NOT NULL THEN
            RAISE EXCEPTION 'MARRIAGE_NOT_AVAILABLE';
        END IF;
    END IF;
    IF s ? 'status' AND s->>'status' = 'waiting' THEN
        IF p_month >= 2 AND v.cash > 0.5 AND NOT EXISTS (
            SELECT 1 FROM public.player_month_actions WHERE user_id = p_user_id
              AND month = p_month AND action_key = 'alloc:' || p_month)
            THEN RAISE EXCEPTION 'ALLOCATION_REQUIRED'; END IF;
        IF p_month = 4 AND g.marriage_round_active AND v.spouse_archetype IS NULL
            THEN RAISE EXCEPTION 'MARRIAGE_DECISION_REQUIRED'; END IF;
    END IF;
    IF s ? 'reveal' THEN
        IF EXISTS (SELECT 1 FROM public.player_spouse_reveals
            WHERE user_id = p_user_id AND archetype_id = s->'reveal'->>'archetype_id'
            AND trait_key = s->'reveal'->>'trait_key') THEN
            RETURN row_to_json(v)::jsonb || jsonb_build_object('reveal_cost', 0);
        END IF;
        IF (SELECT count(*) FROM public.player_spouse_reveals WHERE user_id = p_user_id) >= 3
            THEN reveal_cost := 5000; END IF;
        IF v.cash < reveal_cost THEN RAISE EXCEPTION 'INSUFFICIENT_CASH'; END IF;
        d := d || jsonb_build_object('cash', -reveal_cost);
        INSERT INTO public.player_spouse_reveals(user_id, archetype_id, trait_key)
            VALUES(p_user_id, s->'reveal'->>'archetype_id', s->'reveal'->>'trait_key');
    END IF;
    IF n IS NOT NULL THEN
        IF NOT g.negotiation_enabled OR v.spouse_archetype IS NULL OR v.spouse_archetype = 'single'
            THEN RAISE EXCEPTION 'NEGOTIATION_NOT_AVAILABLE'; END IF;
        IF EXISTS (SELECT 1 FROM public.player_negotiations WHERE user_id = p_user_id
            AND month = p_month AND confirmed AND outcome IN
            ('accepted_full', 'accepted_counter', 'refused', 'delayed', 'auto_resolved'))
            THEN RAISE EXCEPTION 'DUPLICATE_ACTION'; END IF;
        PERFORM 1 FROM public.player_negotiations
            WHERE id = (n->>'id')::bigint AND user_id = p_user_id AND month = p_month
            AND round = (n->>'round')::int AND intent = n->>'intent'
            AND params = n->'params' AND NOT confirmed AND outcome = 'pending' FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'PENDING_NEGOTIATION_REQUIRED'; END IF;
        IF (n->>'round')::int != 1 + (SELECT count(*) FROM public.player_negotiations
            WHERE user_id = p_user_id AND month = p_month AND confirmed)
            THEN RAISE EXCEPTION 'DUPLICATE_ACTION'; END IF;
    END IF;
    -- 1. Idempotency claim, atomic with the mutation below. A concurrent SAME-action
    --    call blocks on the PK until this txn commits, then gets a unique_violation.
    IF p_action_key IS NOT NULL THEN
        BEGIN
            INSERT INTO public.player_month_actions (user_id, month, action_key)
            VALUES (p_user_id, p_month, p_action_key);
        EXCEPTION WHEN unique_violation THEN
            RAISE EXCEPTION 'DUPLICATE_ACTION';
        END;
    END IF;

    -- 2. Lock this player's row. A concurrent DIFFERENT action blocks here until we
    --    commit, so both compose on the authoritative balance instead of racing.
    SELECT * INTO v FROM public.player_state WHERE user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'PLAYER_NOT_FOUND';
    END IF;

    -- 3. Affordability guard, re-checked under the lock against authoritative cash.
    IF p_require_cash IS NOT NULL AND v.cash < p_require_cash THEN
        RAISE EXCEPTION 'INSUFFICIENT_CASH';
    END IF;

    -- 4. Apply ADDITIVE deltas (missing keys => 0 => no change).
    v_cash   := v.cash                                  + COALESCE((d->>'cash')::numeric, 0);
    v_stocks := v.stocks                                + COALESCE((d->>'stocks')::numeric, 0);
    v_gold   := v.gold                                  + COALESCE((d->>'gold')::numeric, 0);
    v_ef     := v.emergency_fund                        + COALESCE((d->>'emergency_fund')::numeric, 0);
    v_loans  := v.loans                                 + COALESCE((d->>'loans')::numeric, 0);
    v_trust  := COALESCE(v.trust_score, 0)              + COALESCE((d->>'trust_score')::numeric, 0);
    v_sat    := COALESCE(v.spouse_satisfaction, 60)     + COALESCE((d->>'spouse_satisfaction')::numeric, 0);
    v_hmod   := COALESCE(v.household_expense_modifier,0)+ COALESCE((d->>'household_expense_modifier')::numeric, 0);

    -- Floors: assets and trust cannot go negative; satisfaction clamps 0..100.
    -- Cash: only sub-Rs2 rounding noise is snapped to 0 (this reproduces the
    -- max(0, available - invested) tolerance allocate_month used for float/display
    -- rounding). Larger negatives are PRESERVED so behaviour that intentionally
    -- allows negative cash (e.g. wedding + a negative month-6 spouse flow, which
    -- the safety net covers next month) is unchanged. p_require_cash still guards
    -- every genuine spend, so cash never drops materially below zero here.
    IF v_cash < 0 AND v_cash >= -2 THEN v_cash := 0; END IF;
    IF v_stocks < 0 THEN v_stocks := 0; END IF;
    IF v_gold   < 0 THEN v_gold   := 0; END IF;
    IF v_ef     < 0 THEN v_ef     := 0; END IF;
    IF v_loans  < 0 THEN v_loans  := 0; END IF;
    IF v_trust  < 0 THEN v_trust  := 0; END IF;
    IF p_clamp_satisfaction THEN
        v_sat := GREATEST(0, LEAST(100, v_sat));
    END IF;

    IF p_recompute_networth THEN
        v_nw := v_cash + v_stocks + v_gold + v_ef - v_loans;
    ELSE
        v_nw := v.net_worth;   -- preserve existing behaviour (these routes never set it)
    END IF;

    -- 5. Persist balances.
    UPDATE public.player_state SET
        cash                       = v_cash,
        stocks                     = v_stocks,
        gold                       = v_gold,
        emergency_fund             = v_ef,
        loans                      = v_loans,
        trust_score                = v_trust,
        spouse_satisfaction        = v_sat,
        household_expense_modifier = v_hmod,
        net_worth                  = v_nw
    WHERE user_id = p_user_id;

    -- 6. Absolute sets — only these columns may be set this way.
    IF s ? 'spouse_archetype' THEN
        UPDATE public.player_state SET spouse_archetype = (s->>'spouse_archetype') WHERE user_id = p_user_id;
    END IF;
    IF s ? 'insurance_plan' THEN
        UPDATE public.player_state SET insurance_plan = (s->>'insurance_plan') WHERE user_id = p_user_id;
    END IF;
    IF s ? 'risk_level' THEN
        UPDATE public.player_state SET risk_level = (s->>'risk_level')::int WHERE user_id = p_user_id;
    END IF;
    IF s ? 'financial_health_score' THEN
        UPDATE public.player_state SET financial_health_score = (s->>'financial_health_score')::numeric WHERE user_id = p_user_id;
    END IF;
    IF s ? 'status' THEN
        UPDATE public.player_state SET status = (s->>'status') WHERE user_id = p_user_id;
    END IF;

    -- 7. Loan inserts (e.g. a new voluntary loan, or a spouse's brought loan).
    IF p_loan_inserts IS NOT NULL THEN
        FOR li IN SELECT * FROM jsonb_array_elements(p_loan_inserts) LOOP
            INSERT INTO public.player_loans
                (user_id, principal, current_amount, interest_rate, month_taken, term_months, loan_type, emi, status)
            VALUES (
                p_user_id,
                (li->>'principal')::numeric,
                (li->>'current_amount')::numeric,
                (li->>'interest_rate')::numeric,
                (li->>'month_taken')::int,
                COALESCE((li->>'term_months')::int, 6),       -- NULL-safe: missing => NULL
                COALESCE(li->>'loan_type', 'player'),
                COALESCE((li->>'emi')::numeric, 0),            -- NULL-safe
                COALESCE(li->>'status', 'active')
            );
        END LOOP;
    END IF;

    -- 8. Loan updates (e.g. allocate-month prepayment applied oldest-first in Python).
    IF p_loan_updates IS NOT NULL THEN
        FOR lu IN SELECT * FROM jsonb_array_elements(p_loan_updates) LOOP
            UPDATE public.player_loans
               SET current_amount = (lu->>'current_amount')::numeric,
                   status         = COALESCE(lu->>'status', 'active')
             WHERE id = (lu->>'id')::int AND user_id = p_user_id;
        END LOOP;
    END IF;

    IF n IS NOT NULL THEN
        UPDATE public.player_negotiations SET confirmed = true,
            outcome = n->>'outcome', rule_input = n->'rule_input',
            rule_output = n->'rule_output', ai_source = 'rules'
        WHERE id = (n->>'id')::bigint;
    END IF;
    -- 9. Return the fresh authoritative row.
    SELECT * INTO v FROM public.player_state WHERE user_id = p_user_id;
    RETURN row_to_json(v)::jsonb || jsonb_build_object('reveal_cost', reveal_cost);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;
REVOKE EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB) FROM anon;
REVOKE EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB) TO service_role;

CREATE OR REPLACE FUNCTION public.sell_asset_atomic(
    p_user_id UUID,
    p_asset_type TEXT,
    p_amount NUMERIC,
    p_month INT,
    p_penalty_rate NUMERIC
) RETURNS JSON AS $$
DECLARE
    v_current NUMERIC;
    v_new_val NUMERIC;
    v_penalty NUMERIC;
    v_receive NUMERIC;
    g public.game_control%ROWTYPE;
    v public.player_state%ROWTYPE;
BEGIN
    SELECT * INTO g FROM public.game_control WHERE id = 1 FOR SHARE;
    IF g.game_status != 'active' OR g.current_month != p_month THEN
        RAISE EXCEPTION 'TURN_NOT_PLAYABLE';
    END IF;
    SELECT * INTO v FROM public.player_state WHERE user_id = p_user_id FOR UPDATE;
    IF NOT FOUND OR v.status != 'active' OR v.month != p_month THEN
        RAISE EXCEPTION 'TURN_NOT_PLAYABLE';
    END IF;
    IF p_asset_type NOT IN ('stocks', 'gold', 'emergency_fund') THEN
        RAISE EXCEPTION 'Invalid asset type: %', p_asset_type;
    END IF;
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be positive';
    END IF;

    PERFORM 1 FROM public.player_state WHERE user_id = p_user_id FOR UPDATE;

    EXECUTE format('SELECT %I FROM public.player_state WHERE user_id = $1', p_asset_type)
        INTO v_current USING p_user_id;

    IF v_current IS NULL THEN
        RAISE EXCEPTION 'Player not found';
    END IF;

    IF v_current < p_amount THEN
        RAISE EXCEPTION 'Insufficient % balance', p_asset_type;
    END IF;

    v_new_val := v_current - p_amount;
    v_penalty := p_amount * p_penalty_rate;
    v_receive := p_amount - v_penalty;

    EXECUTE format('UPDATE public.player_state SET %I = $1 WHERE user_id = $2', p_asset_type)
        USING v_new_val, p_user_id;

    INSERT INTO public.player_sales (
        user_id, asset_type, amount_sold, penalty, cash_to_receive, month_sold_in, month_to_credit
    ) VALUES (
        p_user_id, p_asset_type, p_amount, v_penalty, v_receive, p_month, p_month + 1
    );

    RETURN json_build_object(
        'new_balance', v_new_val,
        'penalty', v_penalty,
        'cash_to_receive', v_receive
    );
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;
REVOKE EXECUTE ON FUNCTION public.sell_asset_atomic(UUID, TEXT, NUMERIC, INT, NUMERIC) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.sell_asset_atomic(UUID, TEXT, NUMERIC, INT, NUMERIC) FROM anon;
REVOKE EXECUTE ON FUNCTION public.sell_asset_atomic(UUID, TEXT, NUMERIC, INT, NUMERIC) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.sell_asset_atomic(UUID, TEXT, NUMERIC, INT, NUMERIC) TO service_role;

NOTIFY pgrst, 'reload schema';
COMMIT;

SELECT p.proname AS installed_function
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND p.proname IN (
    'initialize_player', 'begin_month_transition', 'process_month_atomically', 'finish_game_atomically', 'player_apply_atomic', 'sell_asset_atomic'
)
ORDER BY p.proname;
