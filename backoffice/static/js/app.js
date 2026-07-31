/* Backoffice — main entry point: detect page and initialise the right module */

(function () {
  "use strict";

  const path = window.location.pathname;

  // ── Initialise shared modules ────────────────────────────────
  initModals();

  // ── Page-specific initialisation ─────────────────────────────
  if (path === "/login") {
    initLoginPage();
  } else {
    // Protected pages — build navigation first
    initNavigation();

    if (path === "/") {
      initDashboard();
    } else if (path === "/products") {
      initProductsPage();
    } else if (path.startsWith("/products/")) {
      initProductDetailPage();
    } else if (path === "/stocks") {
      initStocksPage();
    } else if (path === "/branches") {
      initBranchesPage();
    } else if (path === "/users") {
      initUsersPage();
    }
  }
})();
