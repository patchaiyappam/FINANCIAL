document.addEventListener('DOMContentLoaded', () => {
    
    // Auth for admin can be skipped or just use normal if you want.
    // For this prototype, admin panel relies on endpoints.
    
    const sysLog = document.getElementById('systemLog');
    
    let currentServerMonth = 1;

    async function tickStatus() {
        try {
            const res = await fetch(`${API_BASE_URL}/game-status`);
            if (res.ok) {
                const data = await res.json();
                document.getElementById('gameStatusLabel').innerText = `Month ${data.current_month} | Status: ${data.game_status}`;
                currentServerMonth = data.current_month;
            }
        } catch(e) {}
    }
    
    setInterval(tickStatus, 3000);
    tickStatus();
    
    document.getElementById('startBtn').addEventListener('click', async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/start-game`, { method: 'POST' });
            const data = await res.json();
            sysLog.innerText = data.message;
            tickStatus();
        } catch (e) {
            sysLog.innerText = "Error starting game";
        }
    });

    document.getElementById('nextBtn').addEventListener('click', async () => {
        try {
            sysLog.innerText = "Processing month...";
            const res = await fetch(`${API_BASE_URL}/next-month`, { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ expected_month: currentServerMonth })
            });
            const data = await res.json();
            sysLog.innerText = data.message || data.error;
            tickStatus();
        } catch (e) {
            sysLog.innerText = "Error advancing month";
        }
    });

    // We can just query Supabase directly for Admin reading events
    loadEvents();
    loadLeaderboard();

    document.getElementById('eventForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const payload = {
            month: document.getElementById('evMonth').value,
            event_name: document.getElementById('evName').value,
            event_type: document.getElementById('evType').value,
            impact_target: document.getElementById('evImpact').value,
            value: document.getElementById('evValue').value,
            description: document.getElementById('evDesc').value
        };

        const res = await fetch(`${API_BASE_URL}/event`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            sysLog.innerText = "Event added";
            loadEvents();
        }
    });

    document.getElementById('choiceForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const payload = {
            month: document.getElementById('optMonth').value,
            name: document.getElementById('optName').value,
            cost: document.getElementById('optCost').value,
            risk_type: document.getElementById('optRisk').value,
            reward_type: document.getElementById('optRewardType').value,
            probability: document.getElementById('optProb').value,
            reward_value: document.getElementById('optVal').value
        };

        const res = await fetch(`${API_BASE_URL}/choice-admin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            sysLog.innerText = "Optional choice added";
        }
    });

    document.getElementById('refreshLeaderboardBtn').addEventListener('click', loadLeaderboard);

    async function loadEvents() {
        const { data, error } = await window.supabase.from('events').select('*').order('month');
        if (data) {
            const list = document.getElementById('eventList');
            list.innerHTML = '';
            data.forEach(ev => {
                list.innerHTML += `<li class="list-group-item bg-transparent text-light border-secondary d-flex justify-content-between">
                    <span>Month ${ev.month}: ${ev.event_name} (${ev.event_type} on ${ev.impact_target}: ${ev.value})</span>
                    <button class="btn btn-sm btn-danger py-0 px-2" onclick="delEvent(${ev.id})">X</button>
                </li>`;
            });
        }
    }

    async function loadLeaderboard() {
        const res = await fetch(`${API_BASE_URL}/leaderboard`);
        const data = await res.json();
        const tbody = document.getElementById('leaderboardTbody');
        tbody.innerHTML = '';
        data.forEach(row => {
            const name = row.users?.name || "Anonymous";
            tbody.innerHTML += `<tr><td>${name}</td><td>₹${row.net_worth.toLocaleString('en-IN')}</td></tr>`;
        });
    }

});

async function delEvent(id) {
    const res = await fetch(`${API_BASE_URL}/event/${id}`, { method: 'DELETE' });
    if (res.ok) {
        document.getElementById('systemLog').innerText = "Event deleted";
        // Reload events relies on supabase call in global scope... 
        // Quick reload
        window.location.reload();
    }
}

