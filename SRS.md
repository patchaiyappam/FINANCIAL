# Money Master — Software Requirements Specification

**Version 1.1** · updated 2026-10-20
Architecture decisions: see `ARCHITECTURE_DECISIONS.md`. Product content: see `PRD.md`. This document specifies the system as **actually built** — contracts, invariants, and requirements that code does not self-document.

---

## 1. System Overview

Three-tier: static HTML/JS frontend → Flask (Python) backend → Supabase (PostgreSQL + Auth).

**Reality note:** the original preference was React + Tailwind; the shipped V1 frontend is plain HTML/CSS/JS pages calling the Flask API. This SRS documents reality. A React migration would classify as Level 2+ under ADR-013 and is not currently planned.

```
frontend/*.html  →  Flask (backend/app.py)
                      ├── routes/    player_routes.py, admin_routes.py
                      ├── services/  auth_service, game_service, choice_service
                      ├── engine/    monthly_processor, market_engine,
                      │              event_engine, scoring
                      └── models/    constants.py (single source of tuning truth)
                            ↓
                    Supabase PostgreSQL (+ RPC) / Supabase Auth
```

## 2. Module Responsibilities

- **engine/** — pure game logic. No HTTP, no direct DB writes (ADR-007 discipline). `monthly_processor.process_month_for_player` is the core loop: sales credit → salary → expenses (inflation-adjusted) → existing market growth and emergency interest → investment-lot returns/fees/maturities → events → bike EMI → loan EMI/interest → safety net + discipline grading → risk → net worth → Financial Health Score.
- **investment_engine** — product rules, lot lifecycle, risk/liquidity exposure, FIFO sale and exit fees. Product settings are simulation assumptions in `INVESTMENT_RULES.md`; the investment Horizon Lab is client-side and excluded from persisted competition results.
- **market_engine** — global market path (ADR-009): RNG seeded `GLOBAL:{month}:market`; identical returns for all players. Also net worth and 0–100 risk score.
- **event_engine** — per-player state-driven events (seeded `user_id:{month}:events`) + globally-seeded market events (`GLOBAL:{month}:market_events`) + admin event injection.
- **scoring** — composite Financial Health Score (ADR-008). Pure functions; formula public.
- **services/game_service** — DB reads, score-refreshed leaderboard, `fair_roll` (deterministic per `user_id:month:choice_id`), RPC payload validation.
- **routes/** — HTTP only: auth extraction, input validation, engine invocation, response shaping.

## 3. API Contract (summary)

**Player** (Supabase JWT required except status/leaderboard):
`GET /game-status` · `GET /case-study` · `POST /allocate` (Month 1; exact budget includes investment lots and validates finite nonnegative amounts and bike cost) · `POST /allocate-month` (monthly stocks, gold, emergency fund, investment lots, loan prepayment; cash remainder stays liquid) · `GET /dashboard` (state, refreshed derived score, investment summary, game and logs) · `POST /investment-sale-quote` · `POST /sell-investment` (idempotent request ID and portfolio compare-and-swap) · `GET /leaderboard` (current score desc, net worth tie-break) · existing asset-sale, insurance, loan, marriage and negotiation endpoints.

**Admin** (`admin_required`):
`POST /start-game` (wipes all player data — destructive, intentional) · `POST /next-month` (advances all players atomically; requires `expected_month` for race protection) · `POST /end-game` · `POST /event`, `DELETE /event/<id>` · `POST /choice-admin` · `GET /admin/players` · `POST /admin/update-player` (whitelist-field edit; net worth always recomputed server-side; audit-logged) · `POST /admin/reset-player`.

## 4. Data Model

Tables: `users`, `player_state` (1 row/player; includes `investment_portfolio JSONB`, `discipline_score`, `financial_health_score`), `player_loans`, `player_sales`, `player_month_allocations` (including investment allocations), `player_month_log` (append-only history/audit), `player_relative_score`, `player_relative_actions`, `events` (admin-authored), `optional_choices`, `case_study`, `game_control` (singleton: `current_month`, `game_status`). Each investment is a lot with value, principal, purchase month and optional maturity month.

Canonical DDL and upgrade path: `supabase.sql`; it is repeatable and preserves existing rows. Historical migrations are not an installation sequence and must not be replayed after the canonical file. Future household model (`households`, `owners` supertype): pending ADR-001/005 database design — **not yet implemented**.

## 5. Invariants (binding)

1. **Determinism (ADR-000):** all randomness is seeded. Market: global per month. Personal events: per `(user_id, month)`. Choice rolls: per `(user_id, month, choice_id)`. Same inputs → same outputs, always.
2. **Fairness:** no unseeded or per-player randomness may affect ranking. Market outcomes identical for all players in a month.
3. **Atomicity:** month advancement is one RPC (`process_month_atomically`) — locks `game_control` and player rows, validates the month transition, refuses to reprocess an already-logged month (idempotency), applies all state/loan/log changes or none.
4. **History is append-only:** financial history is never overwritten; `player_month_log` records every month and every admin correction.
5. **Server authority:** the client never supplies computed financials; net worth is recomputed transactionally and score/risk/net worth views are refreshed from the authoritative portfolio snapshot.
6. **No mid-game changes (ADR-012/013):** Level 3+ deploys and all migrations occur only between games.

## 6. Security Requirements

Supabase Auth JWTs; `admin_required` on all admin routes; RLS policies per `security_fix_rls.sql`; admin edits restricted to a field whitelist; any auth/RLS change classifies Level 4 (ADR-013). Secrets in `backend/.env`, never committed.

## 7. Deployment

Backend: Flask (Render or local `run_backend.bat`). Frontend: static hosting (Netlify, `netlify.toml`). Database: Supabase project; schema via SQL editor.

**Binding pair rule:** backend code and the matching canonical `supabase.sql` deploy together between games. `supabase.sql` is the repeatable installation/upgrade path; historical migrations are not replayed afterward. Any live upgrade requires a reviewed backup and staging rehearsal. No live database change is included in this implementation.

## 8. Verification Requirements

Any Level 3+ change must demonstrate before deploy: determinism (same inputs twice → identical outputs), cross-player market fairness, score bounds (0–100 at edges: bankruptcy, extreme wealth, deep debt), full 12-month simulation without error, and RPC payload validation. Reference suite: the 9 checks executed for the ADR-008/009 changes (2026-07-12). Performance claims in Section 9 require a load test at the target player count before being marked ✅.

## 9. Non-Functional Requirements

Compliance is stated honestly per requirement; ❌ items are open work, not aspirations recorded as fact.

| Category | Requirement | Status |
|---|---|---|
| Performance | Dashboard response < 2 s | ✅ (simple indexed reads) |
| Performance | Month processing < 10 s for 500 players | ❌ **Not met.** Per-player sequential queries in `/next-month` → ~50–100 s at 500 players. Known fix: batch-fetch loans/sales (2 queries total, group in memory). Level 3 change, pending. Honest current capacity: ~50–100 players. |
| Performance | Leaderboard generation < 1 s | ⚠️ Score refresh now reads portfolio snapshots; target-scale timing has not been load-tested. |
| Reliability | No partial financial commits; month processing atomic | ✅ (`process_month_atomically` RPC — Invariant 3) |
| Availability | Operational throughout live events | ✅ by process (no mid-game deploys, ADR-012); no HA infrastructure claimed |
| Availability | Admin recovery procedures documented | ❌ **Missing artifact.** No runbook exists for mid-event failures (backend down, wrong event published, month advanced early). Required before next live event. |
| Scalability | 500 concurrent players | ⚠️ Reads scale (Supabase); month processing blocked by the ❌ above; Flask needs multi-worker deployment (gunicorn) at that scale. |
| Scalability | Future multi-game architecture | ⚠️ `game_control` is a singleton row; multi-game requires a `game_id` dimension — future Level 4 design, noted in ADR-001/012 territory. |
| Maintainability | Business rules isolated; no financial calculations in routes | ✅ (engine/ modules; routes orchestrate only — ADR-007) |
| Auditability | Every financial mutation traceable; every admin action logged | ✅ (`player_month_log` append-only; admin edits audit-logged) |
| Security | JWT required, RLS enforced, secrets never committed | ✅ (Section 6) |

## 10. Traceability

| Requirement area | Authority |
|---|---|
| Priorities & conflicts | ADR-000 |
| Household / data foundation | ADR-001, ADR-005 (design pending) |
| Events | ADR-004, ADR-006, ADR-011 |
| Business rules discipline | ADR-007 |
| Scoring | ADR-008 |
| Market/economy | ADR-009 |
| AI (future) | ADR-003, ADR-010 |
| Versioning & deploy timing | ADR-012 |
| Change process | ADR-013 + workflow section |
