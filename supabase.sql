-- ============================================================================
-- Supabase Schema for Money Master — Financial Simulation Game
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ──── Users ────
CREATE TABLE public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT,
    email TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- ──── Case Study (Scenario Setup) ────
CREATE TABLE public.case_study (
    id SERIAL PRIMARY KEY,
    title TEXT,
    description TEXT,
    rent NUMERIC,
    food NUMERIC,
    transport NUMERIC,
    family NUMERIC
);

INSERT INTO public.case_study (title, description, rent, food, transport, family)
VALUES ('The First Job', 'Manage ₹1,00,000 monthly income across 12 months.', 20000, 10000, 5000, 5000);

-- ──── Admin Events (Global per-month events) ────
CREATE TABLE public.events (
    id SERIAL PRIMARY KEY,
    month INTEGER,
    event_name TEXT,
    event_type TEXT,       -- 'fixed', 'percentage'
    impact_target TEXT,    -- 'cash', 'stocks', 'gold', 'expense_increase'
    value NUMERIC,
    description TEXT
);

-- ──── Optional Choices (player decisions per month) ────
CREATE TABLE public.optional_choices (
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
CREATE TABLE public.game_control (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    current_month INTEGER DEFAULT 1,
    game_status TEXT DEFAULT 'waiting'
);

INSERT INTO public.game_control (id, current_month, game_status) VALUES (1, 1, 'waiting');

-- ──── Player State (Single Source of Truth) ────
CREATE TABLE public.player_state (
    user_id UUID REFERENCES public.users(id) PRIMARY KEY,
    month INTEGER DEFAULT 1,
    cash NUMERIC DEFAULT 0,
    stocks NUMERIC DEFAULT 0,
    gold NUMERIC DEFAULT 0,
    emergency_fund NUMERIC DEFAULT 0,
    loans NUMERIC DEFAULT 0,
    pending_cash_next_month NUMERIC DEFAULT 0,
    lifestyle_type TEXT,
    bike_status BOOLEAN DEFAULT false,
    bike_lock_in_months INTEGER DEFAULT 0,
    net_worth NUMERIC DEFAULT 0,
    trust_score NUMERIC DEFAULT 0,
    risk_level INTEGER DEFAULT 50,
    status TEXT DEFAULT 'active'  -- 'active' = needs to play, 'waiting' = turn locked
);

-- ──── Player Loans ────
CREATE TABLE public.player_loans (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id),
    principal NUMERIC,
    current_amount NUMERIC,
    interest_rate NUMERIC DEFAULT 0.12,
    month_taken INTEGER,
    status TEXT DEFAULT 'active'  -- 'active', 'paid'
);

-- ──── Player Asset Sales ────
CREATE TABLE public.player_sales (
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
CREATE TABLE public.relative_events (
    id SERIAL PRIMARY KEY,
    month INTEGER,
    relative_type TEXT,
    scenario TEXT
);

-- ──── Player Relative Trust Scores ────
CREATE TABLE public.player_relative_score (
    user_id UUID REFERENCES public.users(id),
    relative_type TEXT,
    total_spent NUMERIC DEFAULT 0,
    trust_score INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, relative_type)
);

-- ──── Player Relative Actions Log ────
CREATE TABLE public.player_relative_actions (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id),
    month INTEGER,
    relative_type TEXT,
    action_taken TEXT,     -- 'none', 'medium', 'high'
    amount_spent NUMERIC
);

-- ──── Monthly Audit Logs ────
CREATE TABLE public.player_month_log (
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
CREATE POLICY "Enable read/write for own user" ON public.users FOR ALL USING (auth.uid() = id);
CREATE POLICY "Enable read for all" ON public.case_study FOR SELECT USING (true);
CREATE POLICY "Enable read for all" ON public.events FOR SELECT USING (true);
CREATE POLICY "Enable read for all" ON public.optional_choices FOR SELECT USING (true);
CREATE POLICY "Enable read for all" ON public.game_control FOR SELECT USING (true);
CREATE POLICY "Enable read for all" ON public.relative_events FOR SELECT USING (true);
CREATE POLICY "Enable all for leaderboard read" ON public.player_state FOR SELECT USING (true);

-- Player-specific policies
CREATE POLICY "Enable all for user state" ON public.player_state FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Enable all for user sales" ON public.player_sales FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Enable all for user loans" ON public.player_loans FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Enable all for user score" ON public.player_relative_score FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Enable all for user actions" ON public.player_relative_actions FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Enable all for user logs" ON public.player_month_log FOR ALL USING (auth.uid() = user_id);

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

    -- ✅ UPDATE PLAYER STATE
    UPDATE public.player_state ps
    SET
        month = (data->>'month')::int,
        cash = (data->>'cash')::numeric,
        stocks = (data->>'stocks')::numeric,
        gold = (data->>'gold')::numeric,
        emergency_fund = (data->>'emergency_fund')::numeric,
        lifestyle_type = data->>'lifestyle_type',
        bike_status = (data->>'bike_status')::boolean,
        loans = (data->>'loans')::numeric,
        pending_cash_next_month = (data->>'pending_cash_next_month')::numeric,
        bike_lock_in_months = (data->>'bike_lock_in_months')::int,
        net_worth = (data->>'net_worth')::numeric,
        trust_score = COALESCE((data->>'trust_score')::numeric, ps.trust_score),
        risk_level = COALESCE((data->>'risk_level')::int, ps.risk_level),
        status = data->>'status'
    FROM json_array_elements(p_updates_player_state) AS data
    WHERE ps.user_id = (data->>'user_id')::uuid;

    -- ✅ UPDATE LOANS
    UPDATE public.player_loans pl
    SET
        current_amount = (data->>'current_amount')::numeric,
        status = data->>'status'
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
        game_status = 'active'
    WHERE id = 1;

    RETURN TRUE;

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
