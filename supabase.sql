-- ============================================================================
-- Supabase Schema for Money Master — Financial Simulation Game
-- ============================================================================

BEGIN;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ──── Users ────
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT,
    email TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- ──── Case Study (Scenario Setup) ────
CREATE TABLE IF NOT EXISTS public.case_study (
    id SERIAL PRIMARY KEY,
    title TEXT,
    description TEXT,
    rent NUMERIC,
    food NUMERIC,
    transport NUMERIC,
    family NUMERIC
);

INSERT INTO public.case_study (title, description, rent, food, transport, family)
SELECT 'The First Job', 'Manage ₹1,00,000 monthly income across 12 months.', 20000, 10000, 5000, 5000
WHERE NOT EXISTS (SELECT 1 FROM public.case_study);

-- ──── Admin Events (Global per-month events) ────
CREATE TABLE IF NOT EXISTS public.events (
    id SERIAL PRIMARY KEY,
    month INTEGER,
    event_name TEXT,
    event_type TEXT,       -- 'fixed', 'percentage'
    impact_target TEXT,    -- 'cash', 'stocks', 'gold', 'expense_increase'
    value NUMERIC,
    description TEXT
);

-- ──── Optional Choices (player decisions per month) ────
CREATE TABLE IF NOT EXISTS public.optional_choices (
    id SERIAL PRIMARY KEY,
    month INTEGER,
    name TEXT,
    cost NUMERIC,
    risk_type TEXT,
    reward_type TEXT,
    reward_value NUMERIC,
    probability INTEGER
);

-- ──── Game Control (Singleton) ────
CREATE TABLE IF NOT EXISTS public.game_control (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    current_month INTEGER DEFAULT 1,
    game_status TEXT DEFAULT 'waiting',
    auto_events BOOLEAN NOT NULL DEFAULT false,
    auto_market BOOLEAN NOT NULL DEFAULT false
);

INSERT INTO public.game_control (id, current_month, game_status) VALUES (1, 1, 'waiting') ON CONFLICT (id) DO NOTHING;

-- ──── Player State (Single Source of Truth) ────
CREATE TABLE IF NOT EXISTS public.player_state (
    user_id UUID REFERENCES public.users(id) PRIMARY KEY,
    month INTEGER DEFAULT 1,
    cash NUMERIC DEFAULT 0,
    stocks NUMERIC DEFAULT 0,
    gold NUMERIC DEFAULT 0,
    emergency_fund NUMERIC DEFAULT 0,
    investment_portfolio JSONB NOT NULL DEFAULT '{}'::jsonb,
    loans NUMERIC DEFAULT 0,
    pending_cash_next_month NUMERIC DEFAULT 0,
    lifestyle_type TEXT,
    bike_status BOOLEAN DEFAULT false,
    bike_lock_in_months INTEGER DEFAULT 0,
    net_worth NUMERIC DEFAULT 0,
    trust_score NUMERIC DEFAULT 0,
    risk_level INTEGER DEFAULT 50,
    discipline_score NUMERIC DEFAULT 100,        -- ADR-008: running discipline average
    financial_health_score NUMERIC DEFAULT 0,    -- ADR-008: composite leaderboard score
    status TEXT DEFAULT 'active'  -- 'active' = needs to play, 'waiting' = turn locked
);

-- ──── Player Loans ────
CREATE TABLE IF NOT EXISTS public.player_loans (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id),
    principal NUMERIC,
    current_amount NUMERIC,
    interest_rate NUMERIC DEFAULT 0.12,
    month_taken INTEGER,
    status TEXT DEFAULT 'active'  -- 'active', 'paid'
);

-- ──── Player Asset Sales ────
CREATE TABLE IF NOT EXISTS public.player_sales (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id),
    asset_type TEXT,
    amount_sold NUMERIC,
    penalty NUMERIC,
    cash_to_receive NUMERIC,
    month_sold_in INTEGER,
    month_to_credit INTEGER
);

