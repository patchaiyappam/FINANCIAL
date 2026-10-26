// ============================================================================
// DASHBOARD — Main game interface with correct API endpoints
// ============================================================================

let currentUser = null;
let currentMonth = 1;
let currentCourtship = null;
let latestPlayerSnapshot = null;
let latestMonthlyExpense = 88000;
let latestInvestmentSummary = {};

// ── Auth Helper ──
async function getAuthHeaders() {
    const { data: { session } } = await window.supabase.auth.getSession();
    if (!session) {
        window.location.href = '/';
        return {};
    }
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${session.access_token}`
    };
}

// ── Toast Notification ──
function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        container.id = 'toastContainer';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-glass toast-${type}`;
    const icons = {
        error: 'fa-circle-xmark',
        success: 'fa-circle-check',
        info: 'fa-circle-info'
    };
    toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}"></i><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Format Currency (Indian) ──
function formatINR(val) {
    return `₹${Math.floor(val).toLocaleString('en-IN')}`;
}

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
    const waitForSession = async () => {
        let retries = 5;
        while (retries--) {
            const { data: { session } } = await window.supabase.auth.getSession();
            if (session) return session;
            await new Promise(res => setTimeout(res, 500));
        }
        alert("Please login first.");
        window.location.href = '/';
        return null;
    };

    const session = await waitForSession();
    if (!session) return;

    currentUser = session.user;

    window.supabase.auth.onAuthStateChange((event, session) => {
        if (!session) window.location.href = '/';
        else currentUser = session.user;
    });

    document.getElementById('userName').innerText =
        currentUser.user_metadata?.name || currentUser.email;

    document.getElementById('logoutBtn').addEventListener('click', async () => {
        await window.supabase.auth.signOut();
        window.location.href = '/';
    });

    const staySingleBtn = document.getElementById('staySingleBtn');
    if (staySingleBtn) {
        staySingleBtn.addEventListener('click', async () => {
            if (!confirm("Choose to stay single? This choice is final for this game.")) return;
            try {
                const h = await getAuthHeaders();
                const res = await fetch(`${API_BASE_URL}/courtship/marry`, {
                    method: 'POST',
                    headers: h,
                    body: JSON.stringify({ choice: 'single' })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message, 'success');
                    await loadDashboard();
                } else {
                    showToast(data.error, 'error');
                }
            } catch (err) {
                showToast('Failed to stay single', 'error');
            }
        });
    }

    document.getElementById('endTurnBtn').addEventListener('click', async () => {
        if (!confirm("Lock your turn for this month? You won't be able to make more decisions until the admin advances.")) return;

        try {
            const h = await getAuthHeaders();
            const res = await fetch(`${API_BASE_URL}/lock-turn`, {
                method: 'POST',
                headers: h
            });
            const data = await res.json();
            if (res.ok) showToast(data.message, 'success');
            else showToast(data.error, 'error');
            await loadDashboard();
        } catch (err) {
            console.error(err);
            showToast('Failed to lock turn', 'error');
        }
    });

    await loadDashboard();
    // The dashboard polls every 5s. Without this guard the poll re-rendered the
    // allocation and loan inputs mid-keystroke and wiped whatever the player had
    // typed — the single most infuriating bug in the old UI.
    setInterval(() => {
        if (isEditing()) return;
        loadDashboard();
    }, 5000);
});

