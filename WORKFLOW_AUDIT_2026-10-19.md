# Money Master workflow audit — 19 October 2026

## Scope and verdict

Reviewed the current local frontend, Flask routes, financial engines, negotiation services, canonical SQL and automated tests. Existing uncommitted changes were preserved. No application code or deployed service was changed.

Verdict: the ordinary lifecycle passes local tests, but the game has confirmed financial integrity and recovery defects. It is not ready to rely on for a competitive event without repairing the high priority findings below.

This is not a guarantee that every defect has been found. Real Supabase authentication, deployed browser behavior, production schema compatibility and native concurrent database sessions were not verified.

## Actual workflow

1. Admin provisions player accounts; players sign in using usernames mapped to event.local addresses.
2. Admin starts/restarts the game. Authored content is preserved; player data is deleted.
3. Player reads the case study and allocates Rs100,000, chooses City/Outer and optionally a bike. Most apparent expense buckets are retained as cash; only the bike down payment is consumed. Initial allocation automatically locks Month 1.
4. Admin advances only once registered non-admin players have allocated and current players have locked, except unstarted accounts marked absent.
5. Advancing to Months 2–12 credits pending sales, pays income, charges living costs/insurance, applies markets/events, services debt, covers deficits using emergency funds then automatic loans, and records the monthly score.
6. Players can change insurance, sell assets for next-month settlement, borrow once per month, and allocate cash once per month, including keeping cash. They then lock the turn.
7. In Month 4 the host can open marriage. Public family profiles show income, expenses, assets and debt. Players marry or stay single. Wedding cost and spouse assets/debt apply immediately; recurring spouse cash flow starts Month 5.
8. If enabled, married players interpret and confirm conversations. Month 6 uses the festival proposal. Other conversations use authored/default proposals. Confirmed effects change finances and satisfaction.
9. All players lock Month 12; the next advancement refreshes final scores and ends the game. Manual End Game takes a different path.
10. The leaderboard sorts Financial Health Score first and net worth second.

Optional opportunities and relative-help interfaces are intentionally hidden. Their APIs remain callable, which has consequences described below.

## Verification

- Existing suite: 114 tests run; 112 passed, 2 skipped. Skips are native PostgreSQL concurrency tests because pgserver/psycopg are unavailable.
- Additional isolated probes exercised real Flask routes and local PostgreSQL through the existing test adapter.
- Probe script: `.test-runtime/audit_probe.py`. It never uses configured live Supabase credentials.
- Local lifecycle coverage uses offline AI and fixture authentication; it does not establish production readiness.

## High priority findings

### 1. Resetting a player after Month 1 blocks the game

Evidence: runtime reproduced. `/admin/reset-player` deletes player state at any month; `/allocate` and `initialize_player` accept only Month 1. At Month 2, reset returned success, reallocation returned 400, and advancement returned 409 with one unallocated player.

Impact: the reset player cannot rejoin, while readiness prevents everyone else advancing. The interface explicitly promises they can allocate again.

Locations: `backend/routes/admin_routes.py: reset_player`; `backend/routes/player_routes.py: allocate_month1`; `supabase.sql: initialize_player, begin_month_transition`.

Repair: reject this reset after Month 1, or implement an explicit current-month re-entry/restoration transaction. Until repaired, use an in-place correction instead of reset during an event.

### 2. Bike purchase does not enforce the down payment

Evidence: runtime reproduced. `POST /allocate` with `misc=100000`, `bike_status=true`, `bike_down_payment=0` returns 200, retains Rs100,000 cash and enables the bike.

Impact: a caller can avoid the intended Rs10,000 purchase cost and receive the transport discount. Frontend defaults do not protect the API.

Location: `backend/routes/player_routes.py: allocate_month1`.

Repair: derive the down payment from BIKE_DOWN_PAYMENT whenever a bike is selected; reject inconsistent payloads and validate each individual bucket.

### 3. Admin debt corrections change a summary, not actual debt

Evidence: runtime reproduced. Borrowed Rs20,000, then corrected `loans` to zero. Stored player_state debt became zero, but `/dashboard` still reported Rs20,000 from player_loans. The next monthly engine also uses those actual loan rows.

Impact: the correction is ineffective and scores can temporarily use a different debt figure from the dashboard and repayments.

Location: `backend/routes/admin_routes.py: update_player`; `backend/routes/player_routes.py: get_dashboard`; `backend/engine/monthly_processor.py: loan processing`.

Repair: correct actual loan records and derive their aggregate in one transaction. A scalar debt field is insufficient to specify loan terms and balances.

### 4. Restart/reset operations are not atomic and bypass the game transition lock

Evidence: code confirmed. `/start-game` publishes active Month 1 before executing separate table deletions; `/admin/reset-player` also deletes tables through separate requests. Neither operation uses the shared transactional freeze protocol.

