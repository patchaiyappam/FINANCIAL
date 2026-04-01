// ============================================================================
// ADMIN PANEL — Game control, event management, leaderboard
// ============================================================================

function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast-glass toast-${type}`;
    const icons = { error: 'fa-circle-xmark', success: 'fa-circle-check', info: 'fa-circle-info' };
    toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}"></i><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

function showSystemLog(msg, type = 'success') {
    const el = document.getElementById('systemLog');
    const text = document.getElementById('systemLogText');
    el.className = `alert-glass alert-${type} mb-section animate-slide-down`;
    text.innerText = msg;
    el.style.display = 'flex';
    setTimeout(() => { el.style.display = 'none'; }, 6000);
}

function formatINR(val) {
    return `₹${Math.floor(val || 0).toLocaleString('en-IN')}`;
}

document.addEventListener('DOMContentLoaded', () => {
    let currentServerMonth = 1;

    // ── Poll game status ──
    async function tickStatus() {
        try {
            const res = await fetch(`${API_BASE_URL}/game-status`);
            if (res.ok) {
                const data = await res.json();
                const badge = data.game_status === 'active'
                    ? `<span style="color: var(--accent-emerald);">● ACTIVE</span>`
                    : data.game_status === 'ended'
                        ? `<span style="color: var(--accent-rose);">■ ENDED</span>`
                        : `<span style="color: var(--accent-amber);">◌ WAITING</span>`;
                document.getElementById('gameStatusLabel').innerHTML =
                    `${badge} — Month ${data.current_month} of 12`;
                currentServerMonth = data.current_month;
            }
        } catch (e) { console.error('Status poll failed', e); }
    }

    setInterval(tickStatus, 3000);
    tickStatus();

    // ── Start Game ──
    document.getElementById('startBtn').addEventListener('click', async () => {
        if (!confirm('Start/restart the game? This will WIPE all player data!')) return;
        try {
            const res = await fetch(`${API_BASE_URL}/start-game`, { method: 'POST' });
            const data = await res.json();
            showSystemLog(data.message || data.error, res.ok ? 'success' : 'danger');
            showToast(res.ok ? 'Game started!' : 'Failed', res.ok ? 'success' : 'error');
            tickStatus();
            await loadLeaderboard();
        } catch (e) {
            showToast('Error starting game', 'error');
        }
    });

    // ── Next Month ──
    document.getElementById('nextBtn').addEventListener('click', async () => {
        const btn = document.getElementById('nextBtn');
        btn.disabled = true;
        btn.innerHTML = '<div class="spinner-glass" style="width:16px;height:16px;border-width:2px;margin:0 auto;"></div>';

        try {
            const res = await fetch(`${API_BASE_URL}/next-month`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ expected_month: currentServerMonth })
            });
            const data = await res.json();

            if (res.ok) {
                showSystemLog(data.message, 'success');
                showToast(`Month processed! ${data.events_triggered || 0} events triggered.`, 'success');

                // Show event details
                if (data.event_details && data.event_details.length > 0) {
                    const box = document.getElementById('eventResults');
                    box.innerHTML = `<strong style="color: var(--accent-primary);">📊 Events this round:</strong>\n` +
                        data.event_details.map(e =>
                            `  [${e.category || 'event'}] ${e.event} (value: ${e.value})`
                        ).join('\n');
                    box.style.display = 'block';
                }
            } else {
                showSystemLog(data.error || 'Failed to advance month', 'danger');
                showToast(data.error || 'Month processing failed', 'error');
            }

            tickStatus();
            await loadLeaderboard();
        } catch (e) {
            showToast('Network error during month processing', 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-forward-step"></i> Next Month';
        }
    });

    // ── End Game ──
    document.getElementById('endBtn').addEventListener('click', async () => {
        if (!confirm('End the game now? This will show the final leaderboard to all players.')) return;
        try {
            const res = await fetch(`${API_BASE_URL}/end-game`, { method: 'POST' });
            const data = await res.json();
            showSystemLog(data.message, res.ok ? 'success' : 'danger');
            tickStatus();
        } catch (e) {
            showToast('Error ending game', 'error');
        }
    });

    // ── Load Events List ──
    async function loadEvents() {
        try {
            const { data, error } = await window.supabase.from('events').select('*').order('month');
            const list = document.getElementById('eventList');
            if (!data || data.length === 0) {
                list.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No events added yet.</p>';
                return;
            }
            list.innerHTML = data.map(ev => `
                <div class="event-chip">
                    <span style="color: var(--text-secondary);">
                        <strong style="color: var(--text-primary);">M${ev.month}</strong>
                        ${ev.event_name}
                        <span style="color: var(--text-muted);">(${ev.event_type} / ${ev.impact_target}: ${ev.value})</span>
                    </span>
                    <button onclick="delEvent(${ev.id})" style="background: none; border: none; color: var(--accent-rose); cursor: pointer; font-size: 0.75rem; padding: 0.2rem 0.4rem;">
                        <i class="fa-solid fa-times"></i>
                    </button>
                </div>
            `).join('');
        } catch (e) { console.error('Events load failed', e); }
    }

    // ── Load Leaderboard ──
    async function loadLeaderboard() {
        const tbody = document.getElementById('leaderboardTbody');
        try {
            const res = await fetch(`${API_BASE_URL}/leaderboard`);
            const data = await res.json();

            if (!data || data.length === 0) {
                tbody.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem;">No players yet.</p>';
                return;
            }

            const trophies = ['🏆', '🥈', '🥉'];
            tbody.innerHTML = data.map((row, idx) => {
                const name = row.users?.name || 'Anonymous';
                const trophy = idx < 3 ? trophies[idx] + ' ' : '';
                return `
                    <div class="lb-row">
                        <span style="color: var(--text-muted); font-family: var(--font-mono); font-size:0.85rem;">${idx + 1}</span>
                        <span style="font-weight: 600;">${trophy}${name}</span>
                        <span style="color: var(--accent-emerald); font-family: var(--font-mono); font-size: 0.9rem;">${formatINR(row.net_worth)}</span>
                    </div>
                `;
            }).join('');
        } catch (e) {
            tbody.innerHTML = '<p style="color: var(--accent-rose); font-size: 0.85rem; padding: 1rem;">Error loading standings.</p>';
        }
    }

    // ── Event Form Submit ──
    document.getElementById('eventForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            month: parseInt(document.getElementById('evMonth').value),
            event_name: document.getElementById('evName').value,
            event_type: document.getElementById('evType').value,
            impact_target: document.getElementById('evImpact').value,
            value: parseFloat(document.getElementById('evValue').value),
            description: document.getElementById('evDesc').value
        };

        const res = await fetch(`${API_BASE_URL}/event`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            showToast(`Event added for Month ${payload.month}`, 'success');
            e.target.reset();
            await loadEvents();
        } else {
            showToast('Failed to add event', 'error');
        }
    });

    // ── Choice Form Submit ──
    document.getElementById('choiceForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            month: parseInt(document.getElementById('optMonth').value),
            name: document.getElementById('optName').value,
            cost: parseFloat(document.getElementById('optCost').value),
            risk_type: document.getElementById('optRisk').value,
            reward_type: document.getElementById('optRewardType').value,
            probability: parseInt(document.getElementById('optProb').value),
            reward_value: parseFloat(document.getElementById('optVal').value)
        };

        const res = await fetch(`${API_BASE_URL}/choice-admin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            showToast(`Choice "${payload.name}" added for Month ${payload.month}`, 'success');
            e.target.reset();
        } else {
            showToast('Failed to add choice', 'error');
        }
    });

    document.getElementById('refreshLeaderboardBtn').addEventListener('click', loadLeaderboard);

    // Init
    loadEvents();
    loadLeaderboard();
});

// ── Delete Event (global) ──
window.delEvent = async function(id) {
    const res = await fetch(`${API_BASE_URL}/event/${id}`, { method: 'DELETE' });
    if (res.ok) {
        // Reload events list
        const { data } = await window.supabase.from('events').select('*').order('month');
        const list = document.getElementById('eventList');
        document.getElementById('eventList').innerHTML = '';
        // Trigger refresh without page reload
        const event = new Event('submit');
        document.getElementById('eventList').dispatchEvent(event);
        window.location.reload();
    }
};
