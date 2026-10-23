# Money Master - Current Project State

Base state documented 2026-09-08 after controlled implementation. Strategic
investment update: 2026-10-20. Old RC/audit documents remain historical.

## Scope and repository

The supplied starting-point note references clean `main` on 2026-09-08. The
workspace inspected for this implementation already contained uncommitted
workflow-audit changes; they were retained. Changes remain uncommitted.
No live database, Render deployment or Netlify deployment was changed or inspected.

The existing concept is preserved: 12 admin-paced months, recurring allocation,
insurance, loans, Month 4 marriage, Month 6 festival, spouse negotiations and
Financial Health Score. No score weights or spouse archetype economics changed.

The 2026-10-20 investment update adds eleven simulated products to the existing
allocation/monthly processing flow. It uses portfolio lots in player_state,
shared monthly market scenarios, modeled fees, early exits and maturity. The
Horizon Lab remains outside competition scoring. The current workspace already
had uncommitted workflow-audit changes when this update began; they were retained.
No hosted database, deployment, or environment file was changed.

## Database

Use supabase.sql as the canonical installation/upgrade path. It now includes all
runtime tables, household/insurance/loan fields, event categories, investment
portfolio storage and transaction functions. The file is repeatable and
transactional. Existing rows are retained. Do not apply the standalone investment
migration from the supplied archive or replay historical migrations after it.

Fresh installation, repeat installation, rollback behavior, runtime table/RPC
coverage and monthly state persistence have local PostgreSQL test coverage.
The dependency map is in IMPLEMENTATION_PLAN.md.

## Repairs

- Database-backed readiness gate counts unlocked and not-yet-allocated players.
  A shared game lock serializes player transactions against month freezing.
- Initial allocation writes state, action claim and log in one transaction.
- Month processing persists all fields returned by the engine, including spouse,
  satisfaction, household modifiers, insurance and new-loan terms.
- Negotiation confirmation and financial effects commit together; confirmation
  must match the saved intent parameters.
- Reveal charging and the reveal record are atomic. Insurance uses the existing
  atomic player transaction.
- Staying single is valid under the spouse foreign key.
- Month 12 finalization recalculates final scores and then ends the game atomically.
- Wedding and revealed traits render backend data. Expense displays use current
  backend values; the lifestyle-selector callback scope is repaired.
- Event entry preserves its category, with category selection in the admin form.
- Zero spouse satisfaction is retained instead of resetting to the default.
- Investment purchases join the current monthly allocation transaction; sale
  snapshots use row locking, compare-and-swap and a required idempotency key.
- Shared scenarios drive product returns; fees and maturities run in monthly
  processing. Month 12 next-month asset sales are blocked, while investment exits
  are immediate and quoted before confirmation.
- Current dashboard and leaderboard scores recalculate from the latest portfolio
  snapshot, so investment mutations appear before the next monthly roll.

Optional choices intentionally remain hidden. Backend functionality is preserved.

## Verification and limits

The isolated lifecycle exercises the actual Flask routes and canonical SQL through
12 months, including marriage, insurance, a voluntary loan, sale credits, the
festival and a later spouse conversation. Authentication is a local test fixture;
AI uses its supported offline path. This is not a deployed Supabase/browser test.

PGlite supplies a local PostgreSQL engine. Native simultaneous-client tests require
pgserver/psycopg and remain skipped on this machine. They now reference the
canonical schema rather than the historical atomic migration.

The six-strategy simulation compares a baseline and the existing event pack.
Healthy liquidity wins over greater risky wealth in the baseline. The event-pack
stress path drives all six fixed, uninsured, single strategies into debt. This is
a content/balance review signal, not proof that no adaptive strategy can succeed.
Weights and event content were left unchanged.

## Next acceptance checks

1. Apply the canonical schema to an isolated Supabase staging project and verify
   real account login, RLS, PostgREST RPC discovery and the deployed UI.
2. Run native PostgreSQL concurrency checks and a multi-player rehearsal.
3. Review authored content using insurance, spouse choices and adaptive strategies
   before selecting the actual pilot schedule.
4. Deploy only after those checks; live version and data are currently unverified.

Detailed results, per-file changes and the verdict are in IMPLEMENTATION_REPORT.md.
Product formulas and limits are in INVESTMENT_RULES.md.
