/* Backoffice — users page: CRUD via API */

async function initUsersPage() {
  if (!requireAuth()) return;
  if (!requireAdmin()) return;

  const tableBody = document.getElementById("users-table-body");
  if (!tableBody) return;

  await loadUsers();
  initUserForms();
}

async function loadUsers() {
  const tableBody = document.getElementById("users-table-body");
  if (!tableBody) return;

  hideError();

  const params = new URLSearchParams(window.location.search);
  const status = params.get("status") || "active";
  const branchId = params.get("branch_id") || "";

  const apiParams = new URLSearchParams();
  if (status !== "active") apiParams.set("status", status);
  if (branchId) apiParams.set("branch_id", branchId);

  try {
    const users = await apiFetch(
      `${CONFIG.API_BASE}/users?${apiParams.toString()}`
    );

    if (!users || users.length === 0) {
      tableBody.innerHTML =
        '<tr><td colspan="6" class="table__empty">Aucun utilisateur trouvé.</td></tr>';
      return;
    }

    tableBody.innerHTML = users
      .map(
        (u) => `
      <tr>
        <td>${escapeHtml(String(u.id))}</td>
        <td>${escapeHtml(u.username)}</td>
        <td><span class="badge badge--${u.role === "admin" ? "admin" : "info"}">${escapeHtml(u.role)}</span></td>
        <td>${u.branch ? escapeHtml(u.branch.name) : "—"}</td>
        <td>${
          u.is_active
            ? '<span class="badge badge--success">Oui</span>'
            : '<span class="badge badge--danger">Non</span>'
        }</td>
        <td class="table__actions">
          <button type="button" class="btn btn--sm" data-action="edit"
            data-user-id="${escapeHtml(String(u.id))}"
            data-username="${escapeHtml(u.username)}"
            data-branch-id="${u.branch ? u.branch.id : ""}">Modifier</button>
          <button type="button" class="btn btn--sm" data-action="password"
            data-user-id="${escapeHtml(String(u.id))}">Changer mot de passe</button>
          ${
            u.is_active && u.role !== "admin"
              ? `<button type="button" class="btn btn--sm btn--danger" data-action="delete"
                  data-user-id="${escapeHtml(String(u.id))}"
                  data-username="${escapeHtml(u.username)}">Supprimer</button>`
              : ""
          }
        </td>
      </tr>`
      )
      .join("");

    // Re-bind modal triggers
    bindUserModalTriggers();
  } catch (err) {
    if (err instanceof ApiError) {
      showError(err.message);
    } else {
      showError("Erreur lors du chargement des utilisateurs.");
    }
    tableBody.innerHTML =
      '<tr><td colspan="6" class="table__empty">Erreur de chargement.</td></tr>';
  }
}

function bindUserModalTriggers() {
  // Edit
  document.querySelectorAll('[data-action="edit"]').forEach((btn) => {
    btn.addEventListener("click", function () {
      const userId = this.getAttribute("data-user-id");
      const username = this.getAttribute("data-username");
      const branchId = this.getAttribute("data-branch-id");

      const form = document.getElementById("edit-user-form");
      if (!form) return;

      form.dataset.userId = userId;
      document.getElementById("edit-username").value = username || "";
      document.getElementById("edit-branch").value = branchId || "";
      openModal("edit-user-modal");
    });
  });

  // Password
  document.querySelectorAll('[data-action="password"]').forEach((btn) => {
    btn.addEventListener("click", function () {
      const userId = this.getAttribute("data-user-id");
      const form = document.getElementById("password-form");
      if (!form) return;

      form.dataset.userId = userId;
      document.getElementById("new-password").value = "";
      openModal("password-modal");
    });
  });

  // Delete
  document.querySelectorAll('[data-action="delete"]').forEach((btn) => {
    btn.addEventListener("click", async function () {
      const userId = this.getAttribute("data-user-id");
      const username = this.getAttribute("data-username");

      if (!confirm(`Supprimer l'utilisateur "${username}" ?`)) return;

      try {
        await apiFetch(`${CONFIG.API_BASE}/users/${userId}`, {
          method: "DELETE",
        });
        showFlash("Utilisateur supprimé avec succès.", "success");
        await loadUsers();
      } catch (err) {
        if (err instanceof ApiError) {
          showFlash(err.message, "error");
        } else {
          showFlash("Erreur lors de la suppression.", "error");
        }
      }
    });
  });
}

function initUserForms() {
  // Create user
  const createForm = document.getElementById("create-user-form");
  if (createForm) {
    createForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const formData = new FormData(createForm);
      const username = formData.get("username");
      const password = formData.get("password");
      const branchId = parseInt(formData.get("branch_id"), 10);

      if (!username || !password || !branchId) {
        showFlash("Tous les champs sont requis.", "error");
        return;
      }

      try {
        await apiFetch(`${CONFIG.API_BASE}/users`, {
          method: "POST",
          body: JSON.stringify({ username, password, branch_id: branchId }),
        });
        showFlash("Utilisateur créé avec succès.", "success");
        closeModal("create-user-modal");
        createForm.reset();
        await loadUsers();
      } catch (err) {
        if (err instanceof ApiError) {
          showFlash(err.message, "error");
        } else {
          showFlash("Erreur lors de la création.", "error");
        }
      }
    });
  }

  // Edit user
  const editForm = document.getElementById("edit-user-form");
  if (editForm) {
    editForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const userId = editForm.dataset.userId;
      const formData = new FormData(editForm);
      const payload = {};

      const username = formData.get("username");
      const branchId = formData.get("branch_id");

      if (username) payload.username = username;
      if (branchId) payload.branch_id = parseInt(branchId, 10);

      try {
        await apiFetch(`${CONFIG.API_BASE}/users/${userId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        showFlash("Utilisateur modifié avec succès.", "success");
        closeModal("edit-user-modal");
        await loadUsers();
      } catch (err) {
        if (err instanceof ApiError) {
          showFlash(err.message, "error");
        } else {
          showFlash("Erreur lors de la modification.", "error");
        }
      }
    });
  }

  // Change password
  const passwordForm = document.getElementById("password-form");
  if (passwordForm) {
    passwordForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const userId = passwordForm.dataset.userId;
      const newPassword = document.getElementById("new-password").value;

      if (!newPassword) {
        showFlash("Mot de passe requis.", "error");
        return;
      }

      try {
        await apiFetch(`${CONFIG.API_BASE}/users/${userId}/password`, {
          method: "PATCH",
          body: JSON.stringify({ new_password: newPassword }),
        });
        showFlash("Mot de passe changé avec succès.", "success");
        closeModal("password-modal");
      } catch (err) {
        if (err instanceof ApiError) {
          showFlash(err.message, "error");
        } else {
          showFlash("Erreur lors du changement de mot de passe.", "error");
        }
      }
    });
  }
}
window.initUsersPage = initUsersPage;