-- ──── Relative Events (Admin-defined social scenarios) ────
CREATE TABLE IF NOT EXISTS public.relative_events (
    id SERIAL PRIMARY KEY,
    month INTEGER,
    relative_type TEXT,
    scenario TEXT
);

-- ──── Player Relative Trust Scores ────
CREATE TABLE IF NOT EXISTS public.player_relative_score (
    user_id UUID REFERENCES public.users(id),
    relative_type TEXT,
    total_spent NUMERIC DEFAULT 0,
    trust_score INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, relative_type)
);

-- ──── Player Relative Actions Log ────
CREATE TABLE IF NOT EXISTS public.player_relative_actions (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id),
    month INTEGER,
    relative_type TEXT,
    action_taken TEXT,     -- 'none', 'medium', 'high'
    amount_spent NUMERIC
);

-- ──── Monthly Audit Logs ────
CREATE TABLE IF NOT EXISTS public.player_month_log (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id),
    month INTEGER,
    starting_cash NUMERIC,
    ending_cash NUMERIC,
    net_worth NUMERIC,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.case_study ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.optional_choices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.game_control ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_loans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.relative_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_relative_score ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_relative_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_month_log ENABLE ROW LEVEL SECURITY;

-- Public read policies
DROP POLICY IF EXISTS "Enable read/write for own user" ON public.users;
CREATE POLICY "Enable read/write for own user" ON public.users FOR ALL USING (auth.uid() = id);
DROP POLICY IF EXISTS "Enable read for all" ON public.case_study;
CREATE POLICY "Enable read for all" ON public.case_study FOR SELECT USING (true);
DROP POLICY IF EXISTS "Enable read for all" ON public.events;
CREATE POLICY "Enable read for all" ON public.events FOR SELECT USING (true);
DROP POLICY IF EXISTS "Enable read for all" ON public.optional_choices;
CREATE POLICY "Enable read for all" ON public.optional_choices FOR SELECT USING (true);
DROP POLICY IF EXISTS "Enable read for all" ON public.game_control;
CREATE POLICY "Enable read for all" ON public.game_control FOR SELECT USING (true);
DROP POLICY IF EXISTS "Enable read for all" ON public.relative_events;
CREATE POLICY "Enable read for all" ON public.relative_events FOR SELECT USING (true);

-- Player-specific policies
DROP POLICY IF EXISTS "Enable all for user state" ON public.player_state;
DROP POLICY IF EXISTS "Enable all for leaderboard read" ON public.player_state;
DROP POLICY IF EXISTS "Enable all for user sales" ON public.player_sales;
DROP POLICY IF EXISTS "Enable all for user loans" ON public.player_loans;
DROP POLICY IF EXISTS "Enable all for user score" ON public.player_relative_score;
DROP POLICY IF EXISTS "Enable all for user actions" ON public.player_relative_actions;
DROP POLICY IF EXISTS "Enable all for user logs" ON public.player_month_log;
-- SECURITY: clients get SELECT-only on their OWN rows. All writes go through
-- the Flask backend using the service_role key (which bypasses RLS). Using
-- "FOR ALL" here would let players write their own financial state (cash,
-- net_worth, ...) straight from the browser and cheat the leaderboard.
-- Do NOT restore FOR ALL on these tables. See security_fix_rls.sql.
DROP POLICY IF EXISTS "player_state read own" ON public.player_state;
CREATE POLICY "player_state read own" ON public.player_state FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "player_sales read own" ON public.player_sales;
CREATE POLICY "player_sales read own" ON public.player_sales FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "player_loans read own" ON public.player_loans;
CREATE POLICY "player_loans read own" ON public.player_loans FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "player_relative_score read own" ON public.player_relative_score;
CREATE POLICY "player_relative_score read own" ON public.player_relative_score FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "player_relative_actions read own" ON public.player_relative_actions;
CREATE POLICY "player_relative_actions read own" ON public.player_relative_actions FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "player_month_log read own" ON public.player_month_log;
CREATE POLICY "player_month_log read own" ON public.player_month_log FOR SELECT USING (auth.uid() = user_id);


