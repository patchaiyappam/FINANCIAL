-- Current-game attendance exception for the three unstarted accounts shown.
-- This does not delete accounts, allocate money, or advance the month.
BEGIN;
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

DO $$
DECLARE matches integer;
BEGIN
    PERFORM 1 FROM public.game_control
        WHERE id = 1 AND current_month = 1 AND game_status = 'active' FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'This attendance repair is only for an active Month 1 game.';
    END IF;
    SELECT count(*) INTO matches FROM public.users u
        WHERE split_part(u.email, '@', 1) IN ('cb22s612706', 'manoj', 'patchai2004')
          AND NOT EXISTS (SELECT 1 FROM public.admins a WHERE a.user_id = u.id)
          AND NOT EXISTS (SELECT 1 FROM public.player_state p WHERE p.user_id = u.id);
    IF matches = 0 THEN
        RAISE EXCEPTION 'No eligible unstarted non-admin accounts found. No changes applied.';
    END IF;
    INSERT INTO public.player_month_actions(user_id, month, action_key)
    SELECT u.id, 0, 'absent' FROM public.users u
        WHERE split_part(u.email, '@', 1) IN ('cb22s612706', 'manoj', 'patchai2004')
          AND NOT EXISTS (SELECT 1 FROM public.admins a WHERE a.user_id = u.id)
          AND NOT EXISTS (SELECT 1 FROM public.player_state p WHERE p.user_id = u.id)
    ON CONFLICT (user_id, month, action_key) DO NOTHING;
END;
$$;

NOTIFY pgrst, 'reload schema';
COMMIT;

SELECT u.email, 'Absent for this game' AS attendance
FROM public.users u JOIN public.player_month_actions a ON a.user_id = u.id
WHERE a.month = 0 AND a.action_key = 'absent'
ORDER BY u.email;
