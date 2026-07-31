(() => {
  "use strict";

  const ACCESS_KEY = "hbntory_access_token";
  const REFRESH_KEY = "hbntory_refresh_token";
  const PRODUCT_PAGE_SIZE = 10;
  const ROLE_VIEWS = Object.freeze({
    admin: new Set(["dashboard", "branches", "products", "users"]),
    common_user: new Set(["dashboard", "branches", "products", "stocks"]),
  });
  const VIEW_LABELS = Object.freeze({
    dashboard: "Tableau de bord",
    branches: "Succursales",
    products: "Produits",
    stocks: "Stocks",
    users: "Utilisateurs",
  });
  const ERROR_MESSAGES = Object.freeze({
    INVALID_JSON: "La requête envoyée n’a pas pu être lue.",
    VALIDATION_ERROR: "Certaines informations saisies ne sont pas valides.",
    AUTHENTICATION_REQUIRED: "Votre session doit être renouvelée.",
    INVALID_CREDENTIALS: "Nom d’utilisateur ou mot de passe incorrect.",
    TOKEN_INVALID: "Votre session n’est plus valide.",
    TOKEN_EXPIRED: "Votre session a expiré.",
    TOKEN_REVOKED: "Votre session a été révoquée.",
    WRONG_TOKEN_TYPE: "Votre session n’est pas autorisée pour cette action.",
    TOKEN_VERSION_INVALID: "Votre session n’est plus valide.",
    ACCOUNT_INACTIVE: "Ce compte est inactif.",
    FORBIDDEN: "Vous n’êtes pas autorisé à effectuer cette action.",
    BRANCH_ACCESS_FORBIDDEN: "Vous ne pouvez pas consulter cette succursale.",
    ADMIN_STOCK_FORBIDDEN: "Un administrateur ne peut pas gérer le stock.",
    USER_NOT_FOUND: "Cet utilisateur est introuvable.",
    BRANCH_NOT_FOUND: "Cette succursale est introuvable.",
    PRODUCT_NOT_FOUND: "Ce produit est introuvable.",
    PRODUCT_API_TIMEOUT: "Le catalogue produits met trop de temps à répondre.",
    PRODUCT_API_UNAVAILABLE: "Le catalogue produits est temporairement indisponible.",
    PRODUCT_API_INVALID_RESPONSE: "Le catalogue produits a renvoyé une réponse inexploitable.",
    STOCK_NOT_FOUND: "Cette ligne de stock est introuvable.",
    STOCK_CONFLICT: "Le stock a changé simultanément. Actualisez puis réessayez.",
    INVALID_QUANTITY: "La quantité doit être un entier strictement positif.",
    INSUFFICIENT_STOCK: "La quantité disponible est insuffisante pour ce retrait.",
    USERNAME_ALREADY_EXISTS: "Ce nom d’utilisateur est déjà utilisé.",
    RESERVED_USERNAME: "Ce nom d’utilisateur est réservé.",
    INTERNAL_ERROR: "Le service a rencontré une erreur inattendue.",
    NETWORK_ERROR: "Le service est injoignable. Vérifiez votre connexion puis réessayez.",
    INVALID_RESPONSE: "Le service a renvoyé une réponse inexploitable.",
    SESSION_EXPIRED: "Votre session a expiré. Reconnectez-vous.",
  });
  const CATEGORY_TRANSLATIONS = Object.freeze({
    Displays: "Écrans",
    displays: "Écrans",
    Monitors: "Écrans",
    monitors: "Écrans",
    Keyboards: "Claviers",
    keyboards: "Claviers",
  });
  const NAME_TRANSLATIONS = Object.freeze({
    "24 inch Compact Monitor": "Écran compact 24 pouces",
    "Compact Monitor": "Écran compact",
  });
  const DESCRIPTION_TRANSLATIONS = Object.freeze({
    "A compact display.": "Un écran compact.",
    "A compact business display.": "Un écran compact pour un usage professionnel.",
    "Compact business monitor": "Écran compact pour un usage professionnel",
  });

  class PublicError extends Error {
    constructor(code, status = 0) {
      super(ERROR_MESSAGES[code] ?? ERROR_MESSAGES.INTERNAL_ERROR);
      this.name = "PublicError";
      this.code = code;
      this.status = status;
    }
  }

  const dom = {
    loginPanel: document.querySelector("#login-panel"),
    loginForm: document.querySelector("#login-form"),
    loginMessage: document.querySelector("#login-message"),
    password: document.querySelector("#password"),
    passwordToggle: document.querySelector("#password-toggle"),
    application: document.querySelector("#application"),
    workspace: document.querySelector("#workspace"),
    viewTitle: document.querySelector("#view-title"),
    breadcrumbView: document.querySelector("#breadcrumb-view"),
    accountName: document.querySelector("#account-name"),
    accountContext: document.querySelector("#account-context"),
    accountAvatar: document.querySelector("#account-avatar"),
    logoutButton: document.querySelector("#logout-button"),
    appMessage: document.querySelector("#app-message"),
    dashboardGreeting: document.querySelector("#dashboard-greeting"),
    dashboardIntro: document.querySelector("#dashboard-intro"),
    dashboardContent: document.querySelector("#dashboard-content"),
    localDate: document.querySelector("#local-date"),
    branchesContent: document.querySelector("#branches-content"),
    branchesSummary: document.querySelector("#branches-summary"),
    branchSearch: document.querySelector("#branch-search"),
    productsContent: document.querySelector("#products-content"),
    productsSummary: document.querySelector("#products-summary"),
    productsForm: document.querySelector("#products-filter-form"),
    productSearch: document.querySelector("#product-search"),
    productSort: document.querySelector("#product-sort"),
    productsPagination: document.querySelector("#products-pagination"),
    stocksContent: document.querySelector("#stocks-content"),
    stocksSummary: document.querySelector("#stocks-summary"),
    stockBranchName: document.querySelector("#stock-branch-name"),
    stockSearch: document.querySelector("#stock-search"),
    stockCreateButton: document.querySelector("#stock-create-button"),
    usersContent: document.querySelector("#users-content"),
    usersSummary: document.querySelector("#users-summary"),
    usersForm: document.querySelector("#users-filter-form"),
    userSearch: document.querySelector("#user-search"),
    usersStatus: document.querySelector("#users-status"),
    usersBranch: document.querySelector("#users-branch-filter"),
    userKpis: document.querySelector("#user-kpis"),
    userCreateButton: document.querySelector("#user-create-button"),
    drawer: document.querySelector("#detail-drawer"),
    drawerOverlay: document.querySelector("#drawer-overlay"),
    drawerClose: document.querySelector("#drawer-close"),
    drawerEyebrow: document.querySelector("#drawer-eyebrow"),
    drawerTitle: document.querySelector("#drawer-title"),
    drawerContent: document.querySelector("#drawer-content"),
    modal: document.querySelector("#action-modal"),
    modalOverlay: document.querySelector("#modal-overlay"),
    modalClose: document.querySelector("#modal-close"),
    modalEyebrow: document.querySelector("#modal-eyebrow"),
    modalTitle: document.querySelector("#modal-title"),
    modalDescription: document.querySelector("#modal-description"),
    modalContent: document.querySelector("#modal-content"),
    toastRegion: document.querySelector("#toast-region"),
    sidebar: document.querySelector("#sidebar"),
    sidebarOpen: document.querySelector("#sidebar-open"),
    sidebarClose: document.querySelector("#sidebar-close"),
    sidebarOverlay: document.querySelector("#sidebar-overlay"),
  };

  const state = {
    user: null,
    activeView: "dashboard",
    branches: [],
    products: [],
    productMeta: {total: 0, limit: PRODUCT_PAGE_SIZE, offset: 0},
    productQuery: {q: "", sort: "name"},
    stocks: [],
    stockBranch: null,
    stockFilter: "all",
    users: [],
    allUsers: null,
    userStatus: "active",
    userBranch: "",
    drawerTrigger: null,
    modalTrigger: null,
  };

  const pendingForms = new WeakSet();
  let refreshPromise = null;
  let logoutPending = false;
  let branchSearchTimer = null;
  let productSearchTimer = null;
  let stockSearchTimer = null;
  let userSearchTimer = null;

  function createElement(tagName, className = "", text) {
    const element = document.createElement(tagName);
    if (className) {
      element.className = className;
    }
    if (text !== undefined) {
      element.textContent = String(text);
    }
    return element;
  }

  function createButton(label, className, onClick) {
    const button = createElement("button", className, label);
    button.type = "button";
    if (onClick) {
      button.addEventListener("click", onClick);
    }
    return button;
  }

  function hasOwn(record, key) {
    return Object.prototype.hasOwnProperty.call(record, key);
  }

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function translated(dictionary, value) {
    return typeof value === "string" && hasOwn(dictionary, value)
      ? dictionary[value]
      : value;
  }

  function displayProduct(product) {
    if (!isRecord(product)) {
      return {};
    }
    return {
      ...product,
      name: translated(NAME_TRANSLATIONS, product.name),
      description: translated(DESCRIPTION_TRANSLATIONS, product.description),
      category: translated(CATEGORY_TRANSLATIONS, product.category),
      supplier: isRecord(product.supplier) ? {...product.supplier} : product.supplier,
      tags: Array.isArray(product.tags) ? [...product.tags] : product.tags,
    };
  }

  function displayRole(role) {
    return role === "admin" ? "Administrateur" : role === "common_user"
      ? "Common user"
      : "Rôle inconnu";
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    if (typeof value === "boolean") {
      return value ? "Oui" : "Non";
    }
    if (Array.isArray(value)) {
      return value.length ? value.join(", ") : "—";
    }
    return String(value);
  }

  function formatPrice(value, currency) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || typeof currency !== "string") {
      return `${displayValue(value)} ${displayValue(currency)}`.trim();
    }
    try {
      return new Intl.NumberFormat("fr-FR", {
        style: "currency",
        currency,
      }).format(amount);
    } catch {
      return `${value} ${currency}`;
    }
  }

  function formatDate(value) {
    if (!value) {
      return "—";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return new Intl.DateTimeFormat("fr-FR", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  function publicMessage(error) {
    return error instanceof PublicError
      ? error.message
      : ERROR_MESSAGES.INTERNAL_ERROR;
  }

  function setAnnouncement(message, kind = "status") {
    dom.appMessage.textContent = message;
    dom.appMessage.setAttribute("role", kind === "error" ? "alert" : "status");
  }

  function showToast(title, message, kind = "success") {
    setAnnouncement(message || title, kind === "error" ? "error" : "status");
    const toast = createElement("div", `toast toast-${kind}`);
    toast.setAttribute("role", kind === "error" ? "alert" : "status");
    const symbol = createElement(
      "span",
      "toast-symbol",
      kind === "error" ? "!" : "✓"
    );
    symbol.setAttribute("aria-hidden", "true");
    const copy = createElement("div");
    copy.append(
      createElement("strong", "", title),
      createElement("span", "", message)
    );
    toast.append(symbol, copy);
    dom.toastRegion.append(toast);
    window.setTimeout(() => {
      if (typeof toast.remove === "function") {
        toast.remove();
      }
    }, 5200);
  }

  function setWorkspaceLoading(loading) {
    dom.workspace.setAttribute("aria-busy", loading ? "true" : "false");
  }

  function renderSkeleton(container, rows = 5) {
    const skeleton = createElement("div", "skeleton-table");
    skeleton.setAttribute("aria-label", "Chargement en cours");
    for (let index = 0; index < rows; index += 1) {
      skeleton.append(createElement("div", "skeleton-row"));
    }
    container.replaceChildren(skeleton);
  }

  function renderEmpty(container, title, message) {
    const stateElement = createElement("div", "empty-state");
    const inner = createElement("div", "state-inner");
    inner.append(
      createElement("div", "state-icon", "—"),
      createElement("h3", "", title),
      createElement("p", "", message)
    );
    stateElement.append(inner);
    container.replaceChildren(stateElement);
  }

  function renderError(container, error, retry) {
    const stateElement = createElement("div", "error-state");
    const inner = createElement("div", "state-inner");
    inner.append(
      createElement("div", "state-icon", "!"),
      createElement("h3", "", "Impossible de charger les données"),
      createElement("p", "", publicMessage(error))
    );
    if (retry) {
      const button = createButton("Réessayer", "button-secondary", retry);
      inner.append(button);
    }
    stateElement.append(inner);
    container.replaceChildren(stateElement);
    setAnnouncement(publicMessage(error), "error");
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

  async function parseResponse(response) {
    const text = await response.text();
    if (!text) {
      return {};
    }
    try {
      return JSON.parse(text);
    } catch {
      throw new PublicError("INVALID_RESPONSE", response.status);
    }
  }

  function errorFromResponse(response, payload) {
    const code = isRecord(payload?.error) && typeof payload.error.code === "string"
      ? payload.error.code
      : null;
    if (code && hasOwn(ERROR_MESSAGES, code)) {
      return new PublicError(code, response.status);
    }
    if (response.status === 401) {
      return new PublicError("SESSION_EXPIRED", response.status);
    }
    if (response.status === 403) {
      return new PublicError("FORBIDDEN", response.status);
    }
    if (response.status >= 500) {
      return new PublicError("INTERNAL_ERROR", response.status);
    }
    return new PublicError("VALIDATION_ERROR", response.status);
  }

  async function refreshAccessToken() {
    if (refreshPromise) {
      return refreshPromise;
    }

    refreshPromise = (async () => {
      const token = refreshToken();
      if (!token) {
        clearTokens();
        return false;
      }
      try {
        const response = await fetch("/api/v1/auth/refresh", {
          method: "POST",
          headers: {Authorization: `Bearer ${token}`},
        });
        if (!response.ok) {
          clearTokens();
          return false;
        }
        const payload = await parseResponse(response);
        const data = payload.data ?? payload;
        if (!isRecord(data) || typeof data.access_token !== "string") {
          clearTokens();
          return false;
        }
        sessionStorage.setItem(ACCESS_KEY, data.access_token);
        if (typeof data.refresh_token === "string") {
          sessionStorage.setItem(REFRESH_KEY, data.refresh_token);
        }
        return true;
      } catch {
        clearTokens();
        return false;
      }
    })();

    try {
      return await refreshPromise;
    } finally {
      refreshPromise = null;
    }
  }

  async function apiRequest(path, options = {}, allowRefresh = true) {
    const headers = new Headers(options.headers ?? {});
    const token = accessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    let response;
    try {
      response = await fetch(path, {...options, headers});
    } catch {
      throw new PublicError("NETWORK_ERROR");
    }

    if (response.status === 401 && allowRefresh) {
      if (await refreshAccessToken()) {
        return apiRequest(path, options, false);
      }
      throw new PublicError("SESSION_EXPIRED", 401);
    }

    const payload = await parseResponse(response);
    if (!response.ok) {
      if (response.status === 401) {
        clearTokens();
      }
      throw errorFromResponse(response, payload);
    }
    return payload;
  }

  function canAccess(view) {
    return ROLE_VIEWS[state.user?.role]?.has(view) ?? false;
  }

  function applyRoleNavigation() {
    document.querySelectorAll("[data-resource]").forEach((button) => {
      const allowed = ROLE_VIEWS[state.user?.role]?.has(button.dataset.resource) ?? false;
      button.hidden = !allowed;
    });
  }

  function closeSidebar() {
    dom.sidebar.classList.remove("sidebar-open");
    dom.sidebarOverlay.hidden = true;
    dom.sidebarOpen.setAttribute("aria-expanded", "false");
  }

  function openSidebar() {
    dom.sidebar.classList.add("sidebar-open");
    dom.sidebarOverlay.hidden = false;
    dom.sidebarOpen.setAttribute("aria-expanded", "true");
  }

  function focusElement(element) {
    if (element && typeof element.focus === "function") {
      element.focus();
    }
  }

  function focusableElements(container) {
    return Array.from(
      container.querySelectorAll("button, input, select, textarea, [tabindex]")
    ).filter(
      (element) =>
        !element.disabled &&
        !element.hidden &&
        String(element.type ?? "").toLowerCase() !== "hidden"
    );
  }

  function trapFocus(event, container) {
    if (event.key !== "Tab") {
      return;
    }
    const focusable = focusableElements(container);
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      focusElement(last);
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      focusElement(first);
    }
  }

  function updateDialogBodyState() {
    const open = !dom.modal.hidden || !dom.drawer.hidden;
    document.body.classList[open ? "add" : "remove"]("dialog-open");
  }

  function openDrawer({eyebrow, title, content, trigger}) {
    closeModal(false);
    state.drawerTrigger = trigger ?? document.activeElement;
    dom.drawerEyebrow.textContent = eyebrow;
    dom.drawerTitle.textContent = title;
    dom.drawerContent.replaceChildren(content);
    dom.drawer.hidden = false;
    dom.drawerOverlay.hidden = false;
    updateDialogBodyState();
    focusElement(dom.drawerClose);
  }

  function closeDrawer(returnFocus = true) {
    if (dom.drawer.hidden) {
      return;
    }
    dom.drawer.hidden = true;
    dom.drawerOverlay.hidden = true;
    dom.drawerContent.replaceChildren();
    updateDialogBodyState();
    if (returnFocus) {
      focusElement(state.drawerTrigger);
    }
    state.drawerTrigger = null;
  }

  function openModal({eyebrow, title, description, content, trigger, initialFocus}) {
    closeDrawer(false);
    state.modalTrigger = trigger ?? document.activeElement;
    dom.modalEyebrow.textContent = eyebrow;
    dom.modalTitle.textContent = title;
    dom.modalDescription.textContent = description;
    dom.modalContent.replaceChildren(content);
    dom.modal.hidden = false;
    dom.modalOverlay.hidden = false;
    updateDialogBodyState();
    const first = initialFocus ?? focusableElements(dom.modal)[0] ?? dom.modalClose;
    focusElement(first);
  }

  function closeModal(returnFocus = true) {
    if (dom.modal.hidden) {
      return;
    }
    dom.modal.hidden = true;
    dom.modalOverlay.hidden = true;
    dom.modalContent.replaceChildren();
    updateDialogBodyState();
    if (returnFocus) {
      focusElement(state.modalTrigger);
    }
    state.modalTrigger = null;
  }

  function detailsContent(sections) {
    const container = createElement("div", "detail-sections");
    sections.forEach((section) => {
      const block = createElement("section", "detail-section");
      block.append(createElement("h3", "", section.title));
      const list = createElement("dl", "detail-list");
      section.items.forEach(([label, value]) => {
        const item = createElement("div", "detail-item");
        item.append(
          createElement("dt", "", label),
          createElement("dd", "", displayValue(value))
        );
        list.append(item);
      });
      block.append(list);
      container.append(block);
    });
    return container;
  }

  function badge(text, kind) {
    return createElement("span", `badge badge-${kind}`, text);
  }

  function cell(title, subtitle = "") {
    const container = createElement("div");
    container.append(createElement("span", "cell-title", displayValue(title)));
    if (subtitle) {
      container.append(createElement("span", "cell-subtitle", subtitle));
    }
    return container;
  }

  function renderTable(container, columns, rows) {
    if (!rows.length) {
      renderEmpty(container, "Aucun résultat", "Aucune donnée ne correspond aux critères actuels.");
      return;
    }
    const scroll = createElement("div", "table-scroll");
    const table = createElement("table", "data-table");
    const head = createElement("thead");
    const headRow = createElement("tr");
    columns.forEach((column) => {
      const header = createElement("th", "", column.label);
      header.scope = "col";
      headRow.append(header);
    });
    head.append(headRow);
    const body = createElement("tbody");
    rows.forEach((row) => {
      const tableRow = createElement("tr");
      columns.forEach((column) => {
        const tableCell = createElement("td");
        const rendered = column.render(row);
        if (rendered && typeof rendered === "object") {
          tableCell.append(rendered);
        } else {
          tableCell.textContent = displayValue(rendered);
        }
        tableRow.append(tableCell);
      });
      body.append(tableRow);
    });
    table.append(head, body);
    scroll.append(table);
    container.replaceChildren(scroll);
  }

  function renderKpi(label, value, note = "") {
    const card = createElement("article", "kpi-card");
    card.append(
      createElement("span", "kpi-label", label),
      createElement("strong", "kpi-value", value),
      createElement("span", "kpi-note", note)
    );
    return card;
  }

  function renderQuickActions(actions) {
    const card = createElement("section", "quick-actions-card");
    card.append(
      createElement("h3", "", "Actions rapides"),
      createElement("p", "muted", "Accédez directement aux fonctions disponibles pour votre rôle.")
    );
    const grid = createElement("div", "quick-actions");
    actions.forEach(([label, view, callback]) => {
      grid.append(createButton(label, "quick-action", callback ?? (() => navigate(view))));
    });
    card.append(grid);
    return card;
  }

  function viewContainer(view) {
    return document.querySelector(`[data-view="${view}"]`);
  }

  async function navigate(view) {
    if (!canAccess(view)) {
      showToast(
        "Accès refusé",
        "Cette vue n’est pas autorisée pour votre rôle.",
        "error"
      );
      return false;
    }
    state.activeView = view;
    document.querySelectorAll("[data-view]").forEach((section) => {
      section.hidden = section.dataset.view !== view;
    });
    document.querySelectorAll("[data-resource]").forEach((button) => {
      if (button.dataset.resource === view) {
        button.setAttribute("aria-current", "page");
      } else {
        button.removeAttribute("aria-current");
      }
    });
    const label = VIEW_LABELS[view];
    dom.viewTitle.textContent = label;
    dom.breadcrumbView.textContent = label;
    closeSidebar();
    await loadView(view);
    return true;
  }

  async function loadView(view) {
    if (!canAccess(view)) {
      return;
    }
    if (view === "dashboard") {
      await loadDashboard();
    } else if (view === "branches") {
      await loadBranches();
    } else if (view === "products") {
      await loadProducts();
    } else if (view === "stocks") {
      await loadStocks();
    } else if (view === "users") {
      await loadUsers();
    }
  }

  async function loadDashboard() {
    renderSkeleton(dom.dashboardContent, 4);
    setWorkspaceLoading(true);
    const username = state.user?.username ?? "utilisateur";
    dom.dashboardGreeting.textContent = `Bonjour ${username}`;
    dom.localDate.textContent = new Intl.DateTimeFormat("fr-FR", {
      dateStyle: "full",
    }).format(new Date());
    try {
      if (state.user?.role === "admin") {
        await loadAdminDashboard();
      } else {
        await loadCommonDashboard();
      }
      setAnnouncement("Tableau de bord chargé.");
    } finally {
      setWorkspaceLoading(false);
    }
  }

  async function loadAdminDashboard() {
    dom.dashboardIntro.textContent = "Suivez les ressources administratives accessibles à votre compte.";
    const results = await Promise.allSettled([
      apiRequest("/api/v1/branches"),
      apiRequest("/api/v1/products?include_discontinued=false&limit=1&offset=0"),
      apiRequest("/api/v1/users?status=all"),
    ]);
    const branchPayload = results[0].status === "fulfilled" ? results[0].value : null;
    const productPayload = results[1].status === "fulfilled" ? results[1].value : null;
    const userPayload = results[2].status === "fulfilled" ? results[2].value : null;
    const allUsers = Array.isArray(userPayload?.data) ? userPayload.data : null;
    if (allUsers) {
      state.allUsers = allUsers.map((user) => ({...user}));
    }
    const commonUsers = allUsers
      ? allUsers.filter((user) => user?.role === "common_user")
      : null;
    const activeUsers = commonUsers
      ? commonUsers.filter((user) => user.is_active === true && !user.deleted_at)
      : null;
    const inactiveUsers = commonUsers
      ? commonUsers.filter((user) => user.is_active !== true || Boolean(user.deleted_at))
      : null;
    const value = (condition, number) => condition ? String(number) : "Indisponible";
    const kpis = createElement("div", "kpi-grid");
    kpis.append(
      renderKpi(
        "Succursales",
        value(branchPayload, branchPayload?.meta?.count ?? branchPayload?.data?.length),
        "Établissements accessibles"
      ),
      renderKpi(
        "Produits",
        value(productPayload, productPayload?.meta?.total),
        "Catalogue externe"
      ),
      renderKpi(
        "Common users actifs",
        value(activeUsers, activeUsers?.length),
        "Comptes opérationnels"
      ),
      renderKpi(
        "Common users supprimés",
        value(inactiveUsers, inactiveUsers?.length),
        "Comptes inactifs ou supprimés"
      )
    );
    dom.dashboardContent.replaceChildren(
      kpis,
      renderQuickActions([
        ["Consulter les succursales", "branches"],
        ["Consulter les produits", "products"],
        ["Gérer les utilisateurs", "users"],
        ["Créer un common user", "users", async () => {
          await navigate("users");
          openUserCreateModal(dom.userCreateButton);
        }],
      ])
    );
  }

  async function loadCommonDashboard() {
    dom.dashboardIntro.textContent = "Consultez le stock réel de la succursale attribuée à votre compte.";
    let payload;
    let failed = false;
    try {
      payload = await apiRequest("/api/v1/stocks?available_only=false");
    } catch {
      failed = true;
    }
    const data = payload?.data;
    const items = Array.isArray(data?.items) ? data.items : [];
    if (!failed) {
      state.stocks = items.map((item) => ({
        ...item,
        product: isRecord(item.product) ? {...item.product} : item.product,
      }));
      state.stockBranch = isRecord(data?.branch) ? {...data.branch} : null;
    }
    const positive = items.filter((item) => Number(item.quantity) > 0);
    const units = items.reduce((total, item) => {
      const quantity = Number(item.quantity);
      return total + (Number.isFinite(quantity) ? quantity : 0);
    }, 0);
    const fallback = failed ? "Indisponible" : null;
    const branchName = state.user?.branch?.name ?? state.user?.branch?.id ?? "Non attribuée";
    const kpis = createElement("div", "kpi-grid");
    kpis.append(
      renderKpi("Succursale assignée", displayValue(branchName), "Périmètre du compte"),
      renderKpi("Lignes de stock", fallback ?? String(items.length), "Lignes incluant les ruptures"),
      renderKpi("Produits disponibles", fallback ?? String(positive.length), "Quantité strictement positive"),
      renderKpi("Unités en stock", fallback ?? String(units), "Somme des quantités")
    );
    dom.dashboardContent.replaceChildren(
      kpis,
      renderQuickActions([
        ["Consulter le stock", "stocks"],
        ["Parcourir les produits", "products"],
        ["Voir ma succursale", "branches"],
      ])
    );
  }

  async function loadBranches() {
    renderSkeleton(dom.branchesContent);
    dom.branchesSummary.textContent = "Chargement…";
    setWorkspaceLoading(true);
    try {
      const payload = await apiRequest("/api/v1/branches");
      state.branches = Array.isArray(payload?.data)
        ? payload.data.map((branch) => ({...branch}))
        : [];
      renderBranches();
      setAnnouncement("Succursales chargées.");
    } catch (error) {
      dom.branchesSummary.textContent = "";
      renderError(dom.branchesContent, error, loadBranches);
      handleSessionError(error);
    } finally {
      setWorkspaceLoading(false);
    }
  }

  function renderBranches() {
    const query = dom.branchSearch.value.trim().toLocaleLowerCase("fr-FR");
    const filtered = state.branches.filter((branch) => {
      const haystack = `${branch.id ?? ""} ${branch.name ?? ""}`.toLocaleLowerCase("fr-FR");
      return !query || haystack.includes(query);
    });
    dom.branchesSummary.textContent =
      `${filtered.length} succursale${filtered.length > 1 ? "s" : ""} affichée${filtered.length > 1 ? "s" : ""}`;
    renderTable(dom.branchesContent, [
      {label: "Identifiant", render: (branch) => branch.id},
      {label: "Nom", render: (branch) => cell(branch.name, `Succursale n° ${branch.id}`)},
      {
        label: "Actions",
        render: (branch) => {
          const actions = createElement("div", "table-actions");
          actions.append(
            createButton("Consulter", "table-action", (event) => {
              loadBranchDetail(branch.id, event.currentTarget);
            })
          );
          return actions;
        },
      },
    ], filtered);
  }

  async function loadBranchDetail(branchId, trigger) {
    try {
      const payload = await apiRequest(`/api/v1/branches/${branchId}`);
      const branch = payload?.data;
      if (!isRecord(branch)) {
        throw new PublicError("INVALID_RESPONSE");
      }
      openDrawer({
        eyebrow: "Succursale",
        title: displayValue(branch.name),
        trigger,
        content: detailsContent([
          {title: "Informations", items: [
            ["Identifiant", branch.id],
            ["Nom", branch.name],
          ]},
        ]),
      });
    } catch (error) {
      showToast("Consultation impossible", publicMessage(error), "error");
      handleSessionError(error);
    }
  }

  function productParameters() {
    const query = new URLSearchParams({
      include_discontinued: "false",
      limit: String(PRODUCT_PAGE_SIZE),
      offset: String(state.productMeta.offset),
      sort: state.productQuery.sort,
    });
    if (state.productQuery.q) {
      query.set("q", state.productQuery.q);
    }
    return query;
  }

  async function loadProducts() {
    renderSkeleton(dom.productsContent);
    dom.productsSummary.textContent = "Chargement…";
    dom.productsPagination.replaceChildren();
    setWorkspaceLoading(true);
    try {
      const payload = await apiRequest(`/api/v1/products?${productParameters().toString()}`);
      state.products = Array.isArray(payload?.data)
        ? payload.data.map((product) => ({...product}))
        : [];
      state.productMeta = {
        total: Number(payload?.meta?.total) || 0,
        limit: Number(payload?.meta?.limit) || PRODUCT_PAGE_SIZE,
        offset: Number(payload?.meta?.offset) || 0,
      };
      renderProducts();
      setAnnouncement("Produits chargés.");
    } catch (error) {
      dom.productsSummary.textContent = "";
      renderError(dom.productsContent, error, loadProducts);
      handleSessionError(error);
    } finally {
      setWorkspaceLoading(false);
    }
  }

  function renderProducts() {
    const displayed = state.products.map(displayProduct);
    const start = state.productMeta.total ? state.productMeta.offset + 1 : 0;
    const end = Math.min(
      state.productMeta.offset + state.products.length,
      state.productMeta.total
    );
    dom.productsSummary.textContent =
      `${state.productMeta.total} résultat${state.productMeta.total > 1 ? "s" : ""} · ${start}–${end} affiché${end - start > 0 ? "s" : ""}`;
    renderTable(dom.productsContent, [
      {
        label: "SKU / identifiant externe",
        render: (product) => cell(product.external_product_id),
      },
      {
        label: "Produit",
        render: (product) => cell(product.name, displayValue(product.brand)),
      },
      {label: "Catégorie", render: (product) => product.category},
      {
        label: "Prix",
        render: (product) => formatPrice(product.unit_price, product.currency),
      },
      {
        label: "Statut",
        render: (product) => product.discontinued
          ? badge("Arrêté", "warning")
          : badge("Actif", "success"),
      },
      {
        label: "Actions",
        render: (product) => {
          const actions = createElement("div", "table-actions");
          actions.append(
            createButton("Consulter", "table-action", (event) => {
              loadProductDetail(product.external_product_id, event.currentTarget);
            })
          );
          return actions;
        },
      },
    ], displayed);
    renderProductPagination();
  }

  function renderProductPagination() {
    dom.productsPagination.replaceChildren();
    const previous = createButton("Précédent", "", async () => {
      state.productMeta.offset = Math.max(0, state.productMeta.offset - state.productMeta.limit);
      await loadProducts();
    });
    previous.disabled = state.productMeta.offset <= 0;
    const next = createButton("Suivant", "", async () => {
      state.productMeta.offset += state.productMeta.limit;
      await loadProducts();
    });
    next.disabled =
      state.productMeta.offset + state.productMeta.limit >= state.productMeta.total;
    const currentPage = Math.floor(state.productMeta.offset / state.productMeta.limit) + 1;
    const pageCount = Math.max(1, Math.ceil(state.productMeta.total / state.productMeta.limit));
    const status = createElement(
      "span",
      "pagination-status",
      `Page ${currentPage} sur ${pageCount}`
    );
    dom.productsPagination.append(previous, status, next);
  }

  async function loadProductDetail(productId, trigger) {
    const identifier = encodeURIComponent(String(productId));
    try {
      const payload = await apiRequest(`/api/v1/products/${identifier}`);
      if (!isRecord(payload?.data)) {
        throw new PublicError("INVALID_RESPONSE");
      }
      const product = displayProduct(payload.data);
      const supplier = isRecord(product.supplier) ? product.supplier : {};
      openDrawer({
        eyebrow: "Produit",
        title: displayValue(product.name),
        trigger,
        content: detailsContent([
          {title: "Catalogue", items: [
            ["SKU / identifiant externe", product.external_product_id],
            ["Nom", product.name],
            ["Description", product.description],
            ["Catégorie", product.category],
            ["Marque", product.brand],
            ["Prix", formatPrice(product.unit_price, product.currency)],
            ["Statut", product.discontinued ? "Arrêté" : "Actif"],
            ["Poids", product.weight_kg === undefined ? null : `${product.weight_kg} kg`],
            ["Tags", product.tags],
            ["Dernière mise à jour", formatDate(product.updated_at)],
          ]},
          {title: "Fournisseur public", items: [
            ["Identifiant", supplier.id],
            ["Nom", supplier.name],
            ["Pays", supplier.country],
            ["Délai", supplier.lead_time_days === undefined ? null : `${supplier.lead_time_days} jours`],
            ["Fiabilité", supplier.reliability_score],
          ]},
        ]),
      });
    } catch (error) {
      showToast("Produit indisponible", publicMessage(error), "error");
      handleSessionError(error);
    }
  }

  async function loadStocks() {
    if (!canAccess("stocks")) {
      return;
    }
    renderSkeleton(dom.stocksContent);
    dom.stocksSummary.textContent = "Chargement…";
    setWorkspaceLoading(true);
    try {
      const payload = await apiRequest("/api/v1/stocks?available_only=false");
      const data = payload?.data;
      if (!isRecord(data) || !Array.isArray(data.items)) {
        throw new PublicError("INVALID_RESPONSE");
      }
      state.stockBranch = isRecord(data.branch) ? {...data.branch} : null;
      state.stocks = data.items.map((item) => ({
        ...item,
        product: isRecord(item.product) ? {...item.product} : item.product,
      }));
      dom.stockBranchName.textContent =
        `Succursale assignée : ${displayValue(state.stockBranch?.name ?? state.stockBranch?.id)}`;
      renderStocks();
      setAnnouncement("Stock chargé.");
    } catch (error) {
      dom.stocksSummary.textContent = "";
      renderError(dom.stocksContent, error, loadStocks);
      handleSessionError(error);
    } finally {
      setWorkspaceLoading(false);
    }
  }

  function filteredStocks() {
    const query = dom.stockSearch.value.trim().toLocaleLowerCase("fr-FR");
    return state.stocks.filter((item) => {
      const quantity = Number(item.quantity);
      const filterMatches =
        state.stockFilter === "all" ||
        (state.stockFilter === "available" && quantity > 0) ||
        (state.stockFilter === "empty" && quantity === 0);
      const translatedName = translated(NAME_TRANSLATIONS, item.product?.name);
      const haystack =
        `${item.external_product_id ?? ""} ${translatedName ?? ""}`.toLocaleLowerCase("fr-FR");
      return filterMatches && (!query || haystack.includes(query));
    });
  }

  function renderStocks() {
    const items = filteredStocks();
    dom.stocksSummary.textContent =
      `${items.length} ligne${items.length > 1 ? "s" : ""} affichée${items.length > 1 ? "s" : ""}`;
    renderTable(dom.stocksContent, [
      {
        label: "Produit",
        render: (item) => cell(
          translated(NAME_TRANSLATIONS, item.product?.name),
          item.external_product_id
        ),
      },
      {label: "Quantité", render: (item) => item.quantity},
      {
        label: "Disponibilité",
        render: (item) => Number(item.quantity) > 0
          ? badge("Disponible", "success")
          : badge("Rupture", "danger"),
      },
      {
        label: "Actions",
        render: (item) => {
          const actions = createElement("div", "table-actions");
          actions.append(
            createButton("Détail", "table-action", (event) => {
              loadStockDetail(item.external_product_id, event.currentTarget);
            }),
            createButton("Ajouter", "table-action", (event) => {
              openStockModal("add", item, event.currentTarget);
            }),
            createButton("Retirer", "table-action table-action-danger", (event) => {
              openStockModal("remove", item, event.currentTarget);
            })
          );
          return actions;
        },
      },
    ], items);
  }

  async function loadStockDetail(productId, trigger) {
    try {
      const payload = await apiRequest(
        `/api/v1/stocks/${encodeURIComponent(String(productId))}`
      );
      const item = payload?.data;
      if (!isRecord(item)) {
        throw new PublicError("INVALID_RESPONSE");
      }
      openDrawer({
        eyebrow: "Stock",
        title: displayValue(translated(NAME_TRANSLATIONS, item.product?.name)),
        trigger,
        content: detailsContent([
          {title: "Ligne de stock", items: [
            ["SKU / identifiant externe", item.external_product_id],
            ["Produit", translated(NAME_TRANSLATIONS, item.product?.name)],
            ["Quantité", item.quantity],
            ["Disponibilité", Number(item.quantity) > 0 ? "Disponible" : "Rupture"],
          ]},
          {title: "Succursale assignée", items: [
            ["Identifiant", item.branch?.id],
            ["Nom", item.branch?.name],
          ]},
        ]),
      });
    } catch (error) {
      showToast("Stock indisponible", publicMessage(error), "error");
      handleSessionError(error);
    }
  }

  function addLabelledField(form, {id, name, label, type = "text", value = "", required = false, readOnly = false, autocomplete = "off", help = ""}) {
    const field = createElement("div", "field");
    const labelElement = createElement("label", "", label);
    labelElement.setAttribute("for", id);
    const input = createElement("input");
    input.id = id;
    input.name = name;
    input.type = type;
    input.value = value;
    input.defaultValue = value;
    input.autocomplete = autocomplete;
    if (required) {
      input.required = true;
    }
    if (readOnly) {
      input.readOnly = true;
      input.setAttribute("readonly", "");
    }
    field.append(labelElement, input);
    if (help) {
      field.append(createElement("p", "inline-help", help));
    }
    form.append(field);
    return input;
  }

  function addSelectField(form, {id, name, label, options, value = ""}) {
    const field = createElement("div", "field");
    const labelElement = createElement("label", "", label);
    labelElement.setAttribute("for", id);
    const select = createElement("select");
    select.id = id;
    select.name = name;
    options.forEach(([optionValue, optionLabel]) => {
      const option = createElement("option", "", optionLabel);
      option.value = String(optionValue);
      if (String(optionValue) === String(value)) {
        option.selected = true;
        select.value = String(optionValue);
      }
      select.append(option);
    });
    field.append(labelElement, select);
    form.append(field);
    return select;
  }

  function addModalActions(form, submitLabel, danger = false) {
    const actions = createElement("div", "modal-actions");
    const cancel = createButton("Annuler", "button-secondary", () => closeModal());
    const submit = createElement(
      "button",
      danger ? "button-danger" : "",
      submitLabel
    );
    submit.type = "submit";
    actions.append(cancel, submit);
    form.append(actions);
    return submit;
  }

  function requiredText(formData, name, label) {
    const value = String(formData.get(name) ?? "").trim();
    if (!value) {
      throw new PublicError("VALIDATION_ERROR");
    }
    if (name === "username" && value.length > 80) {
      throw new PublicError("VALIDATION_ERROR");
    }
    return value;
  }

  function positiveInteger(formData, name) {
    const raw = String(formData.get(name) ?? "").trim();
    const value = Number(raw);
    if (!raw || !Number.isInteger(value) || value < 1) {
      throw new PublicError("INVALID_QUANTITY");
    }
    return value;
  }

  function positiveIdentifier(formData, name) {
    const raw = String(formData.get(name) ?? "").trim();
    const value = Number(raw);
    if (!raw || !Number.isInteger(value) || value < 1) {
      throw new PublicError("VALIDATION_ERROR");
    }
    return value;
  }

  function validatedPassword(formData, name) {
    const password = String(formData.get(name) ?? "");
    if (!password.trim()) {
      throw new PublicError("VALIDATION_ERROR");
    }
    const length = typeof TextEncoder === "function"
      ? new TextEncoder().encode(password).length
      : password.length;
    if (length > 72) {
      throw new PublicError("VALIDATION_ERROR");
    }
    return password;
  }

  function setFormPending(form, pending) {
    form.setAttribute("aria-busy", pending ? "true" : "false");
    form.querySelectorAll("button, input, select").forEach((control) => {
      control.disabled = pending;
    });
  }

  async function submitOnce(form, task) {
    if (pendingForms.has(form)) {
      return false;
    }
    pendingForms.add(form);
    setFormPending(form, true);
    try {
      await task();
      return true;
    } catch (error) {
      showToast("Action impossible", publicMessage(error), "error");
      handleSessionError(error);
      return false;
    } finally {
      pendingForms.delete(form);
      setFormPending(form, false);
    }
  }

  function openStockModal(action, item = null, trigger = null) {
    if (!canAccess("stocks")) {
      showToast("Accès refusé", "Les opérations de stock ne sont pas autorisées.", "error");
      return;
    }
    const isRemoval = action === "remove";
    const form = createElement("form", "modal-form");
    form.id = "stock-operation-form";
    const product = addLabelledField(form, {
      id: "stock-product-id",
      name: "product_id",
      label: "SKU / identifiant externe",
      value: item?.external_product_id ?? "",
      required: true,
      readOnly: Boolean(item?.external_product_id),
      help: item ? "Identifiant canonique de la ligne sélectionnée." : "Saisissez un produit existant du catalogue.",
    });
    const quantity = addLabelledField(form, {
      id: "stock-quantity",
      name: "quantity",
      label: isRemoval ? "Quantité à retirer" : "Quantité à ajouter",
      type: "number",
      value: "1",
      required: true,
      help: isRemoval && item
        ? `Quantité actuellement disponible : ${displayValue(item.quantity)}.`
        : "La quantité doit être un entier strictement positif.",
    });
    quantity.min = "1";
    quantity.step = "1";
    addModalActions(
      form,
      isRemoval ? "Confirmer le retrait" : "Confirmer l’ajout",
      isRemoval
    );
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitOnce(form, async () => {
        const data = new FormData(form);
        const productId = requiredText(data, "product_id", "Le produit");
        const movement = positiveInteger(data, "quantity");
        await apiRequest(
          `/api/v1/stocks/${encodeURIComponent(productId)}/${isRemoval ? "remove" : "add"}`,
          {
            method: "POST",
            body: JSON.stringify({quantity: movement}),
          }
        );
        closeModal();
        await loadStocks();
        showToast(
          isRemoval ? "Stock retiré" : "Stock ajouté",
          `${movement} unité${movement > 1 ? "s" : ""} ${isRemoval ? "retirée" : "ajoutée"}${movement > 1 ? "s" : ""}.`
        );
      });
    });
    openModal({
      eyebrow: "Mouvement de stock",
      title: isRemoval ? "Confirmer le retrait" : "Confirmer l’ajout",
      description: isRemoval
        ? "Cette opération diminue immédiatement le stock de votre succursale."
        : "Cette opération augmente le stock de votre succursale assignée.",
      content: form,
      trigger,
      initialFocus: item ? quantity : product,
    });
  }

  function populateBranchSelect(select, includeAll = false, selected = "") {
    select.replaceChildren();
    if (includeAll) {
      const all = createElement("option", "", "Toutes");
      all.value = "";
      select.append(all);
    }
    state.branches.forEach((branch) => {
      const option = createElement("option", "", branch.name);
      option.value = String(branch.id);
      if (String(branch.id) === String(selected)) {
        option.selected = true;
        select.value = String(branch.id);
      }
      select.append(option);
    });
    if (includeAll && !selected) {
      select.value = "";
    }
  }

  async function ensureBranches() {
    if (state.branches.length) {
      return state.branches;
    }
    const payload = await apiRequest("/api/v1/branches");
    state.branches = Array.isArray(payload?.data)
      ? payload.data.map((branch) => ({...branch}))
      : [];
    return state.branches;
  }

  async function ensureAllUsers(force = false) {
    if (state.allUsers && !force) {
      return state.allUsers;
    }
    const payload = await apiRequest("/api/v1/users?status=all");
    state.allUsers = Array.isArray(payload?.data)
      ? payload.data.map((user) => ({
        ...user,
        branch: isRecord(user.branch) ? {...user.branch} : user.branch,
      }))
      : [];
    return state.allUsers;
  }

  function renderUserKpis() {
    const users = state.allUsers ?? [];
    const common = users.filter((user) => user.role === "common_user");
    const active = common.filter((user) => user.is_active === true && !user.deleted_at);
    const deleted = common.filter((user) => user.is_active !== true || Boolean(user.deleted_at));
    dom.userKpis.replaceChildren();
    [
      ["Common users actifs", active.length],
      ["Common users supprimés", deleted.length],
    ].forEach(([label, value]) => {
      const item = createElement("article", "mini-kpi");
      item.append(
        createElement("span", "", label),
        createElement("strong", "", value)
      );
      dom.userKpis.append(item);
    });
  }

  function usersParameters() {
    const query = new URLSearchParams({status: state.userStatus});
    if (state.userBranch) {
      query.set("branch_id", state.userBranch);
    }
    return query;
  }

  async function loadUsers(options = {}) {
    if (!canAccess("users")) {
      return;
    }
    renderSkeleton(dom.usersContent);
    dom.usersSummary.textContent = "Chargement…";
    setWorkspaceLoading(true);
    try {
      await Promise.all([
        ensureBranches(),
        ensureAllUsers(Boolean(options.refreshStats)),
      ]);
      populateBranchSelect(dom.usersBranch, true, state.userBranch);
      const payload = await apiRequest(`/api/v1/users?${usersParameters().toString()}`);
      state.users = Array.isArray(payload?.data)
        ? payload.data.map((user) => ({
          ...user,
          branch: isRecord(user.branch) ? {...user.branch} : user.branch,
        }))
        : [];
      renderUserKpis();
      renderUsers();
      setAnnouncement("Utilisateurs chargés.");
    } catch (error) {
      dom.usersSummary.textContent = "";
      renderError(dom.usersContent, error, () => loadUsers({refreshStats: true}));
      handleSessionError(error);
    } finally {
      setWorkspaceLoading(false);
    }
  }

  function userIsMutable(user) {
    return user?.role === "common_user" &&
      user.is_active === true &&
      !user.deleted_at;
  }

  function renderUsers() {
    const query = dom.userSearch.value.trim().toLocaleLowerCase("fr-FR");
    const users = state.users.filter((user) => {
      return !query || String(user.username ?? "").toLocaleLowerCase("fr-FR").includes(query);
    });
    dom.usersSummary.textContent =
      `${users.length} utilisateur${users.length > 1 ? "s" : ""} affiché${users.length > 1 ? "s" : ""}`;
    renderTable(dom.usersContent, [
      {label: "Identifiant", render: (user) => user.id},
      {
        label: "Utilisateur",
        render: (user) => cell(user.username, displayRole(user.role)),
      },
      {
        label: "Succursale",
        render: (user) => user.branch?.name ?? "Aucune",
      },
      {
        label: "Statut",
        render: (user) => user.deleted_at || user.is_active !== true
          ? badge("Supprimé", "danger")
          : badge("Actif", "success"),
      },
      {
        label: "Actions",
        render: (user) => {
          const actions = createElement("div", "table-actions");
          actions.append(
            createButton("Détail", "table-action", (event) => {
              loadUserDetail(user.id, event.currentTarget);
            })
          );
          if (userIsMutable(user)) {
            actions.append(
              createButton("Modifier", "table-action", (event) => {
                openUserEditModal(user, event.currentTarget);
              }),
              createButton("Mot de passe", "table-action", (event) => {
                openUserPasswordModal(user, event.currentTarget);
              }),
              createButton("Supprimer", "table-action table-action-danger", (event) => {
                openUserDeleteModal(user, event.currentTarget);
              })
            );
          }
          return actions;
        },
      },
    ], users);
  }

  async function loadUserDetail(userId, trigger) {
    try {
      const payload = await apiRequest(`/api/v1/users/${userId}`);
      const user = payload?.data;
      if (!isRecord(user)) {
        throw new PublicError("INVALID_RESPONSE");
      }
      openDrawer({
        eyebrow: "Utilisateur",
        title: displayValue(user.username),
        trigger,
        content: detailsContent([
          {title: "Compte", items: [
            ["Identifiant", user.id],
            ["Nom d’utilisateur", user.username],
            ["Rôle", displayRole(user.role)],
            ["Statut", user.deleted_at || user.is_active !== true ? "Supprimé" : "Actif"],
            ["Date de suppression", formatDate(user.deleted_at)],
          ]},
          {title: "Affectation", items: [
            ["Identifiant de succursale", user.branch?.id],
            ["Succursale", user.branch?.name],
          ]},
        ]),
      });
    } catch (error) {
      showToast("Utilisateur indisponible", publicMessage(error), "error");
      handleSessionError(error);
    }
  }

  function branchOptions() {
    return state.branches.map((branch) => [branch.id, branch.name]);
  }

  function openUserCreateModal(trigger) {
    if (!canAccess("users")) {
      showToast("Accès refusé", "La création d’utilisateur est réservée à l’administrateur.", "error");
      return;
    }
    const form = createElement("form", "modal-form");
    form.id = "user-create-form";
    const username = addLabelledField(form, {
      id: "create-username",
      name: "username",
      label: "Nom d’utilisateur",
      required: true,
      autocomplete: "off",
      help: "Le nom sera normalisé en minuscules par le service.",
    });
    addLabelledField(form, {
      id: "create-password",
      name: "password",
      label: "Mot de passe initial",
      type: "password",
      required: true,
      autocomplete: "new-password",
      help: "72 octets UTF-8 maximum.",
    });
    addSelectField(form, {
      id: "create-branch-id",
      name: "branch_id",
      label: "Succursale",
      options: branchOptions(),
    });
    addModalActions(form, "Créer le common user");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitOnce(form, async () => {
        const data = new FormData(form);
        await apiRequest("/api/v1/users", {
          method: "POST",
          body: JSON.stringify({
            username: requiredText(data, "username", "Le nom d’utilisateur"),
            password: validatedPassword(data, "password"),
            branch_id: positiveIdentifier(data, "branch_id"),
          }),
        });
        closeModal();
        state.allUsers = null;
        await loadUsers({refreshStats: true});
        showToast("Utilisateur créé", "Le common user est maintenant actif.");
      });
    });
    openModal({
      eyebrow: "Administration",
      title: "Créer un common user",
      description: "Le compte sera affecté à une succursale existante.",
      content: form,
      trigger,
      initialFocus: username,
    });
  }

  function openUserEditModal(user, trigger) {
    if (!userIsMutable(user)) {
      showToast("Action interdite", "Ce compte ne peut pas être modifié.", "error");
      return;
    }
    const form = createElement("form", "modal-form");
    form.id = "user-edit-form";
    const hiddenId = createElement("input");
    hiddenId.type = "hidden";
    hiddenId.name = "user_id";
    hiddenId.value = String(user.id);
    hiddenId.defaultValue = hiddenId.value;
    form.append(hiddenId);
    const username = addLabelledField(form, {
      id: "edit-username",
      name: "username",
      label: "Nom d’utilisateur",
      value: user.username,
      required: true,
      autocomplete: "off",
    });
    addSelectField(form, {
      id: "edit-branch-id",
      name: "branch_id",
      label: "Succursale",
      options: branchOptions(),
      value: user.branch?.id,
    });
    addModalActions(form, "Enregistrer");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitOnce(form, async () => {
        if (!userIsMutable(user)) {
          throw new PublicError("FORBIDDEN");
        }
        const data = new FormData(form);
        await apiRequest(`/api/v1/users/${user.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            username: requiredText(data, "username", "Le nom d’utilisateur"),
            branch_id: positiveIdentifier(data, "branch_id"),
          }),
        });
        closeModal();
        state.allUsers = null;
        await loadUsers({refreshStats: true});
        showToast("Utilisateur modifié", "Les informations du compte ont été actualisées.");
      });
    });
    openModal({
      eyebrow: "Administration",
      title: `Modifier ${displayValue(user.username)}`,
      description: "Seuls le nom et la succursale peuvent être modifiés.",
      content: form,
      trigger,
      initialFocus: username,
    });
  }

  function openUserPasswordModal(user, trigger) {
    if (!userIsMutable(user)) {
      showToast("Action interdite", "Le mot de passe de ce compte ne peut pas être modifié.", "error");
      return;
    }
    const form = createElement("form", "modal-form");
    form.id = "user-password-form";
    const hiddenId = createElement("input");
    hiddenId.type = "hidden";
    hiddenId.name = "user_id";
    hiddenId.value = String(user.id);
    hiddenId.defaultValue = hiddenId.value;
    form.append(hiddenId);
    const password = addLabelledField(form, {
      id: "new-password",
      name: "new_password",
      label: "Nouveau mot de passe",
      type: "password",
      required: true,
      autocomplete: "new-password",
      help: "Cette action invalidera les sessions précédentes de l’utilisateur.",
    });
    addModalActions(form, "Changer le mot de passe");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitOnce(form, async () => {
        if (!userIsMutable(user)) {
          throw new PublicError("FORBIDDEN");
        }
        const data = new FormData(form);
        await apiRequest(`/api/v1/users/${user.id}/password`, {
          method: "PATCH",
          body: JSON.stringify({
            new_password: validatedPassword(data, "new_password"),
          }),
        });
        closeModal();
        await loadUsers();
        showToast("Mot de passe modifié", "Les anciennes sessions du compte sont invalidées.");
      });
    });
    openModal({
      eyebrow: "Action sensible",
      title: `Changer le mot de passe de ${displayValue(user.username)}`,
      description: "Confirmez le nouveau mot de passe avant de poursuivre.",
      content: form,
      trigger,
      initialFocus: password,
    });
  }

  function openUserDeleteModal(user, trigger) {
    if (!userIsMutable(user)) {
      showToast("Action interdite", "Ce compte ne peut pas être supprimé.", "error");
      return;
    }
    const form = createElement("form", "modal-form");
    form.id = "user-delete-form";
    const hiddenId = createElement("input");
    hiddenId.type = "hidden";
    hiddenId.name = "user_id";
    hiddenId.value = String(user.id);
    hiddenId.defaultValue = hiddenId.value;
    form.append(hiddenId);
    const warning = createElement(
      "p",
      "field-error",
      `Le compte ${displayValue(user.username)} sera désactivé. Cette interface ne permet pas sa réactivation.`
    );
    form.append(warning);
    const submit = addModalActions(form, "Supprimer logiquement", true);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitOnce(form, async () => {
        if (!userIsMutable(user)) {
          throw new PublicError("FORBIDDEN");
        }
        await apiRequest(`/api/v1/users/${user.id}`, {method: "DELETE"});
        closeModal();
        state.allUsers = null;
        await loadUsers({refreshStats: true});
        showToast("Utilisateur supprimé", "Le compte a été désactivé et conservé.");
      });
    });
    openModal({
      eyebrow: "Action irréversible dans l’interface",
      title: "Confirmer la suppression logique",
      description: "Les données associées sont conservées, mais le compte ne pourra plus se connecter.",
      content: form,
      trigger,
      initialFocus: submit,
    });
  }

  function handleSessionError(error) {
    if (error instanceof PublicError && error.code === "SESSION_EXPIRED") {
      clearTokens();
      showLogin(ERROR_MESSAGES.SESSION_EXPIRED, "error");
    }
  }

  function showApplication(user) {
    state.user = isRecord(user) ? {...user} : null;
    if (!state.user || !ROLE_VIEWS[state.user.role]) {
      clearTokens();
      showLogin("Ce compte possède un rôle non pris en charge.", "error");
      return;
    }
    dom.loginPanel.hidden = true;
    dom.application.hidden = false;
    dom.accountName.textContent = state.user.username;
    dom.accountAvatar.textContent = String(state.user.username || "U").slice(0, 1);
    dom.accountContext.textContent = state.user.role === "admin"
      ? "Administrateur"
      : `${displayRole(state.user.role)} · ${displayValue(state.user.branch?.name)}`;
    applyRoleNavigation();
    navigate("dashboard");
  }

  function showLogin(message = "", kind = "error") {
    closeModal(false);
    closeDrawer(false);
    closeSidebar();
    dom.application.hidden = true;
    dom.loginPanel.hidden = false;
    state.user = null;
    state.activeView = "dashboard";
    state.allUsers = null;
    dom.loginMessage.textContent = message;
    dom.loginMessage.className = `form-message ${kind === "success" ? "success" : ""}`.trim();
    focusElement(document.querySelector("#username"));
  }

  async function restoreSession() {
    if (!accessToken()) {
      showLogin();
      return;
    }
    try {
      const payload = await apiRequest("/api/v1/auth/me");
      if (!isRecord(payload?.data)) {
        throw new PublicError("INVALID_RESPONSE");
      }
      showApplication(payload.data);
    } catch {
      clearTokens();
      showLogin(ERROR_MESSAGES.SESSION_EXPIRED, "error");
    }
  }

  dom.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (pendingForms.has(dom.loginForm)) {
      return;
    }
    pendingForms.add(dom.loginForm);
    setFormPending(dom.loginForm, true);
    dom.loginMessage.textContent = "Connexion en cours…";
    dom.loginMessage.className = "form-message";
    try {
      const data = new FormData(dom.loginForm);
      const username = requiredText(data, "username", "Le nom d’utilisateur");
      const password = validatedPassword(data, "password");
      let response;
      try {
        response = await fetch("/api/v1/auth/login", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({username, password}),
        });
      } catch {
        throw new PublicError("NETWORK_ERROR");
      }
      const payload = await parseResponse(response);
      if (!response.ok) {
        throw errorFromResponse(response, payload);
      }
      const credentials = payload?.data;
      if (
        !isRecord(credentials) ||
        typeof credentials.access_token !== "string" ||
        typeof credentials.refresh_token !== "string" ||
        !isRecord(credentials.user)
      ) {
        throw new PublicError("INVALID_RESPONSE");
      }
      storeTokens(credentials);
      dom.loginForm.reset();
      dom.password.type = "password";
      dom.passwordToggle.setAttribute("aria-pressed", "false");
      dom.passwordToggle.setAttribute("aria-label", "Afficher le mot de passe");
      dom.loginMessage.textContent = "";
      showApplication(credentials.user);
    } catch (error) {
      clearTokens();
      dom.loginMessage.textContent = publicMessage(error);
      dom.loginMessage.className = "form-message";
    } finally {
      pendingForms.delete(dom.loginForm);
      setFormPending(dom.loginForm, false);
    }
  });

  dom.passwordToggle.addEventListener("click", () => {
    const visible = dom.password.type === "text";
    dom.password.type = visible ? "password" : "text";
    dom.passwordToggle.setAttribute("aria-pressed", visible ? "false" : "true");
    dom.passwordToggle.setAttribute(
      "aria-label",
      visible ? "Afficher le mot de passe" : "Masquer le mot de passe"
    );
    focusElement(dom.password);
  });

  document.querySelectorAll("[data-resource]").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.resource));
  });

  document.querySelectorAll("[data-refresh]").forEach((button) => {
    button.addEventListener("click", () => {
      const view = button.dataset.refresh;
      if (view === "users") {
        loadUsers({refreshStats: true});
      } else {
        loadView(view);
      }
    });
  });

  dom.branchSearch.addEventListener("input", () => {
    window.clearTimeout(branchSearchTimer);
    branchSearchTimer = window.setTimeout(renderBranches, 180);
  });
  dom.branchSearch.addEventListener("change", renderBranches);

  dom.productsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.productQuery.q = dom.productSearch.value.trim();
    state.productQuery.sort = dom.productSort.value;
    state.productMeta.offset = 0;
    await loadProducts();
  });
  dom.productSearch.addEventListener("input", () => {
    window.clearTimeout(productSearchTimer);
    productSearchTimer = window.setTimeout(() => {
      state.productQuery.q = dom.productSearch.value.trim();
      state.productMeta.offset = 0;
      loadProducts();
    }, 320);
  });

  document.querySelectorAll("[data-stock-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.stockFilter = button.dataset.stockFilter;
      document.querySelectorAll("[data-stock-filter]").forEach((candidate) => {
        candidate.setAttribute(
          "aria-pressed",
          candidate === button ? "true" : "false"
        );
      });
      renderStocks();
    });
  });
  dom.stockSearch.addEventListener("input", () => {
    window.clearTimeout(stockSearchTimer);
    stockSearchTimer = window.setTimeout(renderStocks, 180);
  });
  dom.stockSearch.addEventListener("change", renderStocks);
  dom.stockCreateButton.addEventListener("click", (event) => {
    openStockModal("add", null, event.currentTarget);
  });

  dom.usersForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.userStatus = ["active", "deleted", "all"].includes(dom.usersStatus.value)
      ? dom.usersStatus.value
      : "active";
    state.userBranch = dom.usersBranch.value;
    await loadUsers();
  });
  dom.userSearch.addEventListener("input", () => {
    window.clearTimeout(userSearchTimer);
    userSearchTimer = window.setTimeout(renderUsers, 180);
  });
  dom.userSearch.addEventListener("change", renderUsers);
  dom.userCreateButton.addEventListener("click", (event) => {
    openUserCreateModal(event.currentTarget);
  });

  dom.drawerClose.addEventListener("click", () => closeDrawer());
  dom.drawerOverlay.addEventListener("click", () => closeDrawer());
  dom.modalClose.addEventListener("click", () => closeModal());
  dom.modalOverlay.addEventListener("click", () => closeModal());
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (!dom.modal.hidden) {
        closeModal();
      } else if (!dom.drawer.hidden) {
        closeDrawer();
      } else {
        closeSidebar();
      }
      return;
    }
    if (!dom.modal.hidden) {
      trapFocus(event, dom.modal);
    } else if (!dom.drawer.hidden) {
      trapFocus(event, dom.drawer);
    }
  });

  dom.sidebarOpen.addEventListener("click", openSidebar);
  dom.sidebarClose.addEventListener("click", closeSidebar);
  dom.sidebarOverlay.addEventListener("click", closeSidebar);

  dom.logoutButton.addEventListener("click", async () => {
    if (logoutPending) {
      return;
    }
    logoutPending = true;
    dom.logoutButton.disabled = true;
    setWorkspaceLoading(true);
    const access = accessToken();
    const refresh = refreshToken();
    const revocations = [];
    if (access) {
      revocations.push(
        fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: {Authorization: `Bearer ${access}`},
        })
      );
    }
    if (refresh) {
      revocations.push(
        fetch("/api/v1/auth/logout/refresh", {
          method: "POST",
          headers: {Authorization: `Bearer ${refresh}`},
        })
      );
    }
    let confirmed = false;
    try {
      const results = await Promise.allSettled(revocations);
      confirmed = results.every(
        (result) => result.status === "fulfilled" && result.value.ok
      );
    } finally {
      clearTokens();
      logoutPending = false;
      dom.logoutButton.disabled = false;
      setWorkspaceLoading(false);
      showLogin(
        confirmed
          ? "Vous êtes déconnecté."
          : "Déconnexion locale effectuée, mais la révocation serveur n’a pas pu être confirmée.",
        confirmed ? "success" : "error"
      );
    }
  });

  restoreSession();
})();
