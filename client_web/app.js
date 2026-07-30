(() => {
  "use strict";

  const form = document.querySelector("#question-form");
  const questionInput = document.querySelector("#question");
  const submitButton = document.querySelector("#submit-button");
  const requestStatus = document.querySelector("#request-status");
  const answerOutput = document.querySelector("#answer-output");
  const dataOutput = document.querySelector("#data-output");
  const acceptedStatuses = new Set([
    "success",
    "partial",
    "unavailable",
    "unsupported",
  ]);
  const statusLabels = {
    success: "Success — réponse complète.",
    partial: "Partial — réponse partielle.",
    unavailable: "Unavailable — informations insuffisantes.",
    unsupported: "Unsupported — question hors périmètre.",
  };
  const technicalError = "Une erreur technique empêche l’affichage de la réponse.";
  let requestInProgress = false;

  function updateSubmitState() {
    submitButton.disabled =
      requestInProgress || questionInput.value.trim().length === 0;
  }

  function setStatus(state, message) {
    requestStatus.className = `request-status request-status--${state}`;
    requestStatus.dataset.state = state;
    requestStatus.textContent = message;
  }

  function clearResponse() {
    const emptyAnswer = document.createElement("span");
    emptyAnswer.textContent = "";
    answerOutput.replaceChildren(emptyAnswer);
    answerOutput.textContent = "";
    dataOutput.textContent = "";
  }

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isPublicResponse(payload) {
    return (
      isRecord(payload) &&
      acceptedStatuses.has(payload.status) &&
      typeof payload.answer === "string" &&
      isRecord(payload.data)
    );
  }

  function safeHttpMessage(payload) {
    if (
      !isRecord(payload) ||
      payload.status !== "error" ||
      !isRecord(payload.error) ||
      typeof payload.error.code !== "string" ||
      payload.error.code.length === 0 ||
      typeof payload.error.message !== "string" ||
      payload.error.message.length === 0
    ) {
      return null;
    }
    return payload.error.message;
  }

  questionInput.addEventListener("input", updateSubmitState);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const trimmedQuestion = questionInput.value.trim();
    if (!trimmedQuestion || requestInProgress) {
      updateSubmitState();
      return;
    }

    requestInProgress = true;
    updateSubmitState();
    clearResponse();
    setStatus("loading", "Chargement de la réponse…");

    try {
      const response = await fetch("/questions", {
        method: "POST",
        credentials: "omit",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question: trimmedQuestion}),
      });
      const payload = await response.json();

      if (!response.ok) {
        const message = safeHttpMessage(payload);
        if (message === null) {
          throw new Error("invalid error payload");
        }
        setStatus("error", message);
        return;
      }
      if (!isPublicResponse(payload)) {
        throw new Error("invalid response payload");
      }

      setStatus(payload.status, statusLabels[payload.status]);
      answerOutput.textContent = payload.answer;
      dataOutput.textContent = JSON.stringify(payload.data, null, 2);
    } catch (_error) {
      clearResponse();
      setStatus("error", technicalError);
    } finally {
      requestInProgress = false;
      updateSubmitState();
    }
  });

  updateSubmitState();
})();
