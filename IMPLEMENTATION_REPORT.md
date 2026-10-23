# Money Master — Controlled Implementation Report

Date: 2026-10-21. Branch: `main`; working tree contains uncommitted changes. The checkout already contained workflow-audit edits before the investment work; those edits were preserved. No production database, deployment, secret, or environment file was accessed or changed.

## Result

The investment system is integrated with the existing allocation, monthly processing, player sale, dashboard, scoring, and leaderboard flows. Eleven simulated products use shared monthly conditions, product-specific fees and liquidity/maturity rules. Investment assets contribute to net worth and risk; current calculated household expenses feed liquidity scoring. Existing score weights are unchanged. The SIP Horizon Lab remains outside competition results.

`supabase.sql` is the repeatable canonical schema and upgrade path. The supplied archive's standalone investment migration is intentionally excluded because it replaces transaction functions with older contracts. Local schema tests cover fresh and repeat installation with row preservation. No hosted upgrade was run.

## Verification

- Full local Python suite: **128 tests ran; 2 native PostgreSQL concurrency tests skipped** because `pgserver` and `psycopg` are unavailable. The first run had one harness error from an inaccessible optional bundled Flask path; the test harness now falls back to the active interpreter's installed Flask.
- Isolated Flask/PostgreSQL API lifecycle suite: **7 tests passed**, including a complete 12-month lifecycle, portfolio persistence and sale, duplicate sale request, leaderboard ordering, and Month 12 sale rejection.
- Canonical schema tests include repeat-install/data-preservation, RPC permission, transactional rollback, household/insurance/loan persistence, and atomic reveal/negotiation writes.
- Deterministic strategy simulations passed for six baseline strategies and four investment strategies, both across baseline and authored-event conditions. Each run repeats identically across all 12 months; score weights are unchanged. The standalone command also wrote `.test-runtime/strategies.json`.
- `node --check` passed for `frontend/js/dashboard.js` and `frontend/js/allocation.js`; `git diff --check` reported no whitespace errors.

Limits: PGlite/WASM does not validate native concurrent clients or Supabase Auth/PostgREST semantics. No real browser, hosted staging database, deployment, load test, or production-data migration was exercised.

## Main files

- `backend/engine/investment_engine.py`, `backend/engine/monthly_processor.py`, `backend/engine/scoring.py`, and `backend/engine/market_engine.py`: product valuation, monthly lifecycle, risk and scoring integration.
- `backend/routes/player_routes.py`, `backend/routes/admin_routes.py`, and `backend/services/game_service.py`: validation, portfolio transactions, authoritative dashboard/leaderboard snapshots, and household-cost scoring.
- `supabase.sql`: canonical schema, persistent portfolio, transactional contracts, permissions, and Month 12 deferred-sale guard.
- `frontend/allocation.html`, `frontend/js/allocation.js`, `frontend/dashboard.html`, and `frontend/js/dashboard.js`: investment choices, tension preview, portfolio summary, and sale fee confirmation.
- `INVESTMENT_RULES.md`: game-only rates, fees, risk, liquidity, maturity, and exclusions.
- `backend/tests/test_investment_engine.py`, `backend/tests/test_api_lifecycle.py`, `backend/tests/test_runtime_database.py`, and `backend/tests/test_strategy_simulation.py`: calculation, route, database, and deterministic strategy coverage.
- `README.md`, `PRD.md`, `SRS.md`, `PROJECT_STATE.md`, and `IMPLEMENTATION_PLAN.md`: current behavior and installation guidance.
- `WORKFLOW_AUDIT_2026-10-19.md`: related outstanding defects and follow-up status.

## Repeatable local verification

From the repository root:

```powershell
python -m unittest discover -s backend/tests -v
node --check frontend/js/dashboard.js
node --check frontend/js/allocation.js
git diff --check
python backend/tools/strategy_simulation.py --output .test-runtime/strategies.json
```

When the isolated PGlite package is missing, install the documented local-only test dependency with `npm install --prefix .test-runtime --no-audit --no-fund @electric-sql/pglite@0.3.14`. Native concurrency checks need `pgserver` and `psycopg` on a supported host.

## Staging instructions

Review the complete diff and back up the intended database. Apply only `supabase.sql` to an isolated staging copy using an owner role, then run the route and lifecycle tests against that copy and verify the existing rows and RLS/grants. Do not replay historical migrations or the archive's standalone investment migration. Live rollout requires a separate explicit decision and a successful staging rehearsal; none is authorized or performed here.
