/* Backoffice — branches page: list via API */

async function initBranchesPage() {
  if (!requireAuth()) return;

  const tableBody = document.getElementById("branches-table-body");
  if (!tableBody) return;

  await loadBranches();
}

async function loadBranches() {
  const tableBody = document.getElementById("branches-table-body");
  if (!tableBody) return;

  hideError();

  try {
    const branches = await apiFetch(`${CONFIG.API_BASE}/branches`);

    if (!branches || branches.length === 0) {
      tableBody.innerHTML =
        '<tr><td colspan="2" class="table__empty">Aucune succursale trouvée.</td></tr>';
      return;
    }

    tableBody.innerHTML = branches
      .map(
        (b) => `
      <tr>
        <td>${escapeHtml(String(b.id))}</td>
        <td>${escapeHtml(b.name)}</td>
      </tr>`
      )
      .join("");
  } catch (err) {
    if (err instanceof ApiError) {
      showError(err.message);
    } else {
      showError("Erreur lors du chargement des succursales.");
    }
    tableBody.innerHTML =
      '<tr><td colspan="2" class="table__empty">Erreur de chargement.</td></tr>';
  }
}
window.initBranchesPage = initBranchesPage;