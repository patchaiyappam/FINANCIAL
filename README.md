# 💰 Money Master — Financial Simulation Game

A full-stack, backend-driven financial simulation where users allocate ₹1,00,000/month, invest across assets, face random life events, and compete on a live leaderboard over 12 months.

---

## 🏗️ Architecture

```
financial event/
├── backend/
│   ├── app.py                    ← Flask entry point (imports from routes/)
│   ├── supabase_client.py        ← Supabase connection
│   ├── requirements.txt
│   ├── .env                      ← SUPABASE_URL + SUPABASE_SERVICE_KEY
│   ├── engine/
│   │   ├── event_engine.py       ← Dynamic probabilistic event generation
│   │   ├── market_engine.py      ← Stock/gold growth, inflation, risk scoring
│   │   └── monthly_processor.py  ← Core game loop orchestrator
│   ├── models/
│   │   └── constants.py          ← All game parameters (single source of truth)
│   ├── routes/
│   │   ├── player_routes.py      ← Player API endpoints
│   │   └── admin_routes.py       ← Admin API endpoints (uses engine)
│   └── services/
│       ├── auth_service.py       ← Supabase token validation
│       └── game_service.py       ← DB helpers, leaderboard, rate limiting
│
├── frontend/
│   ├── index.html                ← Login (Google OAuth)
│   ├── case-study.html           ← Scenario briefing
│   ├── allocation.html           ← Month 1 budget allocation
│   ├── dashboard.html            ← Main game dashboard
│   ├── leaderboard.html          ← Live/final rankings
│   ├── admin.html                ← Admin control panel
│   ├── css/style.css             ← Premium design system
│   └── js/
│       ├── config.js             ← Supabase client + API_BASE_URL
│       ├── auth.js               ← Google OAuth login
│       ├── case-study.js
│       ├── allocation.js
│       ├── dashboard.js          ← Main game logic (calls /sell, /buy-choice, /handle-relative)
│       └── admin.js
│
├── supabase.sql                  ← Full schema (fresh install)
└── supabase_migration.sql        ← Migration (adds trust_score, risk_level, new RPC)
```

---

## 🎮 Game Flow

```
Login → Case Study → Month 1 Allocation → Dashboard ← → Admin: Next Month → ... → Leaderboard
```

### Month Sequence (Backend Engine):
1. **Income**: +₹1,00,000 salary added
2. **Expenses**: Lifestyle costs deducted (with inflation from month 4)
3. **Sales Credits**: Pending asset sales credited
4. **Investment Growth**: Stocks ±volatility, Gold stable ±, Emergency Fund +2%
5. **Dynamic Events**: Context-aware probabilistic events (emergency, opportunity, social, market)
6. **Bike EMI**: -₹5,000 if applicable
7. **Loan EMIs + Interest**: Repayments calculated
8. **Safety Net**: Emergency fund covers deficit, else auto-loan
9. **Final State**: Net worth, risk score, trust score calculated

---

## 🔌 API Endpoints

### Player Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/game-status` | Current game state |
| GET | `/case-study` | Scenario briefing data |
| POST | `/allocate` | Month 1 budget submission (backend-validated) |
| GET | `/dashboard` | Full player state + choices + event logs |
| POST | `/lock-turn` | Player confirms end of actions |
| POST | `/sell` | Sell stocks/gold/emergency_fund (10% penalty) |
| POST | `/buy-choice` | Purchase optional admin-created choice |
| POST | `/handle-relative` | Donate to relative (trust system) |
| GET | `/leaderboard` | Rankings by net worth |
| GET | `/event-history` | Full event log for player |

### Admin Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/start-game` | Reset all data, start fresh |
| POST | `/next-month` | Process month for ALL players via engine |
| POST | `/end-game` | Manually end the game |
| POST | `/event` | Add global event for a specific month |
| DELETE | `/event/<id>` | Remove a global event |
| POST | `/choice-admin` | Add optional choice for players |

---

## 🎲 Event Engine

Events are **never fixed or predictable**. Each player gets unique events based on:
- **Emergency Fund level** → low EF = higher emergency probability
- **Stock ratio** → aggressive investors face more market volatility
- **Loan burden** → increases emergency probability
- **Trust score** → high trust unlocks windfalls; low trust triggers penalties
- **Month number** → late-game events differ from early game
- **Cash level** → liquid cash attracts investment opportunities

Event categories:
- 🚨 **Financial Emergency** (phone repair, hospital, theft...)
- 📈 **Investment Opportunity** (stock tip, freelance gig, bonus...)
- 📊 **Market Fluctuation** (±stock %, ±gold %)
- 🤝 **Social Responsibility** (charity, wedding, festival...)
- 💸 **Expense Spike** (rent hike, fuel, grocery inflation...)
- 🎁 **Windfall** (tax refund, lucky draw, inheritance...)
- ⚠️ **Trust Penalty** (mid-late game if trust < 2)

---

## 🗄️ Database Setup

### Fresh Install
Run `supabase.sql` in Supabase SQL Editor.

### Existing Database Migration
Run `supabase_migration.sql` to:
- Add `trust_score` column to `player_state`
- Add `risk_level` column to `player_state`
- Replace the `process_month_atomically` RPC with the updated version

---

## 🚀 Running Locally

```bash
cd backend
pip install -r requirements.txt
python app.py         # Starts on http://localhost:5000
```

For the frontend, open `frontend/index.html` directly in a browser, OR use a local HTTP server:
```bash
cd frontend
python -m http.server 8080
# Visit http://localhost:8080
```

**Important**: Set `API_BASE_URL` in `frontend/js/config.js`:
- Local: `"http://localhost:5000"`
- Production: `"https://financial-pecc.onrender.com"`

---

## 🌐 Deployment (Render)

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app`
- **Environment Variables**: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
