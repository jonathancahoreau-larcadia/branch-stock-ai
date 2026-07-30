/* Backoffice — authentication: login, logout, refresh, current user */

/**
 * Authenticate with username/password via the API.
 * Stores tokens in sessionStorage and user info.
 */
async function login(username, password) {
  const response = await fetch(`${CONFIG.API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    let message = "Identifiants invalides.";
    try {
      const body = await response.json();
      if (body?.error?.code === "ACCOUNT_INACTIVE") {
        message = "Compte désactivé. Contactez un administrateur.";
      }
    } catch {
      // keep default message
    }
    throw new Error(message);
  }

  const body = await response.json();
  const data = body.data;

  sessionStorage.setItem(CONFIG.TOKEN_ACCESS, data.access_token);
  sessionStorage.setItem(CONFIG.TOKEN_REFRESH, data.refresh_token);
  sessionStorage.setItem(CONFIG.USER_KEY, JSON.stringify(data.user));

  return data.user;
}

/**
 * Log out: revoke tokens on the server, then clear local state.
 */
async function logout() {
  const accessToken = sessionStorage.getItem(CONFIG.TOKEN_ACCESS);
  const refreshToken = sessionStorage.getItem(CONFIG.TOKEN_REFRESH);

  // Attempt to revoke both tokens (best-effort)
  const headers = { "Content-Type": "application/json" };

  if (accessToken) {
    try {
      await fetch(`${CONFIG.API_BASE}/auth/logout`, {
        method: "POST",
        headers: { ...headers, Authorization: `Bearer ${accessToken}` },
      });
    } catch {
      // network error — continue clearing local state
    }
  }

  if (refreshToken) {
    try {
      await fetch(`${CONFIG.API_BASE}/auth/logout/refresh`, {
        method: "POST",
        headers: { ...headers, Authorization: `Bearer ${refreshToken}` },
      });
    } catch {
      // network error — continue clearing local state
    }
  }

  sessionStorage.clear();
  window.location.href = "/login";
}

/**
 * Return the current user object from sessionStorage, or null.
 */
function getCurrentUser() {
  const raw = sessionStorage.getItem(CONFIG.USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Check if the user is authenticated (has an access token).
 */
function isAuthenticated() {
  return !!sessionStorage.getItem(CONFIG.TOKEN_ACCESS);
}

/**
 * Redirect to /login if not authenticated.
 * Call this on page load for protected pages.
 */
function requireAuth() {
  if (!isAuthenticated()) {
    window.location.href = "/login";
    return false;
  }
  return true;
}

/**
 * Redirect to / if the current user is not an admin.
 */
function requireAdmin() {
  const user = getCurrentUser();
  if (!user || user.role !== "admin") {
    window.location.href = "/";
    return false;
  }
  return true;
}
</write_to_file>