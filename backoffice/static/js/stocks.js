/* Backoffice — stocks page: list, add, remove via API */

async function initStocksPage() {
  if (!requireAuth()) return;

  const tableBody = document.getElementById("stocks-table-body");
  if (!tableBody) return;

  await loadStocks();
  initStockForms();
}

async function loadStocks() {
  const tableBody = document.getElementById("stocks-table-body");
  if (!tableBody) return;

  hideError();

  const params = new URLSearchParams(window.location.search);
  const availableOnly = params.get("available_only") !== "false";
  const search = params.get("search") || "";

  const apiParams = new URLSearchParams();
  apiParams.set("available_only", availableOnly ? "true" : "false");
  if (search) apiParams.set("search", search);

  try {
    const stocks = await apiFetch(
      `${CONFIG.API_BASE}/stocks?${apiParams.toString()}`
    );

    if (!stocks || stocks.length === 0) {
      tableBody.innerHTML =
        '<tr><td colspan="3" class="table__empty">Aucun stock trouvé pour cette succursale.</td></tr>';
      return;
    }

    tableBody.innerHTML = stocks
      .map(
        (s) => `
      <tr>
        <td><code>${escapeHtml(s.external_product_id)}</code></td>
        <td>${escapeHtml(s.product?.name || s.external_product_id)}</td>
        <td class="table__numeric">
          ${
            s.quantity > 0
              ? `<span class="badge badge--success">${escapeHtml(String(s.quantity))}</span>`
              : `<span class="badge badge--danger">0</span>`
          }
        </td>
      </tr>`
      )
      .join("");
  } catch (err) {
    if (err instanceof ApiError) {
      showError(getStockErrorMessage(err.code));
    } else {
      showError("Erreur lors du chargement des stocks.");
    }
    tableBody.innerHTML =
      '<tr><td colspan="3" class="table__empty">Erreur de chargement.</td></tr>';
  }
}

function getStockErrorMessage(code) {
  const messages = {
    INVALID_QUANTITY: "La quantité doit être un entier supérieur à zéro.",
    INSUFFICIENT_STOCK: "Il n'y a pas assez de stock disponible.",
    PRODUCT_NOT_FOUND: "Le produit demandé n'existe pas.",
    ADMIN_STOCK_FORBIDDEN:
      "Un administrateur ne peut pas modifier les stocks.",
    STOCK_CONFLICT:
      "Le stock a changé. Actualise la page puis recommence.",
  };
  return messages[code] || "Erreur lors de l'opération sur le stock.";
}

function initStockForms() {
  // Add stock form
  const addForm = document.getElementById("stock-add-form");
  if (addForm) {
    addForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData(addForm);
      const productId = formData.get("external_product_id");
      const quantity = parseInt(formData.get("quantity") || "1", 10);

      if (!productId) {
        showFlash("ID produit requis.", "error");
        return;
      }
      if (quantity <= 0) {
        showFlash("La quantité doit être positive.", "error");
        return;
      }

      try {
        await apiFetch(
          `${CONFIG.API_BASE}/stocks/${encodeURIComponent(productId)}/add`,
          {
            method: "POST",
            body: JSON.stringify({ quantity }),
          }
        );
        showFlash("Stock ajouté avec succès.", "success");
        addForm.reset();
        await loadStocks();
      } catch (err) {
        if (err instanceof ApiError) {
          showFlash(getStockErrorMessage(err.code), "error");
        } else {
          showFlash("Erreur lors de l'ajout de stock.", "error");
        }
      }
    });
  }

  // Remove stock form
  const removeForm = document.getElementById("stock-remove-form");
  if (removeForm) {
    removeForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData(removeForm);
      const productId = formData.get("external_product_id");
      const quantity = parseInt(formData.get("quantity") || "1", 10);

      if (!productId) {
        showFlash("ID produit requis.", "error");
        return;
      }
      if (quantity <= 0) {
        showFlash("La quantité doit être positive.", "error");
        return;
      }

      try {
        await apiFetch(
          `${CONFIG.API_BASE}/stocks/${encodeURIComponent(productId)}/remove`,
          {
            method: "POST",
            body: JSON.stringify({ quantity }),
          }
        );
        showFlash("Stock retiré avec succès.", "success");
        removeForm.reset();
        await loadStocks();
      } catch (err) {
        if (err instanceof ApiError) {
          showFlash(getStockErrorMessage(err.code), "error");
        } else {
          showFlash("Erreur lors du retrait de stock.", "error");
        }
      }
    });
  }
}
window.initStocksPage = initStocksPage;