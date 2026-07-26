/**
 * Gestion de l'affichage (UI).
 *
 * Met à jour le DOM : affichage de la réponse, du chargement,
 * des erreurs, et du compteur de caractères.
 */

const Ui = (() => {
  // ── Références DOM ──────────────────────────────────────────

  let elements = {};

  function init() {
    elements = {
      form: document.getElementById("question-form"),
      input: document.getElementById("question-input"),
      submitBtn: document.getElementById("submit-button"),
      charCount: document.getElementById("char-count"),
      loading: document.getElementById("loading-indicator"),
      responseArea: document.getElementById("response-area"),
      errorAlert: document.getElementById("error-alert"),
    };
  }

  // ── Compteur de caractères ──────────────────────────────────

  function updateCharCount() {
    if (!elements.input || !elements.charCount) return;
    const count = elements.input.value.length;
    const max = elements.input.maxLength;
    elements.charCount.textContent = `${count} / ${max}`;
  }

  // ── État du bouton submit ───────────────────────────────────

  function updateSubmitButton() {
    if (!elements.input || !elements.submitBtn) return;
    elements.submitBtn.disabled = elements.input.value.trim().length === 0;
  }

  // ── Chargement ──────────────────────────────────────────────

  function showLoading() {
    if (elements.loading) elements.loading.hidden = false;
    if (elements.responseArea) elements.responseArea.innerHTML = "";
    if (elements.errorAlert) elements.errorAlert.hidden = true;
    if (elements.input) elements.input.disabled = true;
    if (elements.submitBtn) elements.submitBtn.disabled = true;
  }

  function hideLoading() {
    if (elements.loading) elements.loading.hidden = true;
    if (elements.input) elements.input.disabled = false;
    updateSubmitButton();
  }

  // ── Réponse ─────────────────────────────────────────────────

  function displayResponse(data) {
    if (!elements.responseArea) return;

    const status = data.status || "success";
    const answer = data.answer || "";
    const responseData = data.data || {};

    // Classe CSS selon le statut
    const statusClass = `response--${status}`;

    let html = `<div class="response ${statusClass}">`;

    // Titre du statut
    html += `<p class="response__answer">${Utils.escapeHtml(answer)}</p>`;

    // Données supplémentaires (produits, branches)
    if (responseData.products && responseData.products.length > 0) {
      html += `<div class="response__data"><strong>Produits :</strong><ul>`;
      for (const product of responseData.products) {
        html += `<li>${Utils.escapeHtml(product.name || product.external_product_id)}`;
        if (product.external_product_id) {
          html += ` (${Utils.escapeHtml(product.external_product_id)})`;
        }
        html += `</li>`;
      }
      html += `</ul></div>`;
    }

    if (responseData.branches && responseData.branches.length > 0) {
      html += `<div class="response__data"><strong>Succursales :</strong><ul>`;
      for (const branch of responseData.branches) {
        html += `<li>${Utils.escapeHtml(branch.branch_name || "?")}`;
        if (branch.available_quantity !== undefined) {
          html += ` — ${branch.available_quantity} unité(s)`;
        }
        html += `</li>`;
      }
      html += `</ul></div>`;
    }

    // Types de questions supportées (pour status "unsupported")
    if (
      responseData.supported_question_types &&
      responseData.supported_question_types.length > 0
    ) {
      html += `<div class="response__data"><strong>Types de questions supportées :</strong><ul>`;
      for (const qtype of responseData.supported_question_types) {
        html += `<li>${Utils.escapeHtml(qtype)}</li>`;
      }
      html += `</ul></div>`;
    }

    // Indice pour les statuts non-success
    if (status !== "success") {
      html += `<p class="response__hint">${Utils.translateStatus(status)}</p>`;
    }

    html += `</div>`;
    elements.responseArea.innerHTML = html;
  }

  // ── Erreur ──────────────────────────────────────────────────

  function displayError(message) {
    if (elements.errorAlert) {
      elements.errorAlert.textContent = message;
      elements.errorAlert.hidden = false;
    }
    if (elements.responseArea) {
      elements.responseArea.innerHTML = "";
    }
  }

  function hideError() {
    if (elements.errorAlert) {
      elements.errorAlert.hidden = true;
    }
  }

  // ── API publique ────────────────────────────────────────────

  return {
    init,
    updateCharCount,
    updateSubmitButton,
    showLoading,
    hideLoading,
    displayResponse,
    displayError,
    hideError,
  };
})();