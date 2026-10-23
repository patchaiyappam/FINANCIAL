# Money Master - Product Requirements Document

Current implementation: 2026-10-20. Owner: A. Patchaiyappan.
This document reflects executable behavior; historical design documents may
describe older costs, marriage timing or future household architecture.

## Purpose and audience

Money Master is a financial life simulation for college students at a live
competition. The administrator controls the pace while students learn through
the financial consequences of their decisions.

## Game structure

There are 12 months. Month 1 starts with Rs1,00,000 and the initial allocation.
The initial living-cost buckets remain cash reserves; the engine charges
recurring living expenses from Month 2 onward. A bike down payment is consumed.

From Months 2-12, the engine adds Rs1,00,000 salary and processes the month.
Players then make decisions and submit their monthly allocation, which may retain
cash. Players with more than Rs0.50 cash must record allocation before locking.

Month advancement is synchronized. All player states must be in the current month
and locked; all provisioned non-admin users must have completed initial allocation.
The administrator receives the number of unready players instead of a partial
advancement. Manual start, settings, corrections, reset and end controls remain.

## Financial decisions

- Lifestyle: City base costs Rs88,000/month; Outer Rs82,000/month.
- Investments: stocks and gold follow a common market scenario; emergency funds
  earn 0.5% monthly. Authored markets take precedence over automatic generation.
- Additional investment lots: 3-month bank FD, 6-month Treasury bill, liquid and
  arbitrage funds, Nifty 50 index, flexi-cap equity, balanced advantage, Gold ETF,
  locked PPF/NPS, and a fictional business/resale venture. Shared market scenarios,
  monthly game fees, early-exit costs and automatic maturities are described in
  INVESTMENT_RULES.md. These are simulation assumptions, not current market rates.
  Month 12 final standings include unmatured and retirement holdings as assets.
- Monthly allocation can buy additional investment products from available cash.
  Sales apply immediately with the quoted exit cost. Month 12 sales credited in
  the next month are blocked because that month is never processed.
- Bike: Rs10,000 down payment, Rs5,000 EMI, three-month lock-in and 50% transport
  savings under the existing rules.
- Asset sales: 10% penalty; proceeds arrive next month.
- Voluntary loans: minimum Rs10,000; 3, 6 or 12-month terms; 1.2% monthly interest.
  Existing debt and EMI limits apply. Forced deficit loans use 2.5% monthly interest.
- Insurance: no cover, Basic (Rs2,500/month, 50% eligible coverage), or Comprehensive
  (Rs6,000/month, 80%). Premiums begin at subsequent monthly processing.
  Medical and emergency cash losses are eligible; market losses are not.
- Optional choices: backend and admin support remains, but the player UI keeps
  them hidden by the organizer's explicit decision. Relative-help routes also remain.

Inflation is 0.5% monthly from Month 4. The dashboard distinguishes base living
costs from current household costs, including inflation, bike savings, spouse
expenses and relationship/negotiated modifiers. Insurance premiums and loan EMIs
are separate obligations.

## Marriage and spouse

In Month 4, the administrator may open marriage. Candidates are Saver, Earner,
Investor and Anchor. A player may reveal income, expenses and assets. Three
distinct reveals are free; later reveals cost Rs5,000 each. Repeating an existing
reveal is free. Choosing a spouse or staying single is final for this game.

A wedding costs Rs25,000. The spouse's assets/liabilities and current-month net
income/expense flow apply once at marriage; subsequent monthly processing applies
recurring income and expenses. These values remain on player_state. There is no
new household ownership model in this implementation.

If the round is open, players must choose spouse or single before locking Month 4.
The database rechecks timing, round availability and prior selection atomically.

When the administrator enables conversations, the spouse makes a proposal.
The player sends a message, sees the interpreted intent and parameters, and
confirms it. The deterministic evaluator controls the amount, satisfaction and
household effects. The confirmed result and financial changes commit together.

Month 6 is the family festival, a one-time consumption decision. Other months use
authored or built-in proposals, including saving, protection, investment and
lifestyle requests. The existing character model affects negotiations. AI remains
an interpretation/narration layer and has an offline fallback.

## Events and content

Auto events and auto markets default to off. Admin-authored events and markets
remain effective in manual mode. Automatic personal events, when enabled, depend
on player state and deterministic seeds. All players share the monthly market path.

The repository contains a months 2-12 event/optional-choice seed pack. Its presence
does not imply it is installed in any live database. Event categories are preserved
from admin entry or seeding through processing and insurance classification.

## Winning and completion

Financial Health Score weights remain:

| Component | Weight |
| --- | ---: |
| Normalized net worth | 40% |
| Emergency-fund liquidity | 15% |
| Debt control | 15% |
| Risk protection | 15% |
| Discipline | 15% |

Leaderboard order is Financial Health Score descending, then net worth descending.
Monthly processing calculates the score. Dashboard and leaderboard views also
recalculate derived score and net worth from current holdings so purchases and
sales are reflected before the next monthly roll. Final completion, after Month 12
turns are locked, refreshes it from the final portfolios before ending the game.

## Operational status

The canonical schema and isolated API/database 12-month lifecycle have been
verified locally. Live authentication, PostgREST integration, native concurrent
clients and a deployed browser rehearsal remain separate acceptance checks.
See IMPLEMENTATION_REPORT.md for current evidence and readiness.

No divorce, children, separate household accounts or other future mechanics are
introduced by this implementation.
