/**
 * Communication avec l'AI Query Service.
 *
 * Envoie une question au service et retourne la réponse structurée.
 */

const Api = (() => {
  const AI_URL = window.APP_CONFIG.AI_QUERY_URL;

  /**
   * Envoie une question à l'AI Query Service.
   *
   * @param {string} question - La question posée par l'utilisateur
   * @returns {Promise<{ok: boolean, data?: object, error?: string}>}
   */
  async function sendQuestion(question) {
    try {
      const response = await fetch(AI_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!response.ok) {
        // Erreur HTTP (5xx, 4xx)
        let errorMessage = `Erreur serveur (${response.status})`;
        try {
          const errorBody = await response.json();
          if (errorBody && errorBody.error) {
            errorMessage = errorBody.error.message || errorMessage;
          }
        } catch {
          // La réponse n'est pas du JSON
        }
        return { ok: false, error: errorMessage };
      }

      const data = await response.json();
      return { ok: true, data };
    } catch (err) {
      // Erreur réseau (pas de connexion, timeout)
      return {
        ok: false,
        error:
          "Impossible de joindre le service. Vérifiez votre connexion " +
          "ou réessayez plus tard.",
      };
    }
  }

  return {
    sendQuestion,
  };
})();