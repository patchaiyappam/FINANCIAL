document.addEventListener('DOMContentLoaded', async () => {
    // Check auth with retry for OAuth redirect delay
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


    // Handle redirect login properly
    window.supabase.auth.onAuthStateChange((event, session) => {
        if (session) {
            console.log("User session active:", session.user);
        } else if (event === 'SIGNED_OUT') {
            window.location.href = '/';
        }
    });


    const valRent = document.getElementById('valRent');
    const valTransport = document.getElementById('valTransport');
    const valBikeDp = document.getElementById('valBikeDp');
    const bikeDpwContainer = document.getElementById('bikeDpwContainer');
    
    // User inputs
    const inputs = document.querySelectorAll('.user-input');
    const totalText = document.getElementById('totalText');
    const btnSubmit = document.getElementById('btnSubmit');
    const errorMsg = document.getElementById('errorMsg');
    
    let isCity = true;
    let hasBike = false;

    // Lifestyle radio buttons
    document.querySelectorAll('input[name="lifestyle"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            isCity = e.target.value === 'city';
            updateFixedExpenses();
            calculateTotal();
        });
    });

    // Bike toggle
    document.getElementById('bikeStatus').addEventListener('change', (e) => {
        hasBike = e.target.checked;
        bikeDpwContainer.style.display = hasBike ? 'block' : 'none';
        updateFixedExpenses();
        calculateTotal();
    });

    function updateFixedExpenses() {
        if (isCity) {
            valRent.value = 25000;
            valTransport.value = 2000;
        } else {
            valRent.value = 10000;
            valTransport.value = 10000;
        }

        if (hasBike) {
            valBikeDp.value = 10000;
            valTransport.value = parseInt(valTransport.value) * 0.5;
        } else {
            valBikeDp.value = 0;
        }
    }

    function calculateTotal() {
        let total = parseInt(valRent.value) + parseInt(valTransport.value) + parseInt(valBikeDp.value);
        inputs.forEach(input => {
            total += parseInt(input.value || 0);
        });
        
        totalText.innerText = `₹${total.toLocaleString('en-IN')}`;
        const barWidth = Math.min((total / 100000) * 100, 100);
        document.getElementById('totalBar').style.width = `${barWidth}%`;
        
        if (total === 100000) {
            btnSubmit.disabled = false;
            errorMsg.classList.add('d-none');
        } else {
            btnSubmit.disabled = true;
            errorMsg.classList.remove('d-none');
            errorMsg.innerText = `Total is ₹${total}. Must be exactly ₹1,00,000.`;
        }
    }

    inputs.forEach(i => i.addEventListener('input', calculateTotal));
    
    btnSubmit.addEventListener('click', async () => {
        btnSubmit.disabled = true;
        btnSubmit.innerText = "Processing...";
        
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
                alert(data.error);
                btnSubmit.disabled = false;
                btnSubmit.innerText = "Confirm Allocation";
            }
        } catch (err) {
            console.error(err);
            alert("Error communicating with server.");
            btnSubmit.disabled = false;
            btnSubmit.innerText = "Confirm Allocation";
        }
    });

    // initial calc
    calculateTotal();
});

