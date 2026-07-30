/**
 * Communication avec l'AI Query Service.
 *
 * Envoie une question au service et retourne la réponse structurée.
 * Gère le timeout (30s) et empêche les doubles envois.
 */

const Api = (() => {
  const AI_URL = window.APP_CONFIG.AI_QUERY_URL;
  const TIMEOUT_MS = 30000; // 30 secondes
  let requestInProgress = false;

  /**
   * Envoie une question à l'AI Query Service.
   *
   * @param {string} question - La question posée par l'utilisateur
   * @returns {Promise<{ok: boolean, data?: object, error?: string}>}
   */
  async function sendQuestion(question) {
    if (requestInProgress) {
      return { ok: false, error: "Une requête est déjà en cours." };
    }

    requestInProgress = true;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

      let response;
      try {
        response = await fetch(AI_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeoutId);
      }

      if (!response.ok) {
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
      if (err.name === "AbortError") {
        return {
          ok: false,
          error:
            "Le service a mis trop de temps à répondre. " +
            "Veuillez reformuler votre question ou réessayer.",
        };
      }
      return {
        ok: false,
        error:
          "Impossible de joindre le service. Vérifiez votre connexion " +
          "ou réessayez plus tard.",
      };
    } finally {
      requestInProgress = false;
    }
  }

  return {
    sendQuestion,
  };
})();
</write_to_file>