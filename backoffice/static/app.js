(() => {
  "use strict";

  const ACCESS_KEY = "hbntory_access_token";
  const REFRESH_KEY = "hbntory_refresh_token";

  const loginPanel = document.querySelector("#login-panel");
  const application = document.querySelector("#application");
  const loginForm = document.querySelector("#login-form");
  const loginMessage = document.querySelector("#login-message");
  const appMessage = document.querySelector("#app-message");
  const currentUser = document.querySelector("#current-user");
  const content = document.querySelector("#content");
  const viewTitle = document.querySelector("#view-title");
  const refreshButton = document.querySelector("#refresh-button");
  const logoutButton = document.querySelector("#logout-button");
  const stockPanel = document.querySelector("#stock-operation-panel");
  const stockForm = document.querySelector("#stock-operation-form");

  const resourceLabels = {
    dashboard: "Tableau de bord",
    branches: "Branches",
    products: "Produits",
    stocks: "Stocks",
    users: "Utilisateurs",
  };

  const resourcePaths = {
    branches: "/api/v1/branches",
    products: "/api/v1/products",
    stocks: "/api/v1/stocks",
    users: "/api/v1/users",
  };

  const ROLE_RESOURCES = {
    admin: new Set(["dashboard", "branches", "products", "users"]),
    common_user: new Set(["dashboard", "branches", "products", "stocks"]),
  };

  let currentRole = null;

  let activeResource = "dashboard";

  function canAccessResource(resource) {
    return ROLE_RESOURCES[currentRole]?.has(resource) ?? false;
  }

  function applyRoleNavigation(role) {
    document.querySelectorAll("[data-resource]").forEach((button) => {
      const resource = button.dataset.resource;
      button.hidden = !(ROLE_RESOURCES[role]?.has(resource) ?? false);
    });

    stockPanel.hidden =
      !canAccessResource("stocks") || activeResource !== "stocks";
  }

  function setMessage(element, text, kind = "") {
    element.textContent = text;
    element.className = `message ${kind}`.trim();
  }

  function clearTokens() {
    sessionStorage.removeItem(ACCESS_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
  }

  function storeTokens(data) {
    sessionStorage.setItem(ACCESS_KEY, data.access_token);
    sessionStorage.setItem(REFRESH_KEY, data.refresh_token);
  }

  function accessToken() {
    return sessionStorage.getItem(ACCESS_KEY);
  }

  function refreshToken() {
    return sessionStorage.getItem(REFRESH_KEY);
  }

  async function parseJsonResponse(response) {
    const text = await response.text();

    if (!text) {
      return {};
    }

    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`Réponse non JSON reçue (${response.status}).`);
    }
  }

  async function refreshAccessToken() {
    const token = refreshToken();

    if (!token) {
      return false;
    }

    const response = await fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      clearTokens();
      return false;
    }

    const payload = await parseJsonResponse(response);
    const data = payload.data ?? payload;

    if (!data.access_token) {
      clearTokens();
      return false;
    }

    sessionStorage.setItem(ACCESS_KEY, data.access_token);

    if (data.refresh_token) {
      sessionStorage.setItem(REFRESH_KEY, data.refresh_token);
    }

    return true;
  }

  async function apiRequest(path, options = {}, retry = true) {
    const headers = new Headers(options.headers ?? {});
    const token = accessToken();

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const response = await fetch(path, {
      ...options,
      headers,
    });

    if (response.status === 401 && retry && await refreshAccessToken()) {
      return apiRequest(path, options, false);
    }

    const payload = await parseJsonResponse(response);

    if (!response.ok) {
      const message =
        payload?.error?.message ??
        payload?.message ??
        `Erreur HTTP ${response.status}`;

      throw new Error(message);
    }

    return payload;
  }

  function extractRows(payload) {
    const data = payload?.data ?? payload;

    if (Array.isArray(data)) {
      return data;
    }

    if (data && typeof data === "object") {
      for (const key of ["items", "results", "branches", "products", "stocks", "users"]) {
        if (Array.isArray(data[key])) {
          return data[key];
        }
      }

      return [data];
    }

    return [];
  }

  function formatCell(value) {
    if (value === null || value === undefined) {
      return "—";
    }

    if (typeof value === "object") {
      return JSON.stringify(value, null, 2);
    }

    return String(value);
  }

  function renderRows(rows) {
    content.replaceChildren();

    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "Aucune donnée à afficher.";
      content.append(empty);
      return;
    }

    const columns = Array.from(
      rows.reduce((set, row) => {
        if (row && typeof row === "object" && !Array.isArray(row)) {
          Object.keys(row).forEach((key) => set.add(key));
        } else {
          set.add("value");
        }

        return set;
      }, new Set())
    );

    const table = document.createElement("table");
    table.className = "data-table";

    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");

    columns.forEach((column) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      headRow.append(th);
    });

    thead.append(headRow);

    const tbody = document.createElement("tbody");

    rows.forEach((row) => {
      const tr = document.createElement("tr");

      columns.forEach((column) => {
        const td = document.createElement("td");
        const pre = document.createElement("pre");
        pre.className = "json-value";

        const value =
          row && typeof row === "object" && !Array.isArray(row)
            ? row[column]
            : row;

        pre.textContent = formatCell(value);
        td.append(pre);
        tr.append(td);
      });

      tbody.append(tr);
    });

    table.append(thead, tbody);
    content.append(table);
  }

  async function loadDashboard() {
    const payload = await apiRequest("/api/v1/auth/me");
    const user = payload?.data ?? payload;
    renderRows([user]);
  }

  async function loadResource(resource = activeResource) {
    if (!canAccessResource(resource)) {
      setMessage(
        appMessage,
        "Cette ressource n’est pas autorisée pour votre rôle.",
        "error"
      );
      return;
    }

    activeResource = resource;
    viewTitle.textContent = resourceLabels[resource] ?? resource;
    stockPanel.hidden =
      !canAccessResource("stocks") || resource !== "stocks";
    setMessage(appMessage, "Chargement…");

    try {
      if (resource === "dashboard") {
        await loadDashboard();
      } else {
        const payload = await apiRequest(resourcePaths[resource]);
        renderRows(extractRows(payload));
      }

      setMessage(appMessage, "Données chargées.", "success");
    } catch (error) {
      setMessage(appMessage, error.message, "error");

      if (!accessToken()) {
        showLogin();
      }
    }
  }

  function showApplication(user) {
    loginPanel.hidden = true;
    application.hidden = false;
    currentRole = user?.role ?? null;
    applyRoleNavigation(currentRole);

    const branch = user?.branch?.name ?? user?.branch ?? "toutes les branches";
    currentUser.textContent =
      `${user?.username ?? "utilisateur"} — ${user?.role ?? "rôle inconnu"} — ${branch}`;

    loadResource("dashboard");
  }

  function showLogin(message = "") {
    application.hidden = true;
    loginPanel.hidden = false;
    currentRole = null;
    activeResource = "dashboard";
    applyRoleNavigation(currentRole);
    currentUser.textContent = "";
    content.replaceChildren();

    if (message) {
      setMessage(loginMessage, message, "error");
    }
  }

  async function restoreSession() {
    if (!accessToken()) {
      showLogin();
      return;
    }

    try {
      const payload = await apiRequest("/api/v1/auth/me");
      showApplication(payload?.data ?? payload);
    } catch {
      clearTokens();
      showLogin("Votre session a expiré. Reconnectez-vous.");
    }
  }

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setMessage(loginMessage, "Connexion…");

    const formData = new FormData(loginForm);

    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: String(formData.get("username") ?? "").trim(),
          password: String(formData.get("password") ?? ""),
        }),
      });

      const payload = await parseJsonResponse(response);

      if (!response.ok) {
        throw new Error(
          payload?.error?.message ??
          payload?.message ??
          "Identifiants incorrects."
        );
      }

      const data = payload.data ?? payload;
      storeTokens(data);
      loginForm.reset();
      setMessage(loginMessage, "");
      showApplication(data.user);
    } catch (error) {
      clearTokens();
      setMessage(loginMessage, error.message, "error");
    }
  });

  document.querySelectorAll("[data-resource]").forEach((button) => {
    button.addEventListener("click", () => {
      loadResource(button.dataset.resource);
    });
  });

  refreshButton.addEventListener("click", () => {
    loadResource(activeResource);
  });

  stockForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!canAccessResource("stocks")) {
      setMessage(
        appMessage,
        "Les opérations de stock ne sont pas autorisées pour votre rôle.",
        "error"
      );
      return;
    }

    const formData = new FormData(stockForm);
    const productId = encodeURIComponent(
      String(formData.get("product_id") ?? "").trim()
    );
    const quantity = Number(formData.get("quantity"));
    const action = formData.get("action") === "remove" ? "remove" : "add";

    if (!productId || !Number.isInteger(quantity) || quantity < 1) {
      setMessage(appMessage, "Produit et quantité positive obligatoires.", "error");
      return;
    }

    try {
      await apiRequest(`/api/v1/stocks/${productId}/${action}`, {
        method: "POST",
        body: JSON.stringify({ quantity }),
      });

      setMessage(appMessage, "Stock modifié avec succès.", "success");
      await loadResource("stocks");
    } catch (error) {
      setMessage(appMessage, error.message, "error");
    }
  });

  logoutButton.addEventListener("click", async () => {
    const access = accessToken();
    const refresh = refreshToken();

    try {
      if (access) {
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${access}`,
          },
        });
      }

      if (refresh) {
        await fetch("/api/v1/auth/logout/refresh", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${refresh}`,
          },
        });
      }
    } finally {
      clearTokens();
      showLogin("Vous êtes déconnecté.");
    }
  });

  restoreSession();
})();