// ══════════════════════════════════════════════
// LOAD DASHBOARD DATA
// ══════════════════════════════════════════════
async function loadDashboard() {
    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/dashboard`, { headers: h });

        if (res.status === 404) {
            window.location.href = 'allocation.html';
            return;
        }

        const data = await res.json();
        if (data.error) {
            if (data.error.includes('No player state')) {
                window.location.href = 'allocation.html';
            }
            return;
        }

        const p = data.player;
        latestPlayerSnapshot = p;
        latestMonthlyExpense = Number(data.expenses?.current) || 88000;
        latestInvestmentSummary = data.investment_summary || {};
        const g = data.game;

        // Game ended → celebrate, then leaderboard
        if (g && g.game_status === 'ended') {
            if (window.fx && !sessionStorage.getItem('mm_finale')) {
                sessionStorage.setItem('mm_finale', '1');
                fx.confetti(120);
                setTimeout(() => { window.location.href = 'leaderboard.html'; }, 2200);
            } else {
                window.location.href = 'leaderboard.html';
            }
            return;
        }

        // ── Update UI ──
        document.getElementById('monthBadge').innerText = `Month ${p.month}`;
        currentMonth = p.month;

        // Net Worth — animated counter with green/red flash and delta chip
        const nwEl = document.getElementById('netWorthVal');
        if (window.fx) fx.animateValue('netWorthVal', p.net_worth);
        else nwEl.innerText = formatINR(p.net_worth);
        if (p.net_worth < 0) nwEl.classList.add('negative');
        else nwEl.classList.remove('negative');

        // Stats — animated
        if (window.fx) {
            fx.animateValue('cashVal', p.cash);
            fx.animateValue('stocksVal', p.stocks);
            fx.animateValue('goldVal', p.gold);
            fx.animateValue('emergencyVal', p.emergency_fund);
            fx.animateValue('loanVal', p.loans);
        } else {
            document.getElementById('cashVal').innerText = formatINR(p.cash);
            document.getElementById('stocksVal').innerText = formatINR(p.stocks);
            document.getElementById('goldVal').innerText = formatINR(p.gold);
            document.getElementById('emergencyVal').innerText = formatINR(p.emergency_fund);
            document.getElementById('loanVal').innerText = formatINR(p.loans);
        }
        document.getElementById('pendingVal').innerText = formatINR(p.pending_cash_next_month || 0);
        renderInvestmentPortfolio(p.investment_portfolio || {}, Number(p.month) || 1, latestInvestmentSummary);
        document.getElementById('lifestyleVal').innerText = p.lifestyle_type === 'city' ? 'City' : 'Outer';
        const expenseSummary = document.getElementById('expenseSummary');
        if (expenseSummary && data.expenses) {
            const e = data.expenses;
            expenseSummary.textContent = `Base living: ${formatINR(e.base)} / month | Current household: ${formatINR(e.current)} / month`;
        }
        document.getElementById('bikeVal').innerText = p.bike_status
            ? (p.bike_lock_in_months > 0 ? `Locked (${p.bike_lock_in_months}m)` : 'Free')
            : 'None';
        
        const relVal = document.getElementById('relationshipVal');
        if (relVal) {
            if (p.spouse_archetype) {
                if (p.spouse_archetype === 'single') {
                    relVal.innerText = 'Single';
                } else {
                    const names = {
                        saver: 'Saver',
                        earner: 'Earner',
                        investor: 'Investor',
                        anchor: 'Anchor'
                    };
                    relVal.innerText = names[p.spouse_archetype] || p.spouse_archetype;
                }
            } else {
                relVal.innerText = 'Unmarried';
            }
        }

        // Risk & Trust
        const riskLevel = p.risk_level || 50;
        const riskLabel = riskLevel > 70 ? 'High' : riskLevel > 40 ? 'Medium' : 'Low';
        const riskColor = riskLevel > 70 ? 'var(--accent-rose)' : riskLevel > 40 ? 'var(--accent-amber)' : 'var(--accent-emerald)';
        document.getElementById('riskVal').innerHTML = `<span style="color:${riskColor}">${riskLabel} (${riskLevel})</span>`;
        document.getElementById('trustVal').innerText = p.trust_score || 0;

        // ── V2 renders: market news, monthly allocation, loans ──
        renderMarketNews(data.market, p.month);
        renderAllocation(data.allocation, data.loan_info);
        renderLoans(data.loan_info);
        renderActionBanner(data.allocation, p, data.courtship, data.negotiation);
        renderInsurance(data.insurance);
        updateTabBadges(data.allocation);
        if (window.renderNegotiation) renderNegotiation(data.negotiation);
        if (window.mascotUpdate) mascotUpdate(data);

        // ── Courtship & Marriage UI Render ──
        const courtshipSec = document.getElementById('courtshipSection');
        const courtship = data.courtship;
        currentCourtship = courtship;
        if (courtshipSec && courtship) {
            renderFamilyOffers(courtshipSec, courtship, p, g);
        }

        // ── Optional Choices ──
        // Opportunities (optional_choices) were REMOVED from the player view on
        // 2026-07-24 at the organizer's request. Backend routes and DB rows remain
        // dormant; re-enabling is a UI change only.
        // ── Event Logs ──
        const logContainer = document.getElementById('eventLogContainer');
        if (data.event_logs && data.event_logs.length > 0) {
            logContainer.innerHTML = data.event_logs.reverse().map(log => {
                const entries = (log.summary || '').split(' | ');
                const monthLabel = `<div style="font-weight:700; color:var(--accent-primary); margin-bottom:0.5rem; font-size:0.85rem;">Month ${log.month}</div>`;
                const items = entries.map(entry => {
                    let cls = 'info';
                    if (entry.includes('⚠') || entry.includes('CRITICAL') || entry.includes('📉')) cls = 'negative';
                    else if (entry.includes('💰') || entry.includes('📈') || entry.includes('✅') || entry.includes('SUCCESS')) cls = 'positive';
                    else if (entry.includes('⚡') || entry.includes('!')) cls = 'warning';
                    return `<div class="event-log-item ${cls}">${entry}</div>`;
                }).join('');
                return monthLabel + items;
            }).join('<hr style="border-color: rgba(59,130,246,0.10); margin: 1rem 0;">');
        }

        // ── Trust Scores from Supabase ──
        // Trust / relative scores were removed with the Social Investment panel.
        // The trustPoor / trustRich elements no longer exist, so this fetch-and-write
        // has been deleted rather than left to throw on every dashboard poll.


        // ── UI Lock State ──
        const actionButtons = document.querySelectorAll('.sell-btn, #relativeContainer button');
        const endTurnBtn = document.getElementById('endTurnBtn');
        const statusBanner = document.getElementById('statusBanner');

        if (p.status === 'waiting') {
            actionButtons.forEach(btn => btn.disabled = true);
            endTurnBtn.style.display = 'none';
            statusBanner.style.display = 'flex';
        } else {
            actionButtons.forEach(btn => btn.disabled = false);
            endTurnBtn.style.display = 'inline-block';
            statusBanner.style.display = 'none';
        }

    } catch (err) {
        console.error('Dashboard load error:', err);
    }
}

// ══════════════════════════════════════════════
// PLAYER ACTIONS — Using correct API endpoints
// ══════════════════════════════════════════════

// ── Sell Asset → POST /sell ──
window.sellAsset = async function(asset) {
    const amountStr = prompt(`How much ${asset} do you want to sell?\n(10% penalty applies, cash credited next month)`);
    if (!amountStr) return;

    const amount = parseInt(amountStr);
    if (isNaN(amount) || amount <= 0) {
        showToast('Enter a valid positive amount', 'error');
        return;
    }

    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/sell`, {
            method: 'POST',
            headers: h,
            body: JSON.stringify({ asset, amount })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
        } else {
            showToast(data.error, 'error');
        }
        await loadDashboard();
    } catch (err) {
        showToast('Failed to sell asset', 'error');
    }
};

