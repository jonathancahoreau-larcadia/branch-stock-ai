/**
 * Point d'entrée de l'application.
 *
 * Initialise tous les modules dans l'ordre.
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialiser l'UI (références DOM)
  Ui.init();

  // 2. Mettre à jour l'état initial du formulaire
  Ui.updateCharCount();
  Ui.updateSubmitButton();

  // 3. Initialiser les événements
  Events.init();
});