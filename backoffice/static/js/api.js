/* Backoffice — shared API client with JWT Bearer, refresh, and error handling */

let _isRefreshing = false;
let _refreshQueue = [];

/**
 * Centralised fetch wrapper for the REST API.
 *
 * 1. Attaches the access token as Authorization: Bearer.
 * 2. On 401, attempts a silent token refresh.
 * 3. On refresh failure, clears sessionStorage and redirects to /login.
 * 4. Returns parsed JSON data or throws an error with a `code` property.
 */
async function apiFetch(url, options = {}) {
  const accessToken = sessionStorage.getItem(CONFIG.TOKEN_ACCESS);
  const headers = new Headers(options.headers || {});

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  headers.set("Content-Type", "application/json");

  let response = await fetch(url, {
    ...options,
    headers,
  });

  // ── Token expired? Try refresh once ──────────────────────────
  if (response.status === 401 && !_isRefreshing) {
    const refreshed = await _attemptRefresh();
    if (refreshed) {
      // Retry with the new token
      const newToken = sessionStorage.getItem(CONFIG.TOKEN_ACCESS);
      headers.set("Authorization", `Bearer ${newToken}`);
      response = await fetch(url, {
        ...options,
        headers,
      });
    } else {
      _forceLogout();
      throw new ApiError("SESSION_EXPIRED", 401, "Session expirée. Veuillez vous reconnecter.");
    }
  }

  // ── Parse JSON body ──────────────────────────────────────────
  let body = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    body = await response.json();
  }

  if (!response.ok) {
    const code = body?.error?.code || "UNKNOWN_ERROR";
    const message = body?.error?.message || response.statusText;
    throw new ApiError(code, response.status, message, body?.error?.details);
  }

  // The API wraps data in { data: …, meta: … }
  return body?.data !== undefined ? body.data : body;
}

/**
 * Attempt to refresh the access token using the stored refresh token.
 * Returns true on success, false otherwise.
 */
async function _attemptRefresh() {
  if (_isRefreshing) {
    // Another refresh is already in progress — wait for it
    return new Promise((resolve) => {
      _refreshQueue.push(resolve);
    });
  }

  _isRefreshing = true;
  const refreshToken = sessionStorage.getItem(CONFIG.TOKEN_REFRESH);
  if (!refreshToken) {
    _isRefreshing = false;
    return false;
  }

  try {
    const response = await fetch(`${CONFIG.API_BASE}/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${refreshToken}`,
      },
    });

    if (!response.ok) {
      _isRefreshing = false;
      _drainQueue(false);
      return false;
    }

    const body = await response.json();
    const newAccessToken = body?.data?.access_token;
    if (!newAccessToken) {
      _isRefreshing = false;
      _drainQueue(false);
      return false;
    }

    sessionStorage.setItem(CONFIG.TOKEN_ACCESS, newAccessToken);
    _isRefreshing = false;
    _drainQueue(true);
    return true;
  } catch {
    _isRefreshing = false;
    _drainQueue(false);
    return false;
  }
}

function _drainQueue(success) {
  _refreshQueue.forEach((resolve) => resolve(success));
  _refreshQueue = [];
}

function _forceLogout() {
  sessionStorage.clear();
  window.location.href = "/login";
}

/* ── Custom error class ──────────────────────────────────────── */

class ApiError extends Error {
  constructor(code, status, message, details) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}