// ── Handle Relative → POST /handle-relative ──
window.handleRelative = async function(relative_type, action) {
    if (action === 'none') {
        try {
            const h = await getAuthHeaders();
            const res = await fetch(`${API_BASE_URL}/handle-relative`, {
                method: 'POST',
                headers: h,
                body: JSON.stringify({ relative_type, action: 'none' })
            });
            const data = await res.json();
            showToast(data.message, 'info');
        } catch (err) {
            showToast('Action failed', 'error');
        }
        return;
    }

    const cost = action === 'medium' ? '₹2,000' : '₹5,000';
    if (!confirm(`Help ${relative_type} relative for ${cost}?`)) return;

    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/handle-relative`, {
            method: 'POST',
            headers: h,
            body: JSON.stringify({ relative_type, action })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
        } else {
            showToast(data.error, 'error');
        }
        await loadDashboard();
    } catch (err) {
        showToast('Action failed', 'error');
    }
};

// ── Buy Optional Choice → POST /buy-choice ──
// buyOptionalChoice removed with the opportunities panel (2026-07-24).


// ── Reveal Trait → POST /courtship/reveal ──
window.revealTrait = async function(archetype_id, trait_key) {
    const datesUsed = parseInt(document.getElementById('datesUsedVal').innerText || '0');
    if (datesUsed >= 3) {
        if (!confirm("You have used all 3 free dates. Going on an extra date to reveal this trait costs ₹5,000. Proceed?")) return;
    }
    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/courtship/reveal`, {
            method: 'POST',
            headers: h,
            body: JSON.stringify({ archetype_id, trait_key })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            await loadDashboard();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Failed to reveal candidate trait', 'error');
    }
};

// ── Propose Marriage → POST /courtship/marry ──
window.proposeMarriage = async function(archetype_id) {
    if (!currentCourtship || !Number.isFinite(currentCourtship.wedding_cost)) return;
    if (!confirm(`Marry this spouse? Pay ${formatINR(currentCourtship.wedding_cost)} now. Spouse income and expenses start in Month ${currentCourtship.marriage_month + 1}. Existing assets and debts join now. This choice is final for this game.`)) return;
    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/courtship/marry`, {
            method: 'POST',
            headers: h,
            body: JSON.stringify({ choice: archetype_id })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, 'success');
            await loadDashboard();
        } else {
            showToast(data.error, 'error');
        }
    } catch (err) {
        showToast('Failed to propose marriage', 'error');
    }
};

// ── Format Revealed Trait ──
function _formatRevealedTrait(archetype_id, trait_key) {
    return currentCourtship?.reveals.find(r => r.archetype_id === archetype_id && r.trait_key === trait_key)?.revealed_value || '?';
}


// ============================================================================
// V2 UI — market news, monthly allocation, loans
// ============================================================================

// 'allocKeep' is gone: the server now derives kept cash as the residual, so there
// is nothing for the player to balance and nothing to get wrong.
const ALLOC_IDS = ['allocStocks', 'allocGold', 'allocEf', 'allocPrepay',
    'allocBankFd', 'allocTreasuryBill', 'allocLiquidFund', 'allocIndexFund',
    'allocFlexiCap', 'allocBalancedAdvantage', 'allocPpf', 'allocNps',
    'allocArbitrageFund', 'allocGoldEtf', 'allocBusinessVenture'];

// The exact server-side value, held as a NUMBER. Never re-read from the rendered
// string: formatINR uses Math.floor while the backend rounds, so 8117.51 displayed
// as "8,117" and re-parsed as 8117 was 0.51 away from the server's 8118 and failed
// the "allocate exactly" check with no way for the player to satisfy it.
let allocAvailableRaw = 0;
let _lastSeenMonth = null;
const LOAN_IDS = ['loanAmount', 'loanTerm'];

// True while the player has focus in any input they are mid-way through filling.
// Used to suspend the 5s dashboard poll so a re-render cannot destroy their entry.
function isEditing() {
    const el = document.activeElement;
    if (!el) return false;
    return ALLOC_IDS.includes(el.id) || LOAN_IDS.includes(el.id);
}

function pctText(v) {
    const pct = (v * 100).toFixed(1);
    return `${v >= 0 ? '+' : ''}${pct}%`;
}

function pctColor(v) {
    if (v > 0.0005) return 'var(--accent-emerald)';
    if (v < -0.0005) return 'var(--accent-rose)';
    return 'var(--text-secondary)';
}

// ── INVESTMENT PORTFOLIO ─────────────────────────────────────────────────────
const INVESTMENT_LABELS = {
    bank_fd_3m: 'Bank Fixed Deposit · 3 months',
    treasury_bill_6m: 'Treasury Bill · 6 months',
    liquid_fund: 'Liquid Mutual Fund',
    arbitrage_fund: 'Arbitrage Mutual Fund',
    gold_etf: 'Gold ETF',
    business_venture: 'Small Business / Resale Venture',
    index_fund: 'Nifty 50 Index Fund',
    flexi_cap_fund: 'Flexi-cap Equity Fund',
    balanced_advantage_fund: 'Balanced Advantage Fund',
    ppf: 'Public Provident Fund (PPF)',
    nps: 'National Pension System (NPS)'
};
const INVESTMENT_LOCKED = new Set(['ppf', 'nps']);

function renderInvestmentPortfolio(portfolio, month, summary = {}) {
    const valueEl = document.getElementById('investmentPortfolioVal');
    const listEl = document.getElementById('investmentPortfolioList');
    if (!valueEl || !listEl) return;
    let total = 0;
    const positions = [];
    for (const [key, lots] of Object.entries(portfolio || {})) {
        if (!Array.isArray(lots) || !INVESTMENT_LABELS[key]) continue;
        const value = lots.reduce((sum, lot) => sum + Math.max(0, Number(lot.value) || 0), 0);
        if (value <= 0.01) continue;
        total += value;
        const locked = INVESTMENT_LOCKED.has(key) || lots.some(lot => lot.maturity_month && Number(lot.maturity_month) > month);
        positions.push({ key, value, locked, lots });
    }
    valueEl.innerText = formatINR(total);
    const summaryEl = document.getElementById('investmentPortfolioSummary');
    if (summaryEl) {
        const pnl = Number(summary.profit_loss) || 0;
        const maturity = summary.next_maturity_month ? `Next maturity: Month ${summary.next_maturity_month}` : 'No term maturity during this game';
        summaryEl.textContent = `${pnl >= 0 ? 'Gain' : 'Loss'} vs principal: ${formatINR(Math.abs(pnl))} · Estimated current-month product fees: ${formatINR(summary.estimated_monthly_fees || 0)} · ${maturity}`;
    }
    if (!positions.length) {
        listEl.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;">No additional investment products yet. Stocks, gold and the emergency fund remain above.</div>';
        return;
    }
    listEl.innerHTML = positions.map(pos => {
        const principal = pos.lots.reduce((sum, lot) => sum + (Number(lot.principal) || 0), 0);
        const delta = pos.value - principal;
        const tone = delta >= 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';
        const maturities = pos.lots.map(lot => Number(lot.maturity_month)).filter(m => m > month).sort((a, b) => a - b);
        const monthlyFee = Number(summary.products?.[pos.key]?.monthly_fee) || 0;
        const lockText = INVESTMENT_LOCKED.has(pos.key) ? 'Locked beyond this game' :
            (maturities.length ? `Term locked until Month ${maturities[0]}` : 'Available to sell');
        const sellButton = INVESTMENT_LOCKED.has(pos.key) ?
            '<span style="font-size:0.72rem;color:var(--text-muted);">LOCKED</span>' :
            `<button class="sell-btn" onclick="sellInvestment('${pos.key}', ${pos.value.toFixed(2)})">Sell</button>`;
        return `<div style="display:flex;justify-content:space-between;align-items:center;gap:0.75rem;flex-wrap:wrap;padding:0.75rem;border:1px solid var(--border-subtle);border-radius:0.65rem;">
            <div style="min-width:180px;flex:1;">
                <div style="font-size:0.88rem;font-weight:650;">${INVESTMENT_LABELS[pos.key]}</div>
                <div style="font-size:0.72rem;color:var(--text-muted);">${lockText} · principal ${formatINR(principal)} · current monthly fee ${formatINR(value * monthlyFee)}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:0.95rem;font-weight:750;">${formatINR(pos.value)}</div>
                <div style="font-size:0.72rem;color:${tone};">${delta >= 0 ? '+' : ''}${formatINR(delta)} simulated gain/loss</div>
            </div>
            <div>${sellButton}</div>
        </div>`;
    }).join('');
}

window.sellInvestment = async function(product, maxValue) {
    const amountText = prompt(`How much of ${INVESTMENT_LABELS[product]} do you want to sell?
Available: ${formatINR(maxValue)}. Early-exit penalties may apply.`);
    if (!amountText) return;
    const amount = Number(amountText);
    if (!Number.isFinite(amount) || amount <= 0 || amount > maxValue + 0.01) {
        showToast('Enter a valid amount within the available balance.', 'error');
        return;
    }
    try {
        const headers = await getAuthHeaders();
        const quoteRes = await fetch(`${API_BASE_URL}/investment-sale-quote`, {
            method: 'POST', headers, body: JSON.stringify({ product, amount })
        });
        const quote = await quoteRes.json();
        if (!quoteRes.ok) {
            showToast(quote.error || 'Could not prepare this sale.', 'error');
            return;
        }
        const detail = `${quote.product_name}\nGross sale: ${formatINR(quote.gross_sold)}\nExit fee: ${formatINR(quote.penalty)}\nCash received now: ${formatINR(quote.cash_proceeds)}\n\nProceed with this sale?`;
        if (!confirm(detail)) return;
        const retryKey = `mm_sale_${product}_${amount.toFixed(2)}`;
        let requestId = sessionStorage.getItem(retryKey);
        if (!requestId) {
            requestId = window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}_${Math.random().toString(36).slice(2)}`;
            sessionStorage.setItem(retryKey, requestId);
        }
        const res = await fetch(`${API_BASE_URL}/sell-investment`, {
            method: 'POST', headers,
            body: JSON.stringify({ product, amount, request_id: requestId })
        });
        const data = await res.json();
        if (res.ok) {
            sessionStorage.removeItem(retryKey);
            showToast(data.message, 'success');
        }
        else showToast(data.error || 'Investment sale failed', 'error');
        await loadDashboard();
    } catch (err) {
        showToast('Failed to sell investment.', 'error');
    }
};

