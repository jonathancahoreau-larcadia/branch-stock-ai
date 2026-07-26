/**
 * Gestion des événements utilisateur.
 *
 * Attache les écouteurs d'événements (submit, input, clic)
 * aux éléments du DOM.
 */

const Events = (() => {
  function init() {
    const form = document.getElementById("question-form");
    const input = document.getElementById("question-input");

    if (!form || !input) return;

    // Compteur de caractères et activation du bouton
    input.addEventListener("input", () => {
      Ui.updateCharCount();
      Ui.updateSubmitButton();
    });

    // Soumission du formulaire
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      await handleSubmit();
    });

    // Permet Ctrl+Enter pour envoyer
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        form.dispatchEvent(new Event("submit"));
      }
    });
  }

  async function handleSubmit() {
    const input = document.getElementById("question-input");
    const question = input.value.trim();

    if (!question) return;

    // Afficher le chargement
    Ui.showLoading();
    Ui.hideError();

    // Envoyer la question
    const result = await Api.sendQuestion(question);

    // Masquer le chargement
    Ui.hideLoading();

    if (result.ok && result.data) {
      Ui.displayResponse(result.data);
    } else {
      Ui.displayError(
        result.error || "Une erreur inattendue s'est produite."
      );
    }
  }

  return {
    init,
  };
})();