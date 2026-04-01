// ============================================================================
// DASHBOARD — Main game interface with correct API endpoints
// ============================================================================

let currentUser = null;
let currentMonth = 1;

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
    setInterval(loadDashboard, 5000);
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
        const g = data.game;

        // Game ended → leaderboard
        if (g && g.game_status === 'ended') {
            window.location.href = 'leaderboard.html';
            return;
        }

        // ── Update UI ──
        document.getElementById('monthBadge').innerText = `Month ${p.month}`;
        currentMonth = p.month;

        // Net Worth
        const nwEl = document.getElementById('netWorthVal');
        nwEl.innerText = formatINR(p.net_worth);
        if (p.net_worth < 0) nwEl.classList.add('negative');
        else nwEl.classList.remove('negative');

        // Stats
        document.getElementById('cashVal').innerText = formatINR(p.cash);
        document.getElementById('stocksVal').innerText = formatINR(p.stocks);
        document.getElementById('goldVal').innerText = formatINR(p.gold);
        document.getElementById('emergencyVal').innerText = formatINR(p.emergency_fund);
        document.getElementById('loanVal').innerText = formatINR(p.loans);
        document.getElementById('pendingVal').innerText = formatINR(p.pending_cash_next_month || 0);
        document.getElementById('lifestyleVal').innerText = p.lifestyle_type === 'city' ? 'City' : 'Outer';
        document.getElementById('bikeVal').innerText = p.bike_status
            ? (p.bike_lock_in_months > 0 ? `Locked (${p.bike_lock_in_months}m)` : 'Free')
            : 'None';

        // Risk & Trust
        const riskLevel = p.risk_level || 50;
        const riskLabel = riskLevel > 70 ? 'High' : riskLevel > 40 ? 'Medium' : 'Low';
        const riskColor = riskLevel > 70 ? 'var(--accent-rose)' : riskLevel > 40 ? 'var(--accent-amber)' : 'var(--accent-emerald)';
        document.getElementById('riskVal').innerHTML = `<span style="color:${riskColor}">${riskLabel} (${riskLevel})</span>`;
        document.getElementById('trustVal').innerText = p.trust_score || 0;

        // ── Optional Choices ──
        const optsCon = document.getElementById('optionalChoicesContainer');
        if (optsCon && data.choices) {
            if (data.choices.length === 0) {
                optsCon.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No opportunities this month.</p>';
            } else {
                optsCon.innerHTML = data.choices.map(c => `
                    <div class="choice-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <span style="font-weight: 600; font-size: 0.9rem;">${c.name}</span>
                            <span style="font-size: 0.75rem; color: var(--accent-amber); font-weight: 600;">Cost: ${formatINR(c.cost)}</span>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">
                            ${c.risk_type} • ${c.probability}% chance → ${formatINR(c.reward_value)} ${c.reward_type}
                        </p>
                        <button class="btn-ghost" style="width: 100%; font-size: 0.8rem; padding: 0.4rem; border-color: rgba(245,158,11,0.3); color: var(--accent-amber);"
                                onclick="buyOptionalChoice(${c.id})">
                            <i class="fa-solid fa-dice"></i> Take Chance
                        </button>
                    </div>
                `).join('');
            }
        }

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
            }).join('<hr style="border-color: rgba(255,255,255,0.05); margin: 1rem 0;">');
        }

        // ── Trust Scores from Supabase ──
        try {
            const { data: scores } = await window.supabase.from('player_relative_score')
                .select('*')
                .eq('user_id', currentUser.id);

            if (scores) {
                scores.forEach(s => {
                    if (s.relative_type === 'poor') document.getElementById('trustPoor').innerText = s.trust_score;
                    if (s.relative_type === 'rich') document.getElementById('trustRich').innerText = s.trust_score;
                });
            }
        } catch (e) { /* non-critical */ }

        // ── UI Lock State ──
        const actionButtons = document.querySelectorAll('.sell-btn, .choice-card button, #relativeContainer button');
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
window.buyOptionalChoice = async function(id) {
    if (!confirm('Take this chance? Cost will be deducted immediately.')) return;

    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/buy-choice`, {
            method: 'POST',
            headers: h,
            body: JSON.stringify({ choice_id: id })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message, data.success ? 'success' : 'info');
        } else {
            showToast(data.error, 'error');
        }
        await loadDashboard();
    } catch (err) {
        showToast('Action failed', 'error');
    }
};