// ── LONG-TERM COMPOUNDING SCENARIOS ──────────────────────────────────────────
const PROJECTION_RATES = {
    index_fund: { annual: 0.10, label: '10% hypothetical annual return' },
    flexi_cap_fund: { annual: 0.12, label: '12% hypothetical annual return' },
    balanced_advantage_fund: { annual: 0.08, label: '8% hypothetical annual return' },
    bank_fd_3m: { annual: 0.064, label: '6.4% fixed game assumption' },
    treasury_bill_6m: { annual: 0.063, label: '6.3% fixed game assumption' },
    liquid_fund: { annual: 0.054, label: '5.4% hypothetical annual return' },
    arbitrage_fund: { annual: 0.057, label: '5.7% illustrative game assumption; not guaranteed' },
    gold_etf: { annual: 0.07, label: '7% hypothetical annual return; gold prices can fall' },
    ppf: { annual: 0.071, label: '7.1% game assumption; actual PPF rates can change' },
    nps: { annual: 0.09, label: '9% hypothetical market-linked return' },
    gold: { annual: 0.07, label: '7% hypothetical annual return' }
};

function updateLongTermProjection() {
    const monthlyInput = document.getElementById('projectionMonthly');
    const productInput = document.getElementById('projectionProduct');
    const yearsInput = document.getElementById('projectionYears');
    if (!monthlyInput || !productInput || !yearsInput) return;
    const monthly = Math.max(0, Number(monthlyInput.value) || 0);
    const years = Math.max(1, Number(yearsInput.value) || 1);
    const months = years * 12;
    const rate = PROJECTION_RATES[productInput.value] || PROJECTION_RATES.index_fund;
    const monthlyRate = Math.pow(1 + rate.annual, 1 / 12) - 1;
    const factor = monthlyRate === 0 ? months : (Math.pow(1 + monthlyRate, months) - 1) / monthlyRate;
    const invested = monthly * months;
    const future = monthly * factor;
    document.getElementById('projectionFutureValue').innerText = formatINR(future);
    document.getElementById('projectionInvested').innerText = formatINR(invested);
    document.getElementById('projectionGain').innerText = formatINR(future - invested);
    document.getElementById('projectionAssumption').innerText =
        `${rate.label}. End-of-month contributions; monthly compounding. Projection excludes taxes, actual product fees and inflation. It is an educational scenario, not a return forecast or promise.`;
}

