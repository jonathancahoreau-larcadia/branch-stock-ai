/* Backoffice — dynamic sidebar navigation */

/**
 * Build and inject the sidebar navigation based on the current user.
 * If the user is not logged in, the sidebar is not rendered.
 */
function initNavigation() {
  const sidebar = document.getElementById("main-navigation");
  if (!sidebar) return;

  const user = getCurrentUser();
  if (!user) return;

  const currentPath = window.location.pathname;

  const links = [
    { href: "/", label: "Dashboard", roles: null },
    { href: "/products", label: "Produits", roles: null },
    { href: "/stocks", label: "Stocks", roles: ["common_user"] },
    { href: "/branches", label: "Succursales", roles: null },
    { href: "/users", label: "Utilisateurs", roles: ["admin"] },
  ];

  const visibleLinks = links.filter(
    (link) => link.roles === null || link.roles.includes(user.role)
  );

  sidebar.innerHTML = `
    <nav class="app__sidebar">
      <div class="sidebar__header">
        <h2>Branch Stock AI</h2>
        <p class="sidebar__role">${escapeHtml(user.role)}</p>
      </div>
      <ul class="sidebar__nav">
        ${visibleLinks
          .map(
            (link) => `
          <li>
            <a href="${link.href}"
               class="nav-link${currentPath === link.href ? " active" : ""}">
              ${escapeHtml(link.label)}
            </a>
          </li>`
          )
          .join("")}
      </ul>
      <div class="sidebar__footer">
        <span class="sidebar__user">${escapeHtml(user.username)}</span>
        <button id="logout-btn" class="btn btn--sm btn--outline">Déconnexion</button>
      </div>
    </nav>
  `;

  document.getElementById("logout-btn")?.addEventListener("click", logout);
}
</write_to_file>