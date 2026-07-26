/**
 * Fonctions utilitaires.
 */

const Utils = (() => {
  /**
   * Échappe les caractères HTML pour éviter les injections XSS.
   * @param {string} str - La chaîne à échapper
   * @returns {string} Chaîne échappée
   */
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /**
   * Formate une date ISO en chaîne lisible (locale fr).
   * @param {string} isoString - Date au format ISO 8601
   * @returns {string} Date formatée
   */
  function formatDate(isoString) {
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString("fr-FR", {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  }

  /**
   * Retourne la chaîne de statut en français pour l'AI Query Service.
   * @param {string} status - Le statut (success, partial, unavailable, unsupported)
   * @returns {string} Libellé en français
   */
  function translateStatus(status) {
    const labels = {
      success: "Réponse complète",
      partial: "Réponse partielle",
      unavailable: "Non disponible",
      unsupported: "Question non prise en charge",
    };
    return labels[status] || status;
  }

  return {
    escapeHtml,
    formatDate,
    translateStatus,
  };
})();