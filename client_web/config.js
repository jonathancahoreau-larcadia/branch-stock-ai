/**
 * Runtime configuration for the public client.
 *
 * AI_QUERY_SERVICE_URL is intentionally isolated in this file so it can be
 * changed in one place — without touching app.js — once ai_service/
 * (Personne 2, POST /questions) exists.
 *
 * Local dev default below. In Docker Compose, replace with the service
 * name, e.g. "http://ai_service:8000/questions".
 */
window.APP_CONFIG = {
  AI_QUERY_SERVICE_URL: "http://localhost:8000/questions", /* replace by the real URL or the Docker Compose service name */
};