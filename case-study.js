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


    // Auth state update
    window.supabase.auth.onAuthStateChange((event, session) => {
        if (!session) window.location.href = '/';
    });


    // Fetch case study
    try {
        const h = { 'Authorization': `Bearer ${session.access_token}` };
        const response = await fetch(`${API_BASE_URL}/case-study`, { headers: h });

        const data = await response.json();
        
        document.getElementById('csTitle').innerText = data.title || "The First Job";
        document.getElementById('csDesc').innerText = data.description || "You have landed your first job...";
        document.getElementById('csRent').innerText = `₹${data.rent || 20000}`;
        document.getElementById('csFood').innerText = `₹${data.food || 10000}`;
        document.getElementById('csTransport').innerText = `₹${data.transport || 5000}`;
        document.getElementById('csFamily').innerText = `₹${data.family || 5000}`;
    } catch (err) {
        console.error('Error fetching case study:', err);
    }
});

