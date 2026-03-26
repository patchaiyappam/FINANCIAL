let currentUser = null;
let currentMonth = 1;

async function getAuthHeaders() {
    const { data: { session: freshSession } } = await window.supabase.auth.getSession();
    if (!freshSession) {
        window.location.href = '/';
        return {};
    }
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${freshSession.access_token}`
    };
}

document.addEventListener('DOMContentLoaded', async () => {
    const waitForSession = async () => {
        let retries = 5;
        while (retries--) {
            const { data: { session } } = await window.supabase.auth.getSession();
            if (session) {
                console.log("Session READY:", session);
                return session;
            }
            console.log("Waiting for session...");
            await new Promise(res => setTimeout(res, 500));
        }
        console.log("No session after retries → redirect");
        alert("Unauthorized - Please Login First");
        window.location.href = '/';
        return null;
    };

    const session = await waitForSession();
    if (!session) return;

    currentUser = session.user;

    // Handle session updates (crucial if token expires or state shifts)
    window.supabase.auth.onAuthStateChange((event, session) => {
        if (!session) {
            window.location.href = '/';
        } else {
            currentUser = session.user;
        }
    });

    
    document.getElementById('userName').innerText = currentUser.user_metadata?.name || currentUser.email;
    
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        await window.supabase.auth.signOut();
        window.location.href = '/';
    });

    
    document.getElementById('endTurnBtn').addEventListener('click', async () => {
        const confirmResult = window.confirm("Are you sure you're done for this month? You won't be able to make more choices until the Admin advances the game.");
        if (!confirmResult) return;
        
        try {
            const h = await getAuthHeaders();
            const res = await fetch(`${API_BASE_URL}/lock-turn`, {
                method: 'POST',
                headers: h
            });
            const data = await res.json();
            if(res.ok) alert(data.message);
            else alert(data.error);
            await loadDashboard();
        } catch(err) {
            console.error(err);
        }
    });

    await loadDashboard();
    
    // Poll every 5 seconds for updates
    setInterval(loadDashboard, 5000);
});

async function loadDashboard() {
    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/dashboard`, {
            headers: h
        });
        
        if (res.status === 404) {
             window.location.href = 'allocation.html';
             return;
        }
        
        const data = await res.json();
        const p = data.player;
        const g = data.game;
        
        if (g.game_status === 'ended') {
             window.location.href = 'leaderboard.html';
             return;
        }
        
        document.getElementById('monthBadge').innerText = `Month ${p.month}`;
        currentMonth = p.month;
        
        // Update stats
        document.getElementById('netWorthVal').innerText = `₹${p.net_worth.toLocaleString('en-IN')}`;
        document.getElementById('cashVal').innerText = `₹${Math.floor(p.cash).toLocaleString('en-IN')}`;
        document.getElementById('loanVal').innerText = `₹${Math.floor(p.loans).toLocaleString('en-IN')}`;
        document.getElementById('stocksVal').innerText = `₹${Math.floor(p.stocks).toLocaleString('en-IN')}`;
        document.getElementById('goldVal').innerText = `₹${Math.floor(p.gold).toLocaleString('en-IN')}`;
        document.getElementById('emergencyVal').innerText = `₹${Math.floor(p.emergency_fund).toLocaleString('en-IN')}`;
        document.getElementById('pendingVal').innerText = `₹${Math.floor(p.pending_cash_next_month).toLocaleString('en-IN')}`;
        document.getElementById('lifestyleVal').innerText = p.lifestyle_type === 'city' ? "City" : "Outer Area";
        
        // Build Optional Choices
        const optsCon = document.getElementById('optionalChoicesContainer');
        if (optsCon && data.choices) {
            optsCon.innerHTML = '';
            if (data.choices.length === 0) {
                optsCon.innerHTML = '<p class="text-muted p-3">No optional opportunities this month.</p>';
            } else {
                data.choices.forEach(c => {
                    optsCon.innerHTML += `
                    <div class="glass-card mb-3 border-secondary p-3">
                        <h6 class="mb-1">${c.name} <span class="badge bg-warning text-dark float-end">Cost: ₹${c.cost}</span></h6>
                        <p class="mb-2 text-muted small">${c.risk_type} - May reward ${c.reward_value} ${c.reward_type} (${c.probability}% chance)</p>
                        <button class="btn btn-sm btn-outline-primary w-100 rounded-pill" onclick="buyOptionalChoice(${c.id})">Take Chance</button>
                    </div>
                    `;
                });
            }
        }

        // Handle Status Locks
        document.getElementById('bikeVal').innerText = p.bike_status ? (p.bike_lock_in_months > 0 ? `Locked (${p.bike_lock_in_months}m)` : "Free") : "None";
        
        if (g.current_month > p.month) { 
             // Player is behind game? This shouldn't happen because game_control increment handles all players.
        }

        // Toggle UI lockout if waiting
        const actionButtons = document.querySelectorAll('button[onclick]');
        const endTurnBtn = document.getElementById('endTurnBtn');
        const statusBanner = document.getElementById('statusBanner');
        
        if (p.status === 'waiting') {
            actionButtons.forEach(btn => btn.disabled = true);
            endTurnBtn.style.display = 'none';
            statusBanner.style.display = 'block';
        } else {
            actionButtons.forEach(btn => btn.disabled = false);
            endTurnBtn.style.display = 'inline-block';
            statusBanner.style.display = 'none';
        }

        // Fetch scores separately for UI
        const { data: scores } = await window.supabase.from('player_relative_score')
            .select('*')
            .eq('user_id', currentUser.id);
            
        if (scores) {
             scores.forEach(s => {
                  if (s.relative_type === 'poor') document.getElementById('trustPoor').innerText = s.trust_score;
                  if (s.relative_type === 'rich') document.getElementById('trustRich').innerText = s.trust_score;
             });
        }
        
    } catch(err) {
        console.error(err);
    }
}

async function sellAsset(asset) {
    const amountStr = prompt(`How much ${asset} do you want to sell? (5% penalty applies, cash available next month)`);
    if (!amountStr) return;
    
    const amount = parseInt(amountStr);
    if (isNaN(amount) || amount <= 0) return alert('Invalid amount');
    
    await makeChoice({ type: 'sell_asset', asset, amount });
}

async function handleRelative(relative_type, action) {
    if (action === 'none') {
         alert("You chose not to help. No trust gained.");
         return;
    }
    await makeChoice({ type: 'relative', relative_type, action });
}

async function buyOptional(cost) {
    const confirm = window.confirm(`Are you sure you want to spend ₹${cost}?`);
    if (!confirm) return;
    await makeChoice({ type: 'optional', cost });
}

async function makeChoice(payload) {
    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/choice`, {
            method: 'POST',
            headers: h,
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();
        alert(data.message || data.error);
        await loadDashboard();
    } catch(err) {
         console.error(err);
         alert("Network error processing choice");
    }
}

window.buyOptionalChoice = async function(id) {
    if (!confirm(`Are you sure you want to buy this optional choice?`)) return;
    try {
        const h = await getAuthHeaders();
        const res = await fetch(`${API_BASE_URL}/choice`, {
            method: 'POST',
            headers: h,
            body: JSON.stringify({ type: 'optional', id: id })
        });
        const data = await res.json();
        if (res.ok) {
            alert(data.message);
            loadDashboard();
        } else {
            alert(data.error);
        }
    } catch (e) {
        alert("Action failed.");
    }
}