-- Current runtime dependencies. Idempotent additions preserve existing game data.
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS trust_score NUMERIC DEFAULT 0;
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS risk_level INTEGER DEFAULT 50;
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'admin';
ALTER TABLE public.game_control ADD COLUMN IF NOT EXISTS marriage_round_active BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.game_control ADD COLUMN IF NOT EXISTS negotiation_enabled BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.game_control ADD COLUMN IF NOT EXISTS auto_events BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.game_control ADD COLUMN IF NOT EXISTS auto_market BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS discipline_score NUMERIC DEFAULT 100;
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS financial_health_score NUMERIC DEFAULT 0;
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS spouse_satisfaction NUMERIC NOT NULL DEFAULT 60;
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS household_expense_modifier NUMERIC NOT NULL DEFAULT 0;
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS insurance_plan TEXT NOT NULL DEFAULT 'none';
ALTER TABLE public.player_loans ADD COLUMN IF NOT EXISTS term_months INTEGER NOT NULL DEFAULT 6;
ALTER TABLE public.player_loans ADD COLUMN IF NOT EXISTS loan_type TEXT NOT NULL DEFAULT 'auto';
ALTER TABLE public.player_loans ADD COLUMN IF NOT EXISTS emi NUMERIC NOT NULL DEFAULT 0;
ALTER TABLE public.player_loans ALTER COLUMN interest_rate SET DEFAULT 0.012;

CREATE TABLE IF NOT EXISTS public.spouse_archetypes (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, income NUMERIC NOT NULL DEFAULT 0,
    expense_mod NUMERIC NOT NULL DEFAULT 0, stocks NUMERIC NOT NULL DEFAULT 0,
    gold NUMERIC NOT NULL DEFAULT 0, ef NUMERIC NOT NULL DEFAULT 0,
    loan NUMERIC NOT NULL DEFAULT 0, description TEXT
);
-- Python ARCHETYPES remains authoritative. Do not overwrite existing authored rows.
INSERT INTO public.spouse_archetypes
    (id, name, income, expense_mod, stocks, gold, ef, loan) VALUES
    ('saver', 'The Saver', 5000, -2500, 0, 12000, 23000, 0),
    ('earner', 'The Earner', 16000, 4500, 0, 0, 5000, 0),
    ('investor', 'The Investor', 4000, -1500, 35000, 16000, 4000, 0),
    ('anchor', 'The Anchor', 7000, -500, 5000, 0, 35000, 0),
    ('teacher', 'The Teacher', 6000, -1500, 2500, 6000, 29000, 0),
    ('healthcare', 'The Healthcare Professional', 11500, 2000, 2500, 0, 20000, 0),
    ('single', 'Single', 0, 0, 0, 0, 0, 0)
ON CONFLICT (id) DO NOTHING;
ALTER TABLE public.player_state ADD COLUMN IF NOT EXISTS spouse_archetype TEXT REFERENCES public.spouse_archetypes(id);
CREATE TABLE IF NOT EXISTS public.player_spouse_reveals (
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    archetype_id TEXT REFERENCES public.spouse_archetypes(id),
    trait_key TEXT NOT NULL CHECK (trait_key IN ('income', 'expense_mod', 'assets')),
    PRIMARY KEY (user_id, archetype_id, trait_key)
);
CREATE TABLE IF NOT EXISTS public.player_month_allocations (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    available_cash NUMERIC NOT NULL DEFAULT 0,
    to_stocks NUMERIC NOT NULL DEFAULT 0, to_gold NUMERIC NOT NULL DEFAULT 0,
    to_emergency_fund NUMERIC NOT NULL DEFAULT 0, to_loan_prepay NUMERIC NOT NULL DEFAULT 0,
    investment_allocations JSONB NOT NULL DEFAULT '{}'::jsonb,
    kept_as_cash NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (user_id, month)
);
ALTER TABLE public.player_state
    ADD COLUMN IF NOT EXISTS investment_portfolio JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.player_month_allocations
    ADD COLUMN IF NOT EXISTS investment_allocations JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE OR REPLACE FUNCTION public.investment_portfolio_value(p_portfolio JSONB)