Impact: a failed deletion leaves partial game data; players can initialize between restart steps and have their fresh state deleted. A restart or correction overlapping an in-flight monthly batch can conflict with or be overwritten by that batch. Native concurrent reproduction remains unverified.

Location: `backend/routes/admin_routes.py: start_game, reset_player, update_player`.

Repair: use a single database transaction with the same game lock as month advancement; reject incompatible operations during processing.

### 5. Intentionally hidden optional mechanics remain financially usable

Evidence: code confirmed. `/buy-choice` and `/handle-relative` remain available to authenticated playable users. `execute_choice` fetches a choice by ID without checking that its authored month equals the player's current month. Its claim uses the current month, allowing the same authored choice again in later months.

Impact: API-capable players can access opportunities other players do not see, and buy past/future opportunities. Hidden relative help can also affect trust and automatic event probabilities.

Locations: `backend/routes/player_routes.py: buy_choice, handle_relative`; `backend/services/choice_service.py: execute_choice`.

Repair: enforce the organizer's disabled-feature decision on the backend. If opportunities return later, check the authored month and feature flag before applying effects.

## Medium priority findings

### 6. Month 12 sales settle in a nonexistent Month 13

Evidence: runtime reproduced. Selling Rs1,000 of stock in Month 12 returns success, removes stock and schedules Rs900 for Month 13. Normal finalization never processes that month.

Impact: the player loses the receivable at game end. Snapshot scoring also ignores pending sale receivables, so interim net worth is incomplete after a sale.

Locations: `supabase.sql: sell_asset_atomic`; `backend/engine/scoring.py: score_player_snapshot`.

Repair: disallow final-month sales or settle them during finalization; consistently include pending receivables in net worth if they are intended to remain assets.

### 7. Financial actions leave displayed ranking scores stale

Evidence: runtime reproduced. A Month 2 emergency-fund investment left stored FHS at 62.25, while the existing snapshot scorer calculated 63.59. Monthly allocation does not refresh risk/FHS. Sales and several other mutations also leave derived values unchanged.

Impact: current standings and player feedback do not reflect actual holdings until the next monthly processing or normal finalization.

Locations: `backend/routes/player_routes.py: allocate_month, sell_asset`; `supabase.sql: player_apply_atomic, sell_asset_atomic`.

Repair: use one consistent snapshot refresh after every relevant financial mutation, within the transaction or through authoritative read-time calculation.

### 8. Manual End Game publishes stale final results

Evidence: code confirmed. `/end-game` only writes game_status=ended; it does not run the score refresh used by normal Month 12 finalization. Combined with finding 7, a final allocation can change the correct ranking without changing the published result.

Location: `backend/routes/admin_routes.py: end_game`.

Repair: use a locked final snapshot transaction for both completion paths, with an explicit policy for early termination.

### 9. Repeated-argument penalties never receive the saved previous category

Evidence: code confirmed. `negotiate_commit` reads `rule_input.primary_category` from the previous confirmed round, but its saved rule_input contains only ask, round, satisfaction and required_minimum.

Impact: the repeated-category discount in spouse_character_service receives None in the actual workflow. Unit tests of the standalone character evaluator do not catch the integration omission.

Locations: `backend/routes/player_routes.py: negotiate_commit`; `backend/services/spouse_character_service.py: evaluate_character`.

Repair: persist the validated argument features/category used for evaluation, then reuse those recorded features on confirmation/retry.

### 10. Household liquidity scoring excludes actual household obligations

Evidence: code confirmed. The monthly and final snapshot scorers use inflated base living costs with bike savings, excluding spouse costs, satisfaction drift and negotiated household modifiers. `household_expenses` already calculates these amounts for actual charges and display. Admin corrections use an even different, uninflated base expense.

Impact: emergency-fund coverage is scored against a different budget from actual recurring household spending; identical states can receive different scores depending on the scoring path.

Locations: `backend/engine/monthly_processor.py: FHS calculation`; `backend/engine/scoring.py: score_player_snapshot`; `backend/routes/admin_routes.py: update_player`.

Repair: define the intended expense denominator explicitly and use one shared expense calculation in all scoring paths. Including premiums/debt payments requires an explicit rules decision.

### 11. Spouse-loan EMIs are omitted from borrowing affordability

Evidence: code confirmed. Marriage inserts inherited debt without an EMI, which defaults to zero. Both the loan gate and dashboard sum stored EMI values; the monthly processor instead calculates an amortized EMI when the stored value is zero.

Impact: actual monthly debt service exceeds the amount used to approve/display additional borrowing.

Locations: `backend/routes/player_routes.py: courtship_marry, take_loan, get_dashboard`; `supabase.sql: player_apply_atomic`; `backend/engine/monthly_processor.py: loan processing`.

Repair: persist a calculated EMI for every loan or share the processor's fallback calculation across the gate and dashboard.

### 12. Input validation accepts invalid allocations and crashes on malformed sales

