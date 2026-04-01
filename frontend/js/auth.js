document.addEventListener('DOMContentLoaded', () => {
    const loginBtn  = document.getElementById('loginBtn');
    const errorBox  = document.getElementById('loginError');  // optional UI element

    function showError(msg) {
        console.error('[Auth]', msg);
        if (errorBox) { errorBox.textContent = msg; errorBox.classList.remove('d-none'); }
        else alert(msg);
    }

    // Auto-redirect if session already exists
    // checkSessionAndRedirect(); // This is now handled by the onAuthStateChange listener

    // Listen for auth state changes (crucial for OAuth redirect)
    window.supabase.auth.onAuthStateChange((event, session) => {
        console.log("🔥 [Auth] Event:", event);
        if (session && (event === 'SIGNED_IN' || event === 'USER_UPDATED')) {
            console.log("User logged in:", session.user);
            window.location.href = '/case-study.html'; // Redirect to case-study page
        } else if (event === 'SIGNED_OUT') {
            console.log("User signed out.");
            window.location.href = '/'; // Redirect to home page on sign out
        }
    });

    // Initial check for session on page load
    checkSessionAndRedirect();
});

// Expose globally so onclick can find it
window.loginWithGoogle = async function () {
  console.log("🔥 [Auth] Login button clicked!");

  const client = window.supabase; // Ensure consistency in calling the Supabase auth client
  if (!client) {
      console.error("[Auth] Supabase client NOT found. Check config.js.");
      alert("System Error: Supabase not initialized.");
      return;
  }

  const { data, error } = await client.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: window.location.origin
    }
  });

  if (error) console.error("OAuth Error:", error);
  console.log("RESULT:", data, error);
};

async function checkSessionAndRedirect() {
    try {
        const client = window.supabase; // Ensure consistency in calling the Supabase auth client
        if (!client) {
            console.error("[Auth] Supabase client NOT found during session check. Check config.js.");
            return;
        }

        const { data: { session } } = await client.auth.getSession();
        if (session) {
            // If a session exists, redirect to the case-study page
            window.location.href = '/case-study.html';
        } else {
            // If no session, ensure we are on the home page (or login page)
            if (window.location.pathname !== '/') {
                // Only redirect if not already on the home page to avoid unnecessary redirects
                window.location.href = '/';
            }
        }
    } catch (e) {
        console.error('[Auth] Session check failed:', e.message);
        // In case of an error during session check, redirect to home page
        window.location.href = '/';
    }
}
