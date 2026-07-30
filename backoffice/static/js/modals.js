/* Backoffice — modal helpers */

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("modal--open");
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("modal--open");
}

function initModals() {
  // Close on backdrop click
  document.querySelectorAll(".modal__backdrop").forEach(function (backdrop) {
    backdrop.addEventListener("click", function () {
      const modal = this.closest(".modal");
      if (modal) modal.classList.remove("modal--open");
    });
  });

  // Close on Escape key
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal--open").forEach(function (m) {
        m.classList.remove("modal--open");
      });
    }
  });
}
</write_to_file>