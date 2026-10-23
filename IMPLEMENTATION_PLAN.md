# Controlled implementation

Starting point: clean `main` on 2026-09-08. No production database operations.

1. Reconcile runtime tables, columns, grants and RPCs in `supabase.sql`; make this
   the repeatable installation/upgrade path. Preserve existing rows.
2. Serialize month advancement and player actions using the existing database
   locks. Persist negotiation results and reveal records with their money changes.
3. Render authoritative wedding/reveal values and calculated household expenses.
   Keep optional choices hidden (explicit organizer decision in dashboard.js).
4. Add database/route regressions and deterministic 12-month strategy and lifecycle
   runs. Keep score weights unchanged. Record verification limits honestly.
5. Update current documentation and produce the implementation report.

## Dependency map

| Application | Table / columns | RPC | Previous definition |
| --- | --- | --- | --- |
| game_service, monthly_processor, investment_engine | player_state: all engine fields plus investment_portfolio JSONB lots | process_month_atomically, player_apply_atomic | supabase.sql, missing household/insurance fields and portfolio persistence |
| game_service.apply_player_txn | state balances, action keys, loan rows | player_apply_atomic | a01_atomic_player_txn_migration.sql only |
| monthly allocation | player_month_allocations: available_cash, to_stocks, to_gold, to_emergency_fund, to_loan_prepay, kept_as_cash | player_apply_atomic for balances | v2_migration.sql |
| market/admin routes | market_scenarios: month, name, reason, stock_pct, gold_pct, regime | monthly RPC persists effects | v2_migration.sql |
| loan routes/engine | player_loans: term_months, loan_type, emi plus original columns | both transaction RPCs | v2_migration.sql |
| courtship routes | spouse_archetypes, player_spouse_reveals; state.spouse_archetype | player_apply_atomic | marriage_migration.sql; single sentinel absent |
| negotiation routes | player_negotiations: user_id, month, round, raw_text, intent, params, confirmed, outcome, ai_source, rule_input, rule_output | player_apply_atomic | no executable definition found |
| proposal routes/negotiation engine | spouse_proposals: archetype_id, month, kind, title, description, amount_min/max, floor_ratio, ev_note | none | no executable definition found |
| ai_service.narrate | spouse_dialogue: archetype_id, outcome, line | none | no executable definition found |
| engine/insurance/negotiation | state.spouse_satisfaction, household_expense_modifier, insurance_plan | both transaction RPCs | no executable definition found |
| admin/event seed/insurance | events.category | monthly RPC persists effects | missing from canonical schema |
| admin/player gates | game_control.marriage_round_active, negotiation_enabled | transaction gates | marriage migration; negotiation flag absent |
| auth, sales, relatives, logs, choices | users, admins, case_study, player_sales, relative_events, player_relative_score/actions, player_month_log, optional_choices, player_month_actions | sell_asset_atomic, signup trigger | supabase.sql |
| investment allocation and exits | player_state.investment_portfolio; player_month_allocations.investment_allocations | player_apply_atomic with portfolio compare-and-swap for exits | canonical supabase.sql |

The canonical schema will retain the original tables and policies, add the missing
runtime objects, and replace only the functions whose contracts require repair.
Historical migrations remain historical; they must not be replayed afterward.

The strategic investment feature uses the same canonical `supabase.sql` path. The
standalone migration from the supplied archive is excluded because it redefines
older transaction functions and is unnecessary when the canonical schema is run.
No production database operation is part of this implementation.
