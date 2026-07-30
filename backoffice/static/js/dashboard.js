/* Backoffice — dashboard page */

async function initDashboard() {
  if (!requireAuth()) return;

  const user = getCurrentUser();

  const welcomeEl = document.getElementById("welcome-username");

  if (welcomeEl && user) {
    welcomeEl.textContent = user.username;
  }

  const usersLink = document.getElementById("dashboard-users-link");

  if (usersLink && user && user.role === "admin") {
    usersLink.hidden = false;
  }
}

window.initDashboard = initDashboard;