/* Backoffice — products page: list, filters, pagination, detail */

async function initProductsPage() {
  if (!requireAuth()) return;

  const tableBody = document.getElementById("products-table-body");
  if (!tableBody) return;

  await loadProducts();
}

async function loadProducts() {
  const tableBody = document.getElementById("products-table-body");
  if (!tableBody) return;

  hideError();

  // Read filters from URL
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const includeDiscontinued = params.get("include_discontinued") === "true";
  const sort = params.get("sort") || "";
  const limit = parseInt(params.get("limit") || "20", 10);
  const offset = parseInt(params.get("offset") || "0", 10);

  // Build API query
  const apiParams = new URLSearchParams();
  apiParams.set("limit", String(limit));
  apiParams.set("offset", String(offset));
  if (includeDiscontinued) apiParams.set("include_discontinued", "true");
  if (sort) apiParams.set("sort", sort);
  if (q) apiParams.set("q", q);
  if (category) apiParams.set("category", category);

  try {
    const products = await apiFetch(
      `${CONFIG.API_BASE}/products?${apiParams.toString()}`
    );

    if (!products || products.length === 0) {
      tableBody.innerHTML =
        '<tr><td colspan="7" class="table__empty">Aucun produit trouvé.</td></tr>';
      return;
    }

    tableBody.innerHTML = products
      .map(
        (p) => `
      <tr>
        <td><code>${escapeHtml(p.external_product_id)}</code></td>
        <td>${escapeHtml(p.name)}</td>
        <td>${escapeHtml(p.category)}</td>
        <td>${escapeHtml(p.brand)}</td>
        <td class="table__numeric">${formatPrice(p.unit_price, p.currency)}</td>
        <td>${
          p.discontinued
            ? '<span class="badge badge--danger">Oui</span>'
            : '<span class="badge badge--success">Non</span>'
        }</td>
        <td>
          <a href="/products/${encodeURIComponent(p.external_product_id)}"
             class="btn btn--sm">Voir les détails</a>
        </td>
      </tr>`
      )
      .join("");

    // Update pagination info
    updatePagination(offset, limit, products.length);
  } catch (err) {
    if (err instanceof ApiError) {
      showError(err.message);
    } else {
      showError("Erreur lors du chargement des produits.");
    }
    tableBody.innerHTML =
      '<tr><td colspan="7" class="table__empty">Erreur de chargement.</td></tr>';
  }
}

function formatPrice(price, currency) {
  if (typeof price !== "number") return "—";
  return price.toFixed(2) + " " + (currency || "EUR");
}

function updatePagination(offset, limit, count) {
  const el = document.getElementById("pagination-info");
  if (!el) return;

  const page = Math.floor(offset / limit) + 1;
  el.textContent = `${count} produit(s) — page ${page}`;
}

async function initProductDetailPage() {
  if (!requireAuth()) return;

  const detailContainer = document.getElementById("product-detail");
  if (!detailContainer) return;

  // Extract product ID from URL
  const pathParts = window.location.pathname.split("/");
  const productId = pathParts[pathParts.length - 1];
  if (!productId) return;

  hideError();

  try {
    const product = await apiFetch(
      `${CONFIG.API_BASE}/products/${encodeURIComponent(productId)}`
    );

    if (!product) {
      showError("Produit introuvable.");
      return;
    }

    // Fill in the detail fields
    setTextContent("detail-sku", product.external_product_id);
    setTextContent("detail-name", product.name);
    setTextContent("detail-description", product.description);
    setTextContent("detail-category", product.category);
    setTextContent("detail-brand", product.brand);
    setTextContent(
      "detail-discontinued",
      product.discontinued ? "Oui" : "Non"
    );
    setTextContent(
      "detail-price",
      formatPrice(product.unit_price, product.currency)
    );
    setTextContent("detail-weight", product.weight_kg ? product.weight_kg.toFixed(2) + " kg" : "—");
    setTextContent("detail-updated-at", product.updated_at || "—");

    // Supplier info
    if (product.supplier) {
      setTextContent("detail-supplier-name", product.supplier.name);
      setTextContent("detail-supplier-country", product.supplier.country);
      setTextContent(
        "detail-supplier-lead-time",
        String(product.supplier.lead_time_days)
      );
      setTextContent(
        "detail-supplier-reliability",
        product.supplier.reliability_score
          ? Math.round(product.supplier.reliability_score * 100) + "%"
          : "—"
      );
    }

    // Tags
    const tagsContainer = document.getElementById("detail-tags");
    if (tagsContainer && product.tags) {
      tagsContainer.innerHTML = product.tags
        .map((t) => `<span class="badge badge--info">${escapeHtml(t)}</span>`)
        .join("");
    }
  } catch (err) {
    if (err instanceof ApiError) {
      showError(err.message);
    } else {
      showError("Erreur lors du chargement du produit.");
    }
  }
}

function setTextContent(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value || "—";
}
</write_to_file>