Evidence: runtime reproduced. Initial allocation accepts `rent=-100000, misc=200000` because it validates aggregated cash instead of each bucket. A sale amount of `oops` raises an uncaught ValueError; Flask production handling would return 500. Multiple financial routes parse floats without rejecting NaN/Infinity explicitly; those nonfinite cases were not runtime verified.

Impact: malformed requests bypass stated constraints or produce server errors instead of useful validation responses. This negative-bucket example preserves the total; it alone is not proof of unlimited-money creation.

Locations: `backend/routes/player_routes.py: allocate_month1, allocate_month, sell_asset, take_loan`; admin financial input handlers.

Repair: validate request shape and every numeric field for type, finiteness, range and supported precision before computing totals.

### 13. AI argument evaluations are recomputed at confirmation and not preserved

Evidence: code confirmed. Confirmation calls `extract_argument_features` again, and its outputs influence the effective negotiation floor through character evaluation. The committed record does not preserve the full argument features or extraction source; ai_source is saved as rules.

Impact: the same confirmed text can receive different monetary thresholds after model variation, an outage or a retry. Offline deterministic tests do not cover that live path. The deterministic rule evaluator alone does not make the complete AI-assisted workflow reproducible.

Locations: `backend/routes/player_routes.py: negotiate_commit`; `backend/services/ai_service.py: extract_argument_features`; `backend/services/spouse_character_service.py`.

Repair: extract, validate and persist argument features at interpretation; confirm against the saved immutable evaluation inputs and preserve model/fallback provenance.

## Additional issues and decisions

- Marriage remains optional, but if the host opens it after some Month 4 turns are already locked, those players cannot make a decision while unlocked players can. Require an explicit round-opening policy before locking begins, or a coordinated reopen path. This is a workflow timing risk, not a reproduced concurrency failure.
- Admin spouse editing can change the selected archetype without reconciling injected assets, debt, wedding cost or satisfaction; null/empty spouse values are ignored, so the blank selection cannot clear a spouse. Replace the raw field editor with explicit correction operations.
- Event logs and toast messages interpolate text into innerHTML. Authored event descriptions can therefore render active HTML on player dashboards. Use textContent or escaping. Current demonstrated input source is trusted admin content; a low-privilege exploit was not established.
- Every initial non-bike rent/food/family/transport bucket becomes cash, and does not determine future living costs. The interface should explain this clearly or simplify the buckets. This behavior is documented, so it is a design clarity issue rather than proof of a calculation bug.
- Monthly allocation tolerates Rs1 overspend and SQL snaps small negative cash to zero, creating a small amount of money; prepayment also tolerates exceeding actual debt by Rs0.50. Use exact currency rounding instead of forgiving spends after the fact.
- The existing balance report flags that all six fixed uninsured single strategies fall into debt with the authored event pack. This is a stress-test signal, not proof that adaptive play or married/insured play cannot succeed. A realistic multi-player rehearsal remains necessary.

## Recommended repair order

1. Repair reset/restart safety, enforce bike cost, reconcile debt corrections, and enforce disabled mechanics server-side.
2. Unify finalization and derived scoring; resolve last-month sale settlement and household expense scoring.
3. Repair negotiation history/provenance, EMI affordability and numeric validation.
4. Add regression coverage for the reproduced failures and run native concurrent PostgreSQL checks.
5. Rehearse the complete event with real staging Supabase accounts and browsers before deployment.

## Follow-up status — 2026-10-21

This implementation fixed several findings above:

- **Finding 6 (Month 12 deferred sales): fixed.** `/sell` rejects final-month requests and `sell_asset_atomic` repeats the guard under the database transaction. The lifecycle regression confirms no asset decrement or sale record.
- **Finding 7 (stale derived ranking values): fixed for current player views and standings.** Dashboard and leaderboard calculate authoritative snapshots from current balances and investment lots. Investment exits use compare-and-swap persistence; month-end processing and finalization recalculate score. Stored scores may still lag between non-investment mutations not covered by a snapshot refresh.
- **Finding 10 (household expense denominator): fixed for monthly processing, final snapshot and admin corrections.** All use the shared current household expense calculation. Premiums and debt service are not added to that denominator; the scoring definition remains living/household expenses.
- **Finding 12 (financial numeric validation): fixed for initial allocation, monthly allocation, asset/investment sales, loan amount and quotes.** Individual initial buckets and finite currency amounts are validated. Admin input paths need separate review.

The following audit findings remain open and were not expanded in this investment change: restart/reset is not a single transaction; hidden optional-choice/relative APIs remain callable; manual early End Game does not share normal finalization; negotiation argument features are recomputed instead of persisted; spouse-loan EMI affordability can differ from monthly charges; marriage-round opening can strand locked Month 4 players; admin spouse edits can desynchronize archetype economics; admin-authored text is inserted into HTML without escaping; initial budget bucket labeling is unclear; small loan prepayment tolerance remains; native concurrency and a real event rehearsal remain unverified.
