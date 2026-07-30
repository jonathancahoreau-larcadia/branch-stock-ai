(() => {
  "use strict";

  const ACCESS_KEY = "hbntory_access_token";
  const REFRESH_KEY = "hbntory_refresh_token";
  const SENSITIVE_FIELDS = new Set([
    "access_token",
    "refresh_token",
    "password",
    "password_hash",
    "new_password",
    "token_version",
  ]);

  const loginPanel = document.querySelector("#login-panel");
  const application = document.querySelector("#application");
  const loginForm = document.querySelector("#login-form");
  const loginMessage = document.querySelector("#login-message");
  const appMessage = document.querySelector("#app-message");
  const currentUser = document.querySelector("#current-user");
  const content = document.querySelector("#content");
  const workspace = document.querySelector(".workspace");
  const viewTitle = document.querySelector("#view-title");
  const resourceSummary = document.querySelector("#resource-summary");
  const refreshButton = document.querySelector("#refresh-button");
  const logoutButton = document.querySelector("#logout-button");

  const panels = {
    branches: document.querySelector("#branches-panel"),
    products: document.querySelector("#products-panel"),
    stocks: document.querySelector("#stocks-panel"),
    users: document.querySelector("#users-panel"),
  };

  const forms = {
    branchDetail: document.querySelector("#branch-detail-form"),
    productDetail: document.querySelector("#product-detail-form"),
    usersFilter: document.querySelector("#users-filter-form"),
    userCreate: document.querySelector("#user-create-form"),
    userDetail: document.querySelector("#user-detail-form"),
    userEdit: document.querySelector("#user-edit-form"),
    userPassword: document.querySelector("#user-password-form"),
    userDelete: document.querySelector("#user-delete-form"),
    stockFilter: document.querySelector("#stock-filter-form"),
    stockDetail: document.querySelector("#stock-detail-form"),
    stockOperation: document.querySelector("#stock-operation-form"),
  };

  const resourceLabels = {
    dashboard: "Tableau de bord",
    branches: "Succursales",
    products: "Produits",
    stocks: "Stocks",
    users: "Utilisateurs",
  };

  const ROLE_RESOURCES = {
    admin: new Set(["dashboard", "branches", "products", "users"]),
    common_user: new Set(["dashboard", "branches", "products", "stocks"]),
  };

  const pendingSignatures = new WeakMap();
  let currentRole = null;
  let activeResource = "dashboard";
  let logoutPending = false;

  function setMessage(element, text, kind = "") {
    element.textContent = text;
    element.className = `message ${kind}`.trim();
  }

  function setLoading(loading, text = "Chargement…") {
    workspace.setAttribute("aria-busy", loading ? "true" : "false");
    if (loading) {
      setMessage(appMessage, text);
    }
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
      clearTokens();
      return false;
    }

    try {
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
    } catch {
      clearTokens();
      return false;
    }
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

    if (response.status === 401 && retry) {
      if (await refreshAccessToken()) {
        return apiRequest(path, options, false);
      }
    }

    const payload = await parseJsonResponse(response);

    if (!response.ok) {
      if (response.status === 401) {
        clearTokens();
      }
      const message =
        payload?.error?.message ??
        payload?.message ??
        `Erreur HTTP ${response.status}`;
      throw new Error(message);
    }

    return payload;
  }

  function canAccessResource(resource) {
    return ROLE_RESOURCES[currentRole]?.has(resource) ?? false;
  }

  function applyRoleNavigation(role) {
    document.querySelectorAll("[data-resource]").forEach((button) => {
      button.hidden = !(ROLE_RESOURCES[role]?.has(button.dataset.resource) ?? false);
    });

    Object.entries(panels).forEach(([resource, panel]) => {
      panel.hidden = !(ROLE_RESOURCES[role]?.has(resource) ?? false);
    });
  }

  function safeRecord(value) {
    if (Array.isArray(value)) {
      return value.map(safeRecord);
    }
    if (!value || typeof value !== "object") {
      return value;
    }

    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !SENSITIVE_FIELDS.has(key))
        .map(([key, item]) => [key, safeRecord(item)])
    );
  }

  function extractRows(payload) {
    const data = payload?.data ?? payload;

    if (Array.isArray(data)) {
      return data.map(safeRecord);
    }
    if (data && typeof data === "object") {
      for (const key of ["items", "results", "branches", "products", "stocks", "users"]) {
        if (Array.isArray(data[key])) {
          return data[key].map(safeRecord);
        }
      }
      return [safeRecord(data)];
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

  function positiveInteger(formData, name, label) {
    const raw = String(formData.get(name) ?? "").trim();
    const value = Number(raw);
    if (!raw || !Number.isInteger(value) || value < 1) {
      throw new Error(`${label} doit être un entier strictement positif.`);
    }
    return value;
  }

  function requiredText(formData, name, label) {
    const value = String(formData.get(name) ?? "").trim();
    if (!value) {
      throw new Error(`${label} est obligatoire.`);
    }
    return value;
  }

  function formSignature(form) {
    return Array.from(form.querySelectorAll("[name]"))
      .map((field) => `${field.name}:${field.value}`)
      .join("|");
  }

  function setFormDisabled(form, disabled) {
    form.querySelectorAll('button, input[type="submit"]').forEach((control) => {
      control.disabled = disabled;
    });
  }

  async function submitOnce(form, task, loadingText = "Traitement en cours…") {
    const signature = formSignature(form);
    let signatures = pendingSignatures.get(form);
    if (!signatures) {
      signatures = new Set();
      pendingSignatures.set(form, signatures);
    }
    if (signatures.has(signature)) {
      return false;
    }

    signatures.add(signature);
    setFormDisabled(form, true);
    setLoading(true, loadingText);

    try {
      await task();
      return true;
    } catch (error) {
      setMessage(appMessage, error.message, "error");
      if (!accessToken()) {
        showLogin("Votre session a expiré. Reconnectez-vous.");
      }
      return false;
    } finally {
      signatures.delete(signature);
      if (!signatures.size) {
        setFormDisabled(form, false);
        setLoading(false);
      }
    }
  }

  function usersQuery() {
    const data = new FormData(forms.usersFilter);
    const status = ["active", "deleted", "all"].includes(data.get("status"))
      ? data.get("status")
      : "active";
    const query = new URLSearchParams({ status });
    const branchId = String(data.get("branch_id") ?? "").trim();

    if (branchId) {
      const value = Number(branchId);
      if (!Number.isInteger(value) || value < 1) {
        throw new Error("L’identifiant de succursale doit être un entier positif.");
      }
      query.set("branch_id", String(value));
    }
    return query;
  }

  function stockAvailability(form = forms.stockFilter) {
    const value = new FormData(form).get("available_only");
    return value === "false" ? "false" : "true";
  }

  async function loadUsers() {
    const payload = await apiRequest(`/api/v1/users?${usersQuery().toString()}`);
    const count = payload?.meta?.count ?? extractRows(payload).length;
    resourceSummary.textContent = `${count} utilisateur(s) reçu(s).`;
    renderRows(extractRows(payload));
  }

  async function loadStocks(availableOnly = stockAvailability()) {
    const payload = await apiRequest(
      `/api/v1/stocks?available_only=${availableOnly}`
    );
    const data = payload?.data ?? payload;
    const branch = data?.branch;
    const branchName = branch?.name ?? branch?.id ?? branch ?? "non précisée";
    resourceSummary.textContent = `Succursale renvoyée : ${branchName}.`;
    renderRows(extractRows(payload));
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
    resourceSummary.textContent = "";
    setLoading(true);

    try {
      if (resource === "dashboard") {
        const payload = await apiRequest("/api/v1/auth/me");
        renderRows(extractRows(payload));
      } else if (resource === "users") {
        await loadUsers();
      } else if (resource === "stocks") {
        await loadStocks();
      } else {
        const payload = await apiRequest(`/api/v1/${resource}`);
        renderRows(extractRows(payload));
      }
      setMessage(appMessage, "Données chargées.", "success");
    } catch (error) {
      setMessage(appMessage, error.message, "error");
      if (!accessToken()) {
        showLogin("Votre session a expiré. Reconnectez-vous.");
      }
    } finally {
      setLoading(false);
    }
  }

  function showApplication(user) {
    loginPanel.hidden = true;
    application.hidden = false;
    currentRole = user?.role ?? null;
    activeResource = "dashboard";
    applyRoleNavigation(currentRole);

    const branch = user?.branch?.name ?? user?.branch ?? "toutes les succursales";
    const branchId = user?.branch?.id;
    if (branchId) {
      document.querySelector("#users-branch-filter").value = String(branchId);
    }
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
    resourceSummary.textContent = "";
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
    const formData = new FormData(loginForm);
    setFormDisabled(loginForm, true);
    setMessage(loginMessage, "Connexion…");

    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: requiredText(formData, "username", "Le nom d’utilisateur"),
          password: requiredText(formData, "password", "Le mot de passe"),
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
      if (!data.access_token || !data.refresh_token || !data.user) {
        throw new Error("Réponse de connexion incomplète.");
      }
      storeTokens(data);
      loginForm.reset();
      setMessage(loginMessage, "");
      showApplication(data.user);
    } catch (error) {
      clearTokens();
      setMessage(loginMessage, error.message, "error");
    } finally {
      setFormDisabled(loginForm, false);
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

  forms.branchDetail.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.branchDetail, async () => {
      const id = positiveInteger(
        new FormData(forms.branchDetail),
        "branch_id",
        "L’identifiant de succursale"
      );
      const payload = await apiRequest(`/api/v1/branches/${id}`);
      renderRows(extractRows(payload));
      setMessage(appMessage, "Succursale chargée.", "success");
    });
  });

  forms.productDetail.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.productDetail, async () => {
      const id = encodeURIComponent(
        requiredText(
          new FormData(forms.productDetail),
          "external_product_id",
          "L’identifiant produit"
        )
      );
      const payload = await apiRequest(`/api/v1/products/${id}`);
      renderRows(extractRows(payload));
      setMessage(appMessage, "Produit chargé.", "success");
    });
  });

  forms.usersFilter.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.usersFilter, async () => {
      await loadUsers();
      setMessage(appMessage, "Liste des utilisateurs chargée.", "success");
    });
  });

  forms.userCreate.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.userCreate, async () => {
      const data = new FormData(forms.userCreate);
      await apiRequest("/api/v1/users", {
        method: "POST",
        body: JSON.stringify({
          username: requiredText(data, "username", "Le nom d’utilisateur"),
          password: requiredText(data, "password", "Le mot de passe"),
          branch_id: positiveInteger(data, "branch_id", "La succursale"),
        }),
      });
      forms.userCreate.reset();
      await loadUsers();
      setMessage(appMessage, "Utilisateur créé avec succès.", "success");
    });
  });

  forms.userDetail.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.userDetail, async () => {
      const id = positiveInteger(
        new FormData(forms.userDetail),
        "user_id",
        "L’identifiant utilisateur"
      );
      const payload = await apiRequest(`/api/v1/users/${id}`);
      renderRows(extractRows(payload));
      setMessage(appMessage, "Utilisateur chargé.", "success");
    });
  });

  forms.userEdit.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.userEdit, async () => {
      const data = new FormData(forms.userEdit);
      const id = positiveInteger(data, "user_id", "L’identifiant utilisateur");
      const username = String(data.get("username") ?? "").trim();
      const branch = String(data.get("branch_id") ?? "").trim();
      const changes = {};

      if (username) {
        changes.username = username;
      }
      if (branch) {
        changes.branch_id = positiveInteger(data, "branch_id", "La succursale");
      }
      if (!Object.keys(changes).length) {
        throw new Error("Renseignez au moins un champ à modifier.");
      }

      await apiRequest(`/api/v1/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify(changes),
      });
      forms.userEdit.reset();
      await loadUsers();
      setMessage(appMessage, "Utilisateur modifié avec succès.", "success");
    });
  });

  forms.userPassword.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.userPassword, async () => {
      const data = new FormData(forms.userPassword);
      const id = positiveInteger(data, "user_id", "L’identifiant utilisateur");
      await apiRequest(`/api/v1/users/${id}/password`, {
        method: "PATCH",
        body: JSON.stringify({
          new_password: requiredText(
            data,
            "new_password",
            "Le nouveau mot de passe"
          ),
        }),
      });
      forms.userPassword.reset();
      await loadUsers();
      setMessage(appMessage, "Mot de passe modifié avec succès.", "success");
    });
  });

  forms.userDelete.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(forms.userDelete);
    let id;

    try {
      id = positiveInteger(data, "user_id", "L’identifiant utilisateur");
    } catch (error) {
      setMessage(appMessage, error.message, "error");
      return;
    }

    if (!confirm(`Confirmer la suppression logique de l’utilisateur ${id} ?`)) {
      setMessage(appMessage, "Suppression annulée.");
      return;
    }

    await submitOnce(forms.userDelete, async () => {
      await apiRequest(`/api/v1/users/${id}`, { method: "DELETE" });
      forms.userDelete.reset();
      await loadUsers();
      setMessage(appMessage, "Utilisateur supprimé logiquement.", "success");
    });
  });

  forms.stockFilter.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.stockFilter, async () => {
      await loadStocks(stockAvailability(forms.stockFilter));
      setMessage(appMessage, "Stock chargé.", "success");
    });
  });

  forms.stockDetail.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitOnce(forms.stockDetail, async () => {
      const id = encodeURIComponent(
        requiredText(
          new FormData(forms.stockDetail),
          "external_product_id",
          "L’identifiant produit"
        )
      );
      const payload = await apiRequest(`/api/v1/stocks/${id}`);
      const data = payload?.data ?? payload;
      const branch = data?.branch;
      if (branch) {
        resourceSummary.textContent =
          `Succursale renvoyée : ${branch.name ?? branch.id ?? branch}.`;
      }
      renderRows(extractRows(payload));
      setMessage(appMessage, "Ligne de stock chargée.", "success");
    });
  });

  document
    .querySelector("#movement-available-only")
    .addEventListener("change", async () => {
      setLoading(true);
      try {
        await loadStocks(stockAvailability(forms.stockOperation));
        setMessage(appMessage, "Stock chargé.", "success");
      } catch (error) {
        setMessage(appMessage, error.message, "error");
        if (!accessToken()) {
          showLogin("Votre session a expiré. Reconnectez-vous.");
        }
      } finally {
        setLoading(false);
      }
    });

  forms.stockOperation.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canAccessResource("stocks")) {
      setMessage(
        appMessage,
        "Les opérations de stock ne sont pas autorisées pour votre rôle.",
        "error"
      );
      return;
    }
    const data = new FormData(forms.stockOperation);
    let productId;
    let quantity;

    try {
      productId = encodeURIComponent(
        requiredText(data, "product_id", "L’identifiant produit")
      );
      quantity = positiveInteger(data, "quantity", "La quantité");
    } catch (error) {
      setMessage(appMessage, error.message, "error");
      return;
    }

    const action = data.get("action") === "remove" ? "remove" : "add";
    const availableOnly = data.get("available_only") === "false" ? "false" : "true";

    await submitOnce(forms.stockOperation, async () => {
      await apiRequest(`/api/v1/stocks/${productId}/${action}`, {
        method: "POST",
        body: JSON.stringify({ quantity }),
      });
      forms.stockOperation.reset();
      await loadStocks(availableOnly);
      setMessage(appMessage, "Stock modifié avec succès.", "success");
    });
  });

  logoutButton.addEventListener("click", async () => {
    if (logoutPending) {
      return;
    }

    logoutPending = true;
    logoutButton.disabled = true;
    setLoading(true, "Déconnexion en cours…");

    const access = accessToken();
    const refresh = refreshToken();
    const revocations = [];

    if (access) {
      revocations.push(
        fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: { Authorization: `Bearer ${access}` },
        })
      );
    }
    if (refresh) {
      revocations.push(
        fetch("/api/v1/auth/logout/refresh", {
          method: "POST",
          headers: { Authorization: `Bearer ${refresh}` },
        })
      );
    }

    try {
      await Promise.allSettled(revocations);
    } finally {
      clearTokens();
      logoutPending = false;
      logoutButton.disabled = false;
      setLoading(false);
      showLogin("Vous êtes déconnecté.");
    }
  });

  restoreSession();
})();