RETURNS NUMERIC AS $$
    SELECT COALESCE(SUM((item.lot->>'value')::numeric), 0)
    FROM jsonb_each(COALESCE(p_portfolio, '{}'::jsonb)) AS product(key, lots)
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(product.lots) = 'array' THEN product.lots ELSE '[]'::jsonb END
    ) AS item(lot)
$$ LANGUAGE sql IMMUTABLE;

CREATE TABLE IF NOT EXISTS public.market_scenarios (
    id BIGSERIAL PRIMARY KEY, month INTEGER NOT NULL UNIQUE CHECK (month BETWEEN 1 AND 12),
    name TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
    stock_pct NUMERIC NOT NULL DEFAULT 0, gold_pct NUMERIC NOT NULL DEFAULT 0,
    regime TEXT DEFAULT 'authored', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.spouse_proposals (
    id BIGSERIAL PRIMARY KEY, archetype_id TEXT NOT NULL REFERENCES public.spouse_archetypes(id),
    month INTEGER CHECK (month BETWEEN 1 AND 12),
    kind TEXT NOT NULL CHECK (kind IN ('lifestyle', 'investment', 'saving', 'protection')),
    title TEXT NOT NULL, description TEXT NOT NULL,
    amount_min NUMERIC NOT NULL CHECK (amount_min >= 0),
    amount_max NUMERIC NOT NULL CHECK (amount_max >= amount_min),
    floor_ratio NUMERIC NOT NULL DEFAULT 0.6, ev_note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS public.spouse_dialogue (
    id BIGSERIAL PRIMARY KEY, archetype_id TEXT NOT NULL REFERENCES public.spouse_archetypes(id),
    outcome TEXT NOT NULL, line TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS public.player_negotiations (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    round INTEGER NOT NULL CHECK (round BETWEEN 1 AND 3),
    raw_text TEXT, intent TEXT NOT NULL, params JSONB NOT NULL DEFAULT '{}',
    confirmed BOOLEAN NOT NULL DEFAULT false, outcome TEXT NOT NULL DEFAULT 'pending',
    ai_source TEXT, rule_input JSONB, rule_output JSONB
);
CREATE INDEX IF NOT EXISTS negotiations_player_month ON public.player_negotiations(user_id, month, round);
CREATE UNIQUE INDEX IF NOT EXISTS negotiations_one_commit ON public.player_negotiations(user_id, month, round) WHERE confirmed;
CREATE INDEX IF NOT EXISTS proposals_archetype_month ON public.spouse_proposals(archetype_id, month);
CREATE INDEX IF NOT EXISTS dialogue_archetype ON public.spouse_dialogue(archetype_id);

ALTER TABLE public.spouse_archetypes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_spouse_reveals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_month_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spouse_proposals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spouse_dialogue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_negotiations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "player_spouse_reveals read own" ON public.player_spouse_reveals;
CREATE POLICY "player_spouse_reveals read own" ON public.player_spouse_reveals FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "allocations read own" ON public.player_month_allocations;
CREATE POLICY "allocations read own" ON public.player_month_allocations FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "negotiations read own" ON public.player_negotiations;
CREATE POLICY "negotiations read own" ON public.player_negotiations FOR SELECT USING (auth.uid() = user_id);
-- Spouse financial traits are revealed through the backend, not a public catalogue.
DROP POLICY IF EXISTS "Enable read for all" ON public.spouse_archetypes;
DROP POLICY IF EXISTS "market_scenarios read all" ON public.market_scenarios;
CREATE POLICY "market_scenarios read all" ON public.market_scenarios FOR SELECT
USING (month <= (SELECT current_month FROM public.game_control WHERE id = 1));


-- ============================================================================
-- ATOMIC MONTHLY PROCESSING RPC
-- Updated to handle trust_score and risk_level
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
        marriage_round_active = (p_next_month = 6),
        negotiation_enabled = (p_next_month = 7),
        game_status = 'active'
    WHERE id = 1;

    RETURN TRUE;

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

-- SECURITY (QA-001): this SECURITY DEFINER function mutates every player's
-- financial state and advances the game month, with no internal admin check
-- of its own — it relies entirely on only being callable by the trusted
-- Flask backend (service_role). Without this revoke, Postgres' default
-- EXECUTE-to-PUBLIC grant lets PostgREST expose it to anon/authenticated at
-- /rest/v1/rpc/process_month_atomically, bypassing admin_required entirely.
-- See security_fix_rpc_grants.sql for the standalone fix on existing projects.
REVOKE EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) FROM anon;
REVOKE EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.process_month_atomically(json, json, json, json, integer) TO service_role;

-- ============================================================================
-- ATOMIC SELL RPC (QA-003)
-- Locks the player row and performs check-decrement-credit as one atomic
-- unit, closing the read-then-write race in the old /sell implementation.
-- The canonical schema is the only supported installation/upgrade path.
-- ============================================================================
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
    IF p_month >= 12 THEN
        RAISE EXCEPTION 'FINAL_MONTH_SALE_NOT_ALLOWED';
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

-- ============================================================================
-- COMPLETENESS (F-02): objects the backend depends on that used to live in
-- separate SQL files. Folded in here so a FRESH INSTALL IS THIS ONE FILE, with
-- no missing files or hidden manual steps. All statements are idempotent.
-- The standalone files (admin_setup.sql, idempotency_migration.sql,
-- supabase_signup_trigger.sql) are retained ONLY for retrofitting an older
-- live project and for the admin-granting data step; they are NOT needed for a
-- fresh install. See DEPLOY_FRESH.md §2.
-- ============================================================================

-- ──── Admin allowlist (server-only; gates every admin route) ────
-- RLS ON with NO policies => anon/authenticated clients are fully denied; only
-- the Flask backend (service_role key) can read it, which is who checks admin.
CREATE TABLE IF NOT EXISTS public.admins (
    user_id    UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.admins ENABLE ROW LEVEL SECURITY;
-- (Grant a specific person admin AFTER install — see DEPLOY_FRESH.md §4a /
--  admin_setup.sql: insert their auth.users.id into public.admins.)

-- ──── Per-(user, month) action idempotency guard ────
-- Backs buy-choice / relative-help claims (game_service.mark_action). Without
-- this table those actions silently fail. RLS ON, no client policy (server-only).
CREATE TABLE IF NOT EXISTS public.player_month_actions (
    user_id     UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    month       INTEGER NOT NULL,
    action_key  TEXT NOT NULL,   -- e.g. 'choice:12' or 'relative:parent'
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    PRIMARY KEY (user_id, month, action_key)
);
ALTER TABLE public.player_month_actions ENABLE ROW LEVEL SECURITY;

-- ──── Signup trigger: auto-create a public.users row on account creation ────
-- public.player_state.user_id REFERENCES public.users(id); nothing in the Flask
-- backend inserts into public.users, so without this trigger the first
-- /allocate call FK-fails. SECURITY DEFINER so it can write public.users.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.users (id, email, name)
    VALUES (
        new.id,
        new.email,
        COALESCE(
            new.raw_user_meta_data->>'name',
            new.raw_user_meta_data->>'full_name',
            split_part(new.email, '@', 1)
        )
    )
    ON CONFLICT (id) DO NOTHING;   -- never clobber an existing profile
    RETURN new;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Backfill profiles for any auth users that already exist (harmless on a truly
-- fresh project; useful if test users were created before this ran).
INSERT INTO public.users (id, email, name)
SELECT u.id, u.email,
       COALESCE(u.raw_user_meta_data->>'name',
                u.raw_user_meta_data->>'full_name',
                split_part(u.email, '@', 1))
FROM auth.users u
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- FRESH INSTALL COMPLETE. Running this single file on an empty Supabase project
-- Current transaction contracts follow. Historical migration files are not replayed.
DROP FUNCTION IF EXISTS public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB);
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
    p_loan_updates        JSONB,    -- array of {id, current_amount, status} to UPDATE
    p_expected_investment_portfolio JSONB DEFAULT NULL -- optimistic concurrency for investment sale
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
        IF NOT g.marriage_round_active OR p_month != 6 OR v.spouse_archetype IS NOT NULL THEN
            RAISE EXCEPTION 'MARRIAGE_NOT_AVAILABLE';
        END IF;
    END IF;
    IF s ? 'status' AND s->>'status' = 'waiting' THEN
        IF p_month >= 2 AND v.cash > 0.5 AND NOT EXISTS (
            SELECT 1 FROM public.player_month_actions WHERE user_id = p_user_id
              AND month = p_month AND action_key = 'alloc:' || p_month)
            THEN RAISE EXCEPTION 'ALLOCATION_REQUIRED'; END IF;
        IF p_month = 6 AND v.spouse_archetype IS NULL
            THEN RAISE EXCEPTION 'MARRIAGE_DECISION_REQUIRED'; END IF;
        IF p_month = 7 AND v.spouse_archetype IS NOT NULL AND v.spouse_archetype <> 'single'
            AND NOT EXISTS (SELECT 1 FROM public.player_negotiations WHERE user_id = p_user_id
                AND month = p_month AND confirmed AND outcome IN
                ('accepted_full','accepted_counter','refused','delayed','auto_resolved'))
            THEN RAISE EXCEPTION 'FUNCTION_DECISION_REQUIRED'; END IF;
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
        IF p_month != 7 OR NOT g.negotiation_enabled OR v.spouse_archetype IS NULL OR v.spouse_archetype = 'single'
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
    IF p_expected_investment_portfolio IS NOT NULL
       AND COALESCE(v.investment_portfolio, '{}'::jsonb)
           IS DISTINCT FROM COALESCE(p_expected_investment_portfolio, '{}'::jsonb) THEN
        RAISE EXCEPTION 'PORTFOLIO_CHANGED';
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
        v_nw := v_cash + v_stocks + v_gold + v_ef
                + public.investment_portfolio_value(COALESCE(s->'investment_portfolio', v.investment_portfolio))
                - v_loans;
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
    IF s ? 'investment_portfolio' THEN
        UPDATE public.player_state SET investment_portfolio = COALESCE(s->'investment_portfolio', '{}'::jsonb)
        WHERE user_id = p_user_id;
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

-- Server-only, same lockdown as sell_asset_atomic / process_month_atomically.
REVOKE EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB, JSONB) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB, JSONB) FROM anon;
REVOKE EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB, JSONB) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.player_apply_atomic(UUID, INT, TEXT, NUMERIC, JSONB, JSONB, BOOLEAN, BOOLEAN, JSONB, JSONB, JSONB) TO service_role;



-- Freeze a synchronized round before Python reads any financial state.
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
          OR (month = 6 AND spouse_archetype IS NULL)
          OR (month = 7 AND spouse_archetype IS NOT NULL AND spouse_archetype <> 'single'
              AND NOT EXISTS (SELECT 1 FROM public.player_negotiations n
                  WHERE n.user_id = player_state.user_id AND n.month = 7 AND n.confirmed
                  AND n.outcome IN ('accepted_full','accepted_counter','refused','delayed','auto_resolved')));
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

-- Initial allocation and its claim/log must either all commit or all roll back.
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

-- All tables are RLS protected. Financial writes are backend-only.
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

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
COMMIT;
-- creates every table, RPC, function, trigger, RLS policy, and grant the
-- backend requires. The only post-install step is granting a specific admin
-- (data, not schema) — see DEPLOY_FRESH.md §4a.
-- ============================================================================
