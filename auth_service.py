# =============================================================================
# AUTH SERVICE — Handles user authentication via Supabase
# =============================================================================

from supabase_client import supabase


def get_user_id(request) -> str | None:
    """Extract user_id from Bearer token via Supabase Auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    try:
        user_res = supabase.auth.get_user(token)
        return user_res.user.id
    except Exception as e:
        print(f"[Auth] Token validation failed: {e}")
        return None


def require_auth(request):
    """Returns user_id or raises a tuple (error_response, status_code)."""
    uid = get_user_id(request)
    if not uid:
        return None
    return uid