document.addEventListener('DOMContentLoaded', () => {
    ['projectionMonthly', 'projectionProduct', 'projectionYears'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', updateLongTermProjection);
        if (el) el.addEventListener('change', updateLongTermProjection);
    });
    updateLongTermProjection();
});

// ── MARKET NEWS ──────────────────────────────────────────────────────────────
function renderMarketNews(market, month) {
    const sec = document.getElementById('marketNews');
    if (!sec) return;
    if (!market || market.source === 'flat') {
        sec.style.display = 'none';
        return;
    }
    sec.style.display = 'block';
    document.getElementById('marketName').innerText = market.name || 'Market Update';
    document.getElementById('marketMonth').innerText = `Month ${month}`;
    document.getElementById('marketReason').innerText = market.reason || '';

    // Fire dramatic feedback ONLY when the month actually advances, so the 5s
    // poll doesn't re-trigger the animation every tick.
    if (window.fx && _lastSeenMonth !== null && month !== _lastSeenMonth) {
        fx.revealEvent('marketNews');
        if (market.stock_pct <= -0.10) fx.shake('marketNews');       // crash / war
        else if (market.stock_pct >= 0.08) fx.celebrate('marketNews'); // strong bull
    }
    _lastSeenMonth = month;

    const sEl = document.getElementById('marketStockPct');
    const gEl = document.getElementById('marketGoldPct');
    sEl.innerText = pctText(market.stock_pct);
    sEl.style.color = pctColor(market.stock_pct);
    gEl.innerText = pctText(market.gold_pct);
    gEl.style.color = pctColor(market.gold_pct);
}

