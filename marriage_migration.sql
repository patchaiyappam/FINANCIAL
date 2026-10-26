-- ============================================================================
-- SQL Migration for Money Master — Marriage & Courtship Feature (ADR-002)
-- ============================================================================

-- ──── 1. Add marriage_round_active to game_control ────
ALTER TABLE public.game_control
ADD COLUMN IF NOT EXISTS marriage_round_active BOOLEAN NOT NULL DEFAULT false;

-- ──── 2. Create spouse_archetypes table ────
CREATE TABLE IF NOT EXISTS public.spouse_archetypes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    income NUMERIC NOT NULL DEFAULT 0,
    expense_mod NUMERIC NOT NULL DEFAULT 0,
    stocks NUMERIC NOT NULL DEFAULT 0,
    gold NUMERIC NOT NULL DEFAULT 0,
    ef NUMERIC NOT NULL DEFAULT 0,
    loan NUMERIC NOT NULL DEFAULT 0,
    description TEXT
);

-- Seed spouse_archetypes
-- ⚠ CANONICAL SOURCE OF TRUTH IS backend/models/constants.py ARCHETYPES.
-- These rows are a MIRROR of that dict and MUST stay byte-for-byte in sync with
-- it (income, expense_mod, stocks, gold, ef, loan). The backend engine reads the
-- Python constant, NOT this table, so any drift here is silently wrong AND — via
-- the ON CONFLICT DO UPDATE below — a re-run would overwrite the tuned live values
-- with whatever is written here. test_archetype_source_consistency guards this.
-- Values below match constants.ARCHETYPES as of the 2026-08-13 audit (D-01 fix).
INSERT INTO public.spouse_archetypes (id, name, income, expense_mod, stocks, gold, ef, loan, description) VALUES
('saver', 'The Saver', 5000, -2500, 0, 12000, 23000, 0, 'Runs the household lean and brings gold and savings. Low income, but she cuts your monthly costs and hands you a cushion.'),
('earner', 'The Earner', 16000, 4500, 0, 0, 5000, 0, 'The strongest second income by far, but a bigger lifestyle to match. Steady cash every month, almost nothing up front.'),
('investor', 'The Investor', 4000, -1500, 35000, 16000, 4000, 0, 'Brings a built portfolio rather than a salary. Worth the most if the market rises, the least if it stalls — a bet on the economy.'),
('anchor', 'The Anchor', 7000, -500, 5000, 0, 35000, 0, 'A large emergency fund and dependable income. Boring on paper; the reason you survive a bad month.'),
('teacher', 'The Teacher', 6000, -1500, 2500, 6000, 29000, 0, 'Steady teaching income, modest living costs and a savings buffer. Values a thoughtful family gathering over an expensive venue.'),
('healthcare', 'The Healthcare Professional', 11500, 2000, 2500, 0, 20000, 0, 'Higher income with higher everyday costs. Wants the family function to feel special, but will discuss a practical budget.')
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  income = EXCLUDED.income,
  expense_mod = EXCLUDED.expense_mod,
  stocks = EXCLUDED.stocks,
  gold = EXCLUDED.gold,
  ef = EXCLUDED.ef,
  loan = EXCLUDED.loan,
  description = EXCLUDED.description;

-- ──── 3. Add spouse fields to player_state ────
ALTER TABLE public.player_state
ADD COLUMN IF NOT EXISTS spouse_archetype TEXT REFERENCES public.spouse_archetypes(id) DEFAULT NULL;

-- ──── 4. Create player_spouse_reveals table ────
CREATE TABLE IF NOT EXISTS public.player_spouse_reveals (
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    archetype_id TEXT REFERENCES public.spouse_archetypes(id) ON DELETE CASCADE,
    trait_key TEXT NOT NULL,
    PRIMARY KEY (user_id, archetype_id, trait_key)
);

-- Enable RLS on player_spouse_reveals
ALTER TABLE public.player_spouse_reveals ENABLE ROW LEVEL SECURITY;

-- Add read own policy (mirroring player_state policies)
CREATE POLICY "player_spouse_reveals read own" ON public.player_spouse_reveals
    FOR SELECT USING (auth.uid() = user_id);

-- Reference tables public-read policy (mirroring events/choices)
ALTER TABLE public.spouse_archetypes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Enable read for all" ON public.spouse_archetypes FOR SELECT USING (true);
