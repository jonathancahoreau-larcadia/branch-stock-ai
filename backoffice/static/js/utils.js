/* Backoffice — utility functions */

/**
 * Escape HTML special characters to prevent XSS.
 */
function escapeHtml(str) {
  if (typeof str !== "string") return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Show an error message in the #page-error element.
 */
function showError(message) {
  const el = document.getElementById("page-error");
  if (!el) return;
  el.textContent = message;
  el.hidden = false;
}

/**
 * Hide the #page-error element.
 */
function hideError() {
  const el = document.getElementById("page-error");
  if (!el) return;
  el.hidden = true;
}

/**
 * Show a success flash message.
 */
function showFlash(message, category) {
  const container = document.getElementById("flash-messages");
  if (!container) return;
  const div = document.createElement("div");
  div.className = "alert alert--" + (category || "info");
  div.textContent = message;
  container.appendChild(div);
  // Auto-dismiss after 5 seconds
  setTimeout(() => div.remove(), 5000);
}
</write_to_file>