// ── ACTION BANNER ────────────────────────────────────────────────────────────
function renderActionBanner(alloc, player, courtship, negotiation) {
    const banner = document.getElementById('actionBanner');
    if (!banner) return;
    const marriagePending = courtship && player.month === courtship.marriage_month && !player.spouse_archetype;
    const functionPending = negotiation && negotiation.active;
    if (marriagePending || functionPending) {
        banner.style.display = 'block';
        document.getElementById('actionBannerTitle').innerText = marriagePending ? 'Your family wants to discuss marriage' : 'Your spouse has planned a big family function';
        document.getElementById('actionBannerText').innerText = marriagePending
            ? 'Month ' + player.month + ' is on hold. Compare the spouse profiles and choose a partner or stay single before continuing.'
            : 'Discuss the proposed budget and confirm your decision before completing this month.';
        document.getElementById('actionBannerBtn').innerText = marriagePending ? 'Meet the candidates' : 'Discuss the budget';
        document.getElementById('actionBannerBtn').onclick = () => {
            switchTab('home');
            document.getElementById(marriagePending ? 'courtshipSection' : 'negotiationSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
        };
        return;
    }
    document.getElementById('actionBannerBtn').innerText = 'Allocate cash';
    if (alloc && alloc.required && !alloc.done) {
        banner.style.display = 'block';
        document.getElementById('actionBannerTitle').innerText = 'Allocation required';
        document.getElementById('actionBannerText').innerText =
            `You have ${formatINR(alloc.available_cash)} sitting idle. Decide where it goes before ending Month ${player.month}.`;
        document.getElementById('actionBannerBtn').onclick = () => {
            switchTab('invest');
            document.getElementById('allocSection').scrollIntoView({ behavior: 'smooth', block: 'center' });
        };
    } else {
        banner.style.display = 'none';
    }
}

// ── MONTHLY ALLOCATION ───────────────────────────────────────────────────────
function renderAllocation(alloc, loanInfo) {
    const sec = document.getElementById('allocSection');
    if (!sec || !alloc) return;

    if (!alloc.required || alloc.done) {
        sec.style.display = 'none';
        return;
    }
    sec.style.display = 'block';

    allocAvailableRaw = Number(alloc.available_cash) || 0;
    document.getElementById('allocAvailable').innerText = formatINR(allocAvailableRaw);

    // Cap the repay field at what is actually owed.
    const outstanding = (loanInfo && loanInfo.outstanding) || 0;
    const prepayWrap = document.getElementById('allocPrepayWrap');
    const prepayInput = document.getElementById('allocPrepay');
    if (outstanding <= 0) {
        prepayWrap.style.display = 'none';
        prepayInput.value = 0;
    } else {
        prepayWrap.style.display = 'block';
        prepayInput.max = outstanding;
        document.getElementById('allocPrepayMax').innerText = `(owed ${formatINR(outstanding)})`;
    }

    recalcAllocation();
}

function allocTotal() {
    return ALLOC_IDS.reduce((sum, id) => {
        const el = document.getElementById(id);
        return sum + (el ? (parseFloat(el.value) || 0) : 0);
    }, 0);
}

function recalcAllocation() {
    const msg = document.getElementById('allocRemaining');
    const btn = document.getElementById('allocSubmit');
    if (!msg || !btn) return;

    const invested = allocTotal();
    const remainder = allocAvailableRaw - invested;

    // Only ONE way to fail now: trying to invest more than you have.
    if (remainder < -1) {
        msg.innerHTML = `<span style="color: var(--accent-rose);">Over by ${formatINR(Math.abs(remainder))}</span>`;
        btn.disabled = true;
    } else {
        msg.innerHTML = `<span style="color: var(--text-muted);">Remaining stays as cash: <strong style="color: var(--accent-emerald);">${formatINR(Math.max(0, remainder))}</strong></span>`;
        btn.disabled = false;
    }
    updateInvestmentTensionPreview();
}

// A deliberate strategy dilemma: the game rewards more than headline growth.
// These previews are advisory estimates, not extra scoring rules or predictions.
const PRODUCT_RISK_WEIGHTS = {
    bank_fd_3m: 0.03, treasury_bill_6m: 0.02, liquid_fund: 0.06,
    arbitrage_fund: 0.10, gold_etf: 0.25, index_fund: 1.0,
    flexi_cap_fund: 1.0, balanced_advantage_fund: 0.55,
    ppf: 0.02, nps: 0.58, business_venture: 0.85
};
const PRODUCT_LOCK_KEYS = new Set(['bank_fd_3m', 'treasury_bill_6m', 'ppf', 'nps', 'business_venture']);
const PRODUCT_KEYS = Object.keys(PRODUCT_RISK_WEIGHTS);
function sumLots(lots) {
    return Array.isArray(lots) ? lots.reduce((sum, lot) => sum + Math.max(0, Number(lot?.value) || 0), 0) : 0;
}
function currentPortfolioValue(portfolio) {
    return Object.values(portfolio || {}).reduce((sum, lots) => sum + sumLots(lots), 0);
}
function updateInvestmentTensionPreview() {
    const riskEl = document.getElementById('allocRiskExposure');
    const lockedEl = document.getElementById('allocLockedCapital');
    const cushionEl = document.getElementById('allocAccessibleCushion');
    const messageEl = document.getElementById('allocTensionMessage');
    if (!riskEl || !lockedEl || !cushionEl || !messageEl) return;

    const p = latestPlayerSnapshot || {};
    const portfolio = p.investment_portfolio || {};
    const month = Number(p.month) || 1;
    const proposed = Object.fromEntries(PRODUCT_KEYS.map(key => {
        const idByKey = {
            bank_fd_3m: 'allocBankFd', treasury_bill_6m: 'allocTreasuryBill', liquid_fund: 'allocLiquidFund',
            arbitrage_fund: 'allocArbitrageFund', gold_etf: 'allocGoldEtf', index_fund: 'allocIndexFund',
            flexi_cap_fund: 'allocFlexiCap', balanced_advantage_fund: 'allocBalancedAdvantage',
            ppf: 'allocPpf', nps: 'allocNps', business_venture: 'allocBusinessVenture'
        };
        return [key, Math.max(0, Number(document.getElementById(idByKey[key])?.value) || 0)];
    }));

    const riskExposure = Math.max(0, Number(p.stocks) || 0) + Math.max(0, Number(document.getElementById('allocStocks')?.value) || 0)
        + PRODUCT_KEYS.reduce((sum, key) => sum + sumLots(portfolio[key]) * PRODUCT_RISK_WEIGHTS[key]
            + proposed[key] * PRODUCT_RISK_WEIGHTS[key], 0);
    const assets = Math.max(1, Math.max(0, Number(p.cash) || allocAvailableRaw)
        + Math.max(0, Number(p.stocks) || 0) + Math.max(0, Number(p.gold) || 0)
        + Math.max(0, Number(p.emergency_fund) || 0) + currentPortfolioValue(portfolio));
    const riskPct = Math.min(1.5, riskExposure / assets) * 100;

    let locked = 0;
    for (const key of PRODUCT_KEYS) {
        const lots = Array.isArray(portfolio[key]) ? portfolio[key] : [];
        for (const lot of lots) {
            const termLocked = PRODUCT_LOCK_KEYS.has(key) &&
                (key === 'ppf' || key === 'nps' || (Number(lot.maturity_month) > month));
            if (termLocked) locked += Math.max(0, Number(lot.value) || 0);
        }
        if (PRODUCT_LOCK_KEYS.has(key)) locked += proposed[key];
    }

    const remainingCash = Math.max(0, allocAvailableRaw - allocTotal());
    const existingLiquid = sumLots(portfolio.liquid_fund) + 0.9975 * sumLots(portfolio.arbitrage_fund);
    const accessible = remainingCash + Math.max(0, Number(p.emergency_fund) || 0)
        + Math.max(0, Number(document.getElementById('allocEf')?.value) || 0)
        + existingLiquid + Math.max(0, proposed.liquid_fund) + 0.9975 * Math.max(0, proposed.arbitrage_fund);
    const expense = Math.max(1, latestMonthlyExpense || 88000);
    const cushionMonths = accessible / expense;
    const lockedPct = locked / assets * 100;

    riskEl.textContent = `${formatINR(riskExposure)} (${riskPct.toFixed(0)}%)`;
    lockedEl.textContent = `${formatINR(locked)} (${lockedPct.toFixed(0)}%)`;
    cushionEl.textContent = `${formatINR(accessible)} (${cushionMonths.toFixed(1)} months)`;

    const proposedValue = Object.values(proposed).reduce((sum, value) => sum + value, 0);
    const currentValue = currentPortfolioValue(portfolio);
    const pnl = Number(latestInvestmentSummary.profit_loss) || 0;
    const valueEl = document.getElementById('allocPortfolioValue');
    if (valueEl) valueEl.textContent = `${formatINR(currentValue + proposedValue)} · ${pnl >= 0 ? '+' : '−'}${formatINR(Math.abs(pnl))} vs principal`;
    const feeRates = Object.fromEntries(PRODUCT_KEYS.map(key => [key, Number(latestInvestmentSummary.products?.[key]?.monthly_fee) || 0]));
    const feeEstimate = PRODUCT_KEYS.reduce((sum, key) => sum + sumLots(portfolio[key]) * feeRates[key] + proposed[key] * feeRates[key], 0);
    const feeEl = document.getElementById('allocFeesEstimate');
    if (feeEl) feeEl.textContent = formatINR(feeEstimate);
    const nextDates = [];
    for (const key of PRODUCT_KEYS) {
        for (const lot of (Array.isArray(portfolio[key]) ? portfolio[key] : [])) {
            const maturity = Number(lot.maturity_month);
            if (maturity > month) nextDates.push(maturity);
        }
        const term = Number(latestInvestmentSummary.products?.[key]?.maturity_months);
        if (proposed[key] > 0 && key !== 'ppf' && key !== 'nps' && term > 0) nextDates.push(month + term);
    }
    const nextEl = document.getElementById('allocNextMaturity');
    if (nextEl) nextEl.textContent = nextDates.length ? `Month ${Math.min(...nextDates)}` : 'None in 12 months';

    const warnings = [];
    if (cushionMonths < 0.75) warnings.push(`Low liquidity: about ${formatINR(Math.max(0, expense - accessible))} short of one month of current household expenses. A surprise before term investments mature could trigger an expensive automatic loan.`);
    else if (cushionMonths < 1.5) warnings.push('Thin liquidity: you have less than 1.5 months of current household expenses in cash-like resources.');
    if (lockedPct > 30) warnings.push('High lock-in: a large share of assets is in term or retirement products. You may need to pay an exit cost—or be unable to withdraw—when cash is urgently needed.');
    if (riskPct > 45) warnings.push('High risk exposure: a market/business downturn may increase the net-worth upside/downside swing and weaken the risk-protection component of your score.');
    if (riskPct < 10) warnings.push('Low market exposure may protect stability, but may miss some upside in a strong market. The game does not guarantee that taking more risk will pay off.');
    if (!warnings.length) warnings.push('No allocation maximizes growth, liquidity and risk protection together. Your decision trades one advantage against another; the actual shared market result arrives after allocation.');
    messageEl.textContent = warnings.join(' ');
}

// ── LOANS ────────────────────────────────────────────────────────────────────
function renderLoans(info) {
    const sec = document.getElementById('loanSection');
    if (!sec || !info) return;
    sec.style.display = 'block';

    const list = document.getElementById('loanList');
    if (!info.active || info.active.length === 0) {
        list.innerHTML = '<div style="font-size:0.85rem; color: var(--text-muted);">No active loans.</div>';
    } else {
        list.innerHTML = info.active.map(l => {
            const isAuto = l.loan_type === 'auto';
            return `<div class="choice-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
                <div>
                    <div style="font-weight:600; font-size:0.9rem;">
                        ${isAuto ? '⚠️ Emergency Auto-Loan' : '🏦 Personal Loan'}
                        <span style="font-size:0.75rem; color:var(--text-muted); font-weight:400;">taken Month ${l.month_taken}</span>
                    </div>
                    <div style="font-size:0.75rem; color: var(--text-muted);">
                        ${(parseFloat(l.interest_rate) * 100).toFixed(1)}%/month · ${l.term_months || 6}-month term
                        ${isAuto ? ' · penalty rate' : ''}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-weight:700; color: var(--accent-rose);">${formatINR(l.current_amount)}</div>
                    <div style="font-size:0.75rem; color: var(--text-muted);">EMI ${formatINR(l.emi || 0)}</div>
                </div>
            </div>`;
        }).join('');
    }

    document.getElementById('loanSubtitle').innerText =
        `You can borrow up to ${formatINR(info.borrowing_headroom)} more at ` +
        `${(info.interest_rate * 100).toFixed(1)}%/month. Total EMI ${formatINR(info.monthly_emi)} of ${formatINR(info.emi_cap)} allowed.`;

    const form = document.getElementById('loanForm');
    const quote = document.getElementById('loanQuote');
    if (!info.can_borrow_this_month) {
        form.style.display = 'none';
        quote.innerText = 'You have already taken a loan this month.';
    } else if (info.borrowing_headroom <= 0) {
        form.style.display = 'none';
        quote.innerText = 'You have reached your debt ceiling. Repay before borrowing again.';
    } else {
        form.style.display = 'grid';
    }
}

async function refreshLoanQuote() {
    const amount = parseFloat(document.getElementById('loanAmount').value) || 0;
    const term = parseInt(document.getElementById('loanTerm').value, 10);
    const quote = document.getElementById('loanQuote');
    if (amount <= 0) { quote.innerText = ''; return; }
    try {
        const res = await fetch(`${API_BASE_URL}/loan/quote`, {
            method: 'POST',
            headers: await getAuthHeaders(),
            body: JSON.stringify({ amount, term_months: term })
        });
        const d = await res.json();
        if (!res.ok) { quote.innerText = d.error || ''; return; }
        quote.innerHTML = `EMI <strong>${formatINR(d.emi)}</strong>/month for ${d.term_months} months · ` +
            `total repayment <strong>${formatINR(d.total_repayment)}</strong> ` +
            `(interest ${formatINR(d.total_interest)})`;
    } catch (e) {
        quote.innerText = '';
    }
}

// ── Wiring ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    ALLOC_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', recalcAllocation);
    });

    const allocBtn = document.getElementById('allocSubmit');
    if (allocBtn) allocBtn.addEventListener('click', submitAllocation);

    LOAN_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', refreshLoanQuote);
        if (el) el.addEventListener('change', refreshLoanQuote);
    });

    const loanBtn = document.getElementById('loanSubmit');
    if (loanBtn) loanBtn.addEventListener('click', submitLoan);
});

async function submitAllocation() {
    const btn = document.getElementById('allocSubmit');
    btn.disabled = true;
    const payload = {
        stocks: parseFloat(document.getElementById('allocStocks').value) || 0,
        gold: parseFloat(document.getElementById('allocGold').value) || 0,
        emergency_fund: parseFloat(document.getElementById('allocEf').value) || 0,
        bank_fd_3m: parseFloat(document.getElementById('allocBankFd').value) || 0,
        treasury_bill_6m: parseFloat(document.getElementById('allocTreasuryBill').value) || 0,
        liquid_fund: parseFloat(document.getElementById('allocLiquidFund').value) || 0,
        arbitrage_fund: parseFloat(document.getElementById('allocArbitrageFund').value) || 0,
        gold_etf: parseFloat(document.getElementById('allocGoldEtf').value) || 0,
        business_venture: parseFloat(document.getElementById('allocBusinessVenture').value) || 0,
        index_fund: parseFloat(document.getElementById('allocIndexFund').value) || 0,
        flexi_cap_fund: parseFloat(document.getElementById('allocFlexiCap').value) || 0,
        balanced_advantage_fund: parseFloat(document.getElementById('allocBalancedAdvantage').value) || 0,
        ppf: parseFloat(document.getElementById('allocPpf').value) || 0,
        nps: parseFloat(document.getElementById('allocNps').value) || 0,
        loan_prepay: parseFloat(document.getElementById('allocPrepay').value) || 0
    };
    try {
        const res = await fetch(`${API_BASE_URL}/allocate-month`, {
            method: 'POST',
            headers: await getAuthHeaders(),
            body: JSON.stringify(payload)
        });
        const d = await res.json();
        if (res.ok) {
            showToast(d.message || 'Allocation confirmed', 'success');
            ALLOC_IDS.forEach(id => { document.getElementById(id).value = 0; });
            await loadDashboard();
        } else {
            showToast(d.error || 'Allocation failed', 'error');
            btn.disabled = false;
        }
    } catch (e) {
        showToast('Failed to connect to server', 'error');
        btn.disabled = false;
    }
}

async function submitLoan() {
    const btn = document.getElementById('loanSubmit');
    const amount = parseFloat(document.getElementById('loanAmount').value) || 0;
    const term = parseInt(document.getElementById('loanTerm').value, 10);
    btn.disabled = true;
    try {
        const res = await fetch(`${API_BASE_URL}/loan`, {
            method: 'POST',
            headers: await getAuthHeaders(),
            body: JSON.stringify({ amount, term_months: term })
        });
        const d = await res.json();
        if (res.ok) {
            showToast(`${d.message} EMI ${formatINR(d.emi)}/month.`, 'success');
            await loadDashboard();
        } else {
            showToast(d.error || 'Loan request failed', 'error');
        }
    } catch (e) {
        showToast('Failed to connect to server', 'error');
    }
    btn.disabled = false;
}


// ── INSURANCE (replaces the removed Social Investment / trust mechanic) ──────
function renderInsurance(ins) {
    const wrap = document.getElementById('insuranceOptions');
    if (!wrap || !ins) return;

    wrap.innerHTML = ins.plans.map(p => {
        const selected = p.id === ins.current;
        return `<button class="choice-card" data-plan="${p.id}"
                    style="text-align:left; cursor:pointer; width:100%;
                           border:1px solid ${selected ? 'var(--accent-emerald)' : 'var(--border-glass)'};
                           background:${selected ? 'rgba(16,185,129,0.08)' : 'transparent'};">
            <div style="font-weight:600; font-size:0.9rem; display:flex; justify-content:space-between; gap:0.5rem;">
                <span>${p.name}</span>
                ${selected ? '<span style="color:var(--accent-emerald); font-size:0.75rem;">✓ Active</span>' : ''}
            </div>
            <div style="font-size:0.75rem; color:var(--text-muted); margin-top:0.35rem;">${p.description}</div>
        </button>`;
    }).join('');

    wrap.querySelectorAll('button[data-plan]').forEach(b => {
        b.addEventListener('click', () => setInsurance(b.getAttribute('data-plan')));
    });
}

async function setInsurance(plan) {
    try {
        const res = await fetch(`${API_BASE_URL}/insurance`, {
            method: 'POST',
            headers: await getAuthHeaders(),
            body: JSON.stringify({ plan })
        });
        const d = await res.json();
        if (res.ok) {
            showToast(d.message, 'success');
            await loadDashboard();
        } else {
            showToast(d.error || 'Could not change cover', 'error');
        }
    } catch (e) {
        showToast('Failed to connect to server', 'error');
    }
}


// ============================================================================
// TABS — Home | Invest | Loans & Cover | History
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
    const bar = document.getElementById('tabBar');
    if (!bar) return;
    bar.setAttribute('role', 'tablist');
    bar.setAttribute('aria-label', 'Dashboard sections');
    const tabs = Array.from(bar.querySelectorAll('.tab-btn'));
    tabs.forEach((btn, index) => {
        const panel = document.getElementById('tab-' + btn.dataset.tab);
        btn.id = 'nav-' + btn.dataset.tab;
        btn.setAttribute('role', 'tab');
        btn.setAttribute('aria-controls', panel.id);
        btn.setAttribute('aria-selected', String(btn.classList.contains('active')));
        btn.tabIndex = btn.classList.contains('active') ? 0 : -1;
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', btn.id);
        panel.tabIndex = 0;
        btn.addEventListener('click', () => {
            tabs.forEach(b => {
                const selected = b === btn;
                b.classList.toggle('active', selected);
                b.setAttribute('aria-selected', String(selected));
                b.tabIndex = selected ? 0 : -1;
            });
            document.querySelectorAll('.tab-panel').forEach(pn => pn.classList.toggle('active', pn === panel));
        });
        btn.addEventListener('keydown', event => {
            let target;
            if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
            if (event.key === 'ArrowLeft') target = (index - 1 + tabs.length) % tabs.length;
            if (event.key === 'Home') target = 0;
            if (event.key === 'End') target = tabs.length - 1;
            if (target === undefined) return;
            event.preventDefault();
            tabs[target].click();
            tabs[target].focus();
        });
    });
});

// Show a pulsing dot on the Invest tab while allocation is pending, so the
// required action is findable without scrolling or guessing.
function updateTabBadges(alloc) {
    const investBtn = document.querySelector('.tab-btn[data-tab="invest"]');
    if (!investBtn) return;
    const needed = alloc && alloc.required && !alloc.done;
    investBtn.innerHTML = needed ? '📈 Invest <span style="color:var(--accent-amber);">●</span>' : '📈 Invest';
    if (needed) investBtn.classList.add('pulse-action');
    else investBtn.classList.remove('pulse-action');
}

// Jump helper used by the action banner.
function switchTab(name) {
    const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
    if (btn) btn.click();
}
