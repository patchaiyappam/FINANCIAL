// ============================================================================
// ALLOCATION PAGE — Month 1 Budget Distribution
// ============================================================================

let isCity = true;
let hasBike = false;

// Expose lifestyle selector globally
window.selectLifestyle = function(type) {
    isCity = (type === 'city');
    document.getElementById('radioCity').classList.toggle('selected', isCity);
    document.getElementById('radioOuter').classList.toggle('selected', !isCity);
    updateFixedExpenses();
    calculateTotal();
};

document.addEventListener('DOMContentLoaded', async () => {
    // ── Auth Check ──
    const waitForSession = async () => {
        let retries = 5;
        while (retries--) {
            const { data: { session } } = await window.supabase.auth.getSession();
            if (session) return session;
            await new Promise(res => setTimeout(res, 500));
        }
        alert("Unauthorized — Please login first.");
        window.location.href = '/';
        return null;
    };

    const session = await waitForSession();
    if (!session) return;

    window.supabase.auth.onAuthStateChange((event, session) => {
        if (event === 'SIGNED_OUT') window.location.href = '/';
    });

    // ── DOM References ──
    const valRent = document.getElementById('valRent');
    const valTransport = document.getElementById('valTransport');
    const valBikeDp = document.getElementById('valBikeDp');
    const bikeDpwContainer = document.getElementById('bikeDpwContainer');
    const inputs = document.querySelectorAll('.user-input');
    const totalText = document.getElementById('totalText');
    const btnSubmit = document.getElementById('btnSubmit');
    const errorMsg = document.getElementById('errorMsg');
    const statusText = document.getElementById('statusText');
    const totalRing = document.getElementById('totalRing');

    // ── Bike Toggle ──
    document.getElementById('bikeStatus').addEventListener('change', (e) => {
        hasBike = e.target.checked;
        bikeDpwContainer.style.display = hasBike ? 'block' : 'none';
        updateFixedExpenses();
        calculateTotal();
    });

    function updateFixedExpenses() {
        if (isCity) {
            valRent.value = 25000;
            valTransport.value = 5000;
        } else {
            valRent.value = 10000;
            valTransport.value = 5000;
        }

        if (hasBike) {
            valBikeDp.value = 10000;
            // Bike halves transport cost
            valTransport.value = Math.floor(parseInt(valTransport.value) * 0.5);
        } else {
            valBikeDp.value = 0;
        }
    }

    function calculateTotal() {
        let total = parseInt(valRent.value || 0) +
                    parseInt(valTransport.value || 0) +
                    parseInt(valBikeDp.value || 0);

        inputs.forEach(input => {
            total += parseInt(input.value || 0);
        });

        // Format with Indian numbering
        const formatted = total.toLocaleString('en-IN');
        totalText.innerText = `₹${formatted}`;

        const pct = Math.min((total / 100000) * 100, 100);
        document.getElementById('totalBar').style.width = `${pct}%`;
        totalRing.style.setProperty('--pct', `${pct}%`);

        if (total === 100000) {
            btnSubmit.disabled = false;
            errorMsg.style.display = 'none';
            statusText.innerHTML = '<span style="color: var(--accent-emerald);">✓ Budget perfectly balanced</span>';
            totalText.className = 'total-amount text-emerald';
        } else {
            btnSubmit.disabled = true;
            errorMsg.style.display = 'block';
            const diff = 100000 - total;
            if (diff > 0) {
                errorMsg.innerText = `₹${diff.toLocaleString('en-IN')} remaining to allocate`;
                statusText.innerHTML = `<span style="color: var(--accent-amber);">⚠ ₹${diff.toLocaleString('en-IN')} unallocated</span>`;
                totalText.className = 'total-amount text-amber';
            } else {
                errorMsg.innerText = `Over allocated by ₹${Math.abs(diff).toLocaleString('en-IN')}`;
                statusText.innerHTML = `<span style="color: var(--accent-rose);">✗ Over budget by ₹${Math.abs(diff).toLocaleString('en-IN')}</span>`;
                totalText.className = 'total-amount text-rose';
            }
        }
    }

    inputs.forEach(i => i.addEventListener('input', calculateTotal));

    // ── Submit Allocation ──
    btnSubmit.addEventListener('click', async () => {
        btnSubmit.disabled = true;
        btnSubmit.innerHTML = '<div class="spinner-glass" style="width:20px;height:20px;border-width:2px;margin:0 auto;"></div>';

        const payload = {
            rent: valRent.value,
            transport: valTransport.value,
            lifestyle_type: isCity ? 'city' : 'outer',
            bike_status: hasBike,
            bike_down_payment: valBikeDp.value,
            food: document.getElementById('valFood').value,
            family: document.getElementById('valFamily').value,
            stocks: document.getElementById('valStocks').value,
            gold: document.getElementById('valGold').value,
            emergency_fund: document.getElementById('valEmergency').value,
            misc: document.getElementById('valMisc').value
        };

        try {
            const { data: { session: freshSession } } = await window.supabase.auth.getSession();
            const res = await fetch(`${API_BASE_URL}/allocate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${freshSession.access_token}`
                },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                window.location.href = 'dashboard.html';
            } else {
                const data = await res.json();
                showToast(data.error || 'Allocation failed', 'error');
                btnSubmit.disabled = false;
                btnSubmit.innerHTML = '<i class="fa-solid fa-check me-2"></i>Confirm Allocation';
            }
        } catch (err) {
            console.error(err);
            showToast('Failed to connect to server', 'error');
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = '<i class="fa-solid fa-check me-2"></i>Confirm Allocation';
        }
    });

    // Initial calc
    calculateTotal();
});

// ── Toast Notification ──
function showToast(message, type = 'info') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-glass toast-${type}`;
    const icon = type === 'error' ? 'fa-circle-xmark' : type === 'success' ? 'fa-circle-check' : 'fa-circle-info';
    toast.innerHTML = `<i class="fa-solid ${icon}"></i><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
