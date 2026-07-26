/**
 * Configuration centralisée.
 *
 * AI_QUERY_URL : URL du service AI Query (POST /questions).
 *                En local : http://localhost:8000/questions
 *                En Docker Compose : http://ai_service:8000/questions
 */
window.APP_CONFIG = {
  AI_QUERY_URL: "http://localhost:8000/questions",
};