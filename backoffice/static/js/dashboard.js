/* Backoffice — dashboard page */

async function initDashboard() {
  if (!requireAuth()) return;

  const user = getCurrentUser();
  const welcomeEl = document.getElementById("welcome-username");
  if (welcomeEl && user) {
    welcomeEl.textContent = user.username;
  }
}
</write_to_file>