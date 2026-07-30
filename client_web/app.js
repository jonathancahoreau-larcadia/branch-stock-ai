(() => {
  "use strict";

  const form = document.querySelector("#question-form");
  const questionInput = document.querySelector("#question");
  const submitButton = document.querySelector("#submit-button");
  const clearButton = document.querySelector("#clear-button");
  const conversationLog = document.querySelector("#conversation-log");
  const emptyState = document.querySelector("#empty-state");
  const characterCount = document.querySelector("#character-count");
  const requestStatus = document.querySelector("#request-status");
  const errorLive = document.querySelector("#error-live");
  const serviceStatus = document.querySelector("#service-status");
  const serviceStatusText = document.querySelector("#service-status-text");
  const exampleButtons = Array.from(
    document.querySelectorAll(".example-button")
  );

  const acceptedStatuses = new Set([
    "success",
    "partial",
    "unavailable",
    "unsupported",
  ]);
  const statusLabels = Object.freeze({
    success: "Réponse complète",
    partial: "Réponse partielle",
    unavailable: "Informations indisponibles",
    unsupported: "Question non comprise",
  });
  const errorMessages = Object.freeze({
    INVALID_JSON: "La requête envoyée n’a pas pu être lue.",
    VALIDATION_ERROR:
      "La question doit contenir entre 1 et 1 000 caractères.",
    MCP_ERROR: "Une source de données n’a pas pu répondre correctement.",
    MCP_UNAVAILABLE:
      "Les informations sur les produits ou les stocks sont indisponibles.",
    AI_PROVIDER_UNAVAILABLE:
      "Le service n’a pas pu comprendre les paramètres de la question.",
    UPSTREAM_TIMEOUT: "Le service a mis trop de temps à répondre.",
    INTERNAL_ERROR: "Le service a rencontré une erreur inattendue.",
  });
  const categoryTranslations = Object.freeze({
    Displays: "Écrans",
    displays: "Écrans",
    Monitors: "Écrans",
    monitors: "Écrans",
    Keyboards: "Claviers",
    keyboards: "Claviers",
  });
  const nameTranslations = Object.freeze({
    "24 inch Compact Monitor": "Écran compact 24 pouces",
    "Compact Monitor": "Écran compact",
  });
  const descriptionTranslations = Object.freeze({
    "A compact display.": "Un écran compact.",
    "A compact business display.":
      "Un écran compact pour un usage professionnel.",
    "Compact business monitor":
      "Écran compact pour un usage professionnel",
  });
  const strategyTranslations = Object.freeze({
    single_branch: "Une seule succursale",
    multiple_branches: "Plusieurs succursales",
    unavailable: "Indisponible",
  });
  const questionTypeTranslations = Object.freeze({
    product_details: "Détails d’un produit",
    product_availability: "Disponibilité d’un produit",
    branch_inventory: "Inventaire d’une succursale",
    shopping_list: "Liste d’achats",
  });
  const retryButtons = [];

  let requestInProgress = false;
  let messageCount = 0;

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function hasOwn(record, key) {
    return Object.prototype.hasOwnProperty.call(record, key);
  }

  function translated(dictionary, value) {
    if (
      typeof value === "string" &&
      Object.prototype.hasOwnProperty.call(dictionary, value)
    ) {
      return dictionary[value];
    }
    return value;
  }

  function createElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) {
      element.className = className;
    }
    if (text !== undefined) {
      element.textContent = String(text);
    }
    return element;
  }

  function formatTime(date) {
    return new Intl.DateTimeFormat("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function updateComposerState() {
    const length = questionInput.value.length;
    characterCount.textContent = `${length.toLocaleString("fr-FR")} / 1 000`;
    submitButton.disabled =
      requestInProgress || questionInput.value.trim().length === 0;
    clearButton.disabled = requestInProgress || messageCount === 0;
    for (const button of retryButtons) {
      button.disabled = requestInProgress;
    }
  }

  function setServiceState(state, text) {
    serviceStatus.className = `service-status service-status--${state}`;
    serviceStatus.dataset.state = state;
    serviceStatusText.textContent = text;
  }

  function announce(message, isError) {
    requestStatus.textContent = isError ? "" : message;
    errorLive.textContent = isError ? message : "";
  }

  function hideEmptyState() {
    emptyState.hidden = true;
  }

  function showEmptyState() {
    emptyState.hidden = false;
  }

  function scrollToLatest(element) {
    element.scrollIntoView({block: "nearest", behavior: "smooth"});
  }

  function createMessageShell(kind, label) {
    const message = createElement("article", `message message--${kind}`);
    const metadata = createElement("div", "message__meta");
    const author = createElement("span", "message__author", label);
    const time = createElement("time", "message__time", formatTime(new Date()));
    time.dateTime = new Date().toISOString();
    metadata.append(author, time);

    const bubble = createElement("div", "message__bubble");
    message.append(metadata, bubble);
    conversationLog.append(message);
    return {message, bubble};
  }

  function appendUserMessage(question) {
    hideEmptyState();
    const shell = createMessageShell("user", "Vous");
    shell.bubble.append(
      createElement("p", "message__answer", question)
    );
    messageCount += 1;
    updateComposerState();
    scrollToLatest(shell.message);
  }

  function appendLoadingMessage() {
    const shell = createMessageShell("assistant loading-message", "HBntory");
    const dots = createElement("span", "loading-dots");
    dots.setAttribute("aria-label", "Réponse en cours");
    dots.append(
      createElement("span"),
      createElement("span"),
      createElement("span")
    );
    shell.bubble.append(dots);
    scrollToLatest(shell.message);
    return shell.message;
  }

  function appendRetryAction(bubble, question) {
    const actions = createElement("div", "message__actions");
    const retry = createElement(
      "button",
      "retry-button",
      "Relancer cette question"
    );
    retry.type = "button";
    retry.setAttribute("aria-label", `Relancer la question : ${question}`);
    retry.addEventListener("click", () => {
      if (!requestInProgress) {
        submitQuestion(question);
      }
    });
    retryButtons.push(retry);
    actions.append(retry);
    bubble.append(actions);
  }

  function appendDetail(list, label, value, dictionary) {
    if (value === undefined || value === null || value === "") {
      return false;
    }
    const term = createElement("dt", "", label);
    const displayValue = dictionary ? translated(dictionary, value) : value;
    const description = createElement("dd", "", displayValue);
    list.append(term, description);
    return true;
  }

  function createTable(headers, rows) {
    const wrapper = createElement("div", "data-table-wrap");
    const table = createElement("table", "data-table");
    const head = createElement("thead");
    const headRow = createElement("tr");
    for (const header of headers) {
      headRow.append(createElement("th", "", header));
    }
    head.append(headRow);

    const body = createElement("tbody");
    for (const row of rows) {
      const tableRow = createElement("tr");
      for (const value of row) {
        tableRow.append(
          createElement(
            "td",
            "",
            value === undefined || value === null ? "" : value
          )
        );
      }
      body.append(tableRow);
    }
    table.append(head, body);
    wrapper.append(table);
    return wrapper;
  }

  function renderProductDetails(container, product) {
    if (!isRecord(product)) {
      return 0;
    }
    const card = createElement("section", "detail-card");
    const rawName = hasOwn(product, "name") ? product.name : undefined;
    const title = translated(nameTranslations, rawName);
    card.append(createElement("h4", "", title || "Produit"));
    const list = createElement("dl", "detail-list");
    let fields = 0;

    if (hasOwn(product, "external_product_id")) {
      fields += appendDetail(
        list,
        "SKU",
        product.external_product_id
      ) ? 1 : 0;
    }
    if (hasOwn(product, "name")) {
      fields += appendDetail(
        list,
        "Produit",
        product.name,
        nameTranslations
      ) ? 1 : 0;
    }
    if (hasOwn(product, "description")) {
      fields += appendDetail(
        list,
        "Description",
        product.description,
        descriptionTranslations
      ) ? 1 : 0;
    }
    if (hasOwn(product, "category")) {
      fields += appendDetail(
        list,
        "Catégorie",
        product.category,
        categoryTranslations
      ) ? 1 : 0;
    }
    for (const field of [
      ["brand", "Marque"],
      ["unit_price", "Prix"],
      ["currency", "Devise"],
      ["weight_kg", "Poids (kg)"],
      ["updated_at", "Dernière mise à jour"],
    ]) {
      if (hasOwn(product, field[0])) {
        fields += appendDetail(list, field[1], product[field[0]]) ? 1 : 0;
      }
    }
    if (hasOwn(product, "discontinued")) {
      const readableStatus = product.discontinued === true ? "Arrêté" : "Actif";
      fields += appendDetail(list, "Statut", readableStatus) ? 1 : 0;
    }
    if (Array.isArray(product.tags) && product.tags.length > 0) {
      fields += appendDetail(list, "Étiquettes", product.tags.join(", ")) ? 1 : 0;
    }
    if (isRecord(product.supplier)) {
      if (hasOwn(product.supplier, "name")) {
        fields += appendDetail(
          list,
          "Fournisseur",
          product.supplier.name
        ) ? 1 : 0;
      }
      if (hasOwn(product.supplier, "id")) {
        fields += appendDetail(
          list,
          "Code fournisseur",
          product.supplier.id
        ) ? 1 : 0;
      }
      for (const field of [
        ["country", "Pays fournisseur"],
        ["lead_time_days", "Délai fournisseur (jours)"],
        ["reliability_score", "Fiabilité fournisseur"],
      ]) {
        if (hasOwn(product.supplier, field[0])) {
          fields += appendDetail(
            list,
            field[1],
            product.supplier[field[0]]
          ) ? 1 : 0;
        }
      }
    }
    if (fields > 0) {
      card.append(list);
      container.append(card);
      return 1;
    }
    return 0;
  }

  function renderBranches(container, stock) {
    if (!isRecord(stock) || !Array.isArray(stock.branches)) {
      return 0;
    }
    const validBranches = stock.branches.filter(isRecord);
    if (validBranches.length === 0) {
      return 0;
    }
    const rows = validBranches.map((branch) => [
      hasOwn(branch, "branch_name") ? branch.branch_name : "",
      hasOwn(branch, "branch_id") ? branch.branch_id : "",
      hasOwn(branch, "quantity") ? branch.quantity : "",
    ]);
    const card = createElement("section", "detail-card");
    card.append(
      createElement("h4", "", "Disponibilité par succursale"),
      createTable(["Succursale", "Identifiant", "Quantité"], rows)
    );
    container.append(card);
    return 1;
  }

  function productNameMap(productsResult) {
    const names = new Map();
    if (!isRecord(productsResult) || !Array.isArray(productsResult.products)) {
      return names;
    }
    for (const product of productsResult.products) {
      if (
        isRecord(product) &&
        typeof product.external_product_id === "string" &&
        typeof product.name === "string"
      ) {
        names.set(
          product.external_product_id,
          translated(nameTranslations, product.name)
        );
      }
    }
    return names;
  }

  function renderBranchInventory(container, branch, names) {
    if (!isRecord(branch) || !Array.isArray(branch.stocks)) {
      return 0;
    }
    const card = createElement("section", "detail-card");
    const branchName = hasOwn(branch, "branch_name")
      ? branch.branch_name
      : "Succursale";
    card.append(createElement("h4", "", `Inventaire — ${branchName}`));
    const list = createElement("dl", "detail-list");
    let metadata = 0;
    if (hasOwn(branch, "branch_id")) {
      metadata += appendDetail(
        list,
        "Identifiant de succursale",
        branch.branch_id
      ) ? 1 : 0;
    }
    if (metadata > 0) {
      card.append(list);
    }

    const stocks = branch.stocks.filter(isRecord);
    if (stocks.length > 0) {
      const rows = stocks.map((stock) => {
        const identifier = hasOwn(stock, "external_product_id")
          ? stock.external_product_id
          : "";
        return [
          names.get(identifier) || "",
          identifier,
          hasOwn(stock, "quantity") ? stock.quantity : "",
        ];
      });
      card.append(createTable(["Produit", "SKU", "Quantité"], rows));
    }
    container.append(card);
    return 1;
  }

  function renderProductList(container, productsResult) {
    if (!isRecord(productsResult) || !Array.isArray(productsResult.products)) {
      return 0;
    }
    const products = productsResult.products.filter(isRecord);
    if (products.length === 0) {
      return 0;
    }
    const rows = products.map((product) => [
      hasOwn(product, "name")
        ? translated(nameTranslations, product.name)
        : "",
      hasOwn(product, "external_product_id")
        ? product.external_product_id
        : "",
    ]);
    const card = createElement("section", "detail-card");
    card.append(
      createElement("h4", "", "Produits"),
      createTable(["Produit", "SKU"], rows)
    );
    container.append(card);
    return 1;
  }

  function renderShoppingPlan(container, plan) {
    if (!isRecord(plan)) {
      return 0;
    }
    const card = createElement("section", "detail-card");
    card.append(createElement("h4", "", "Plan d’achat"));
    const list = createElement("dl", "detail-list");
    let hasDetails = false;
    if (hasOwn(plan, "strategy")) {
      hasDetails = appendDetail(
        list,
        "Stratégie",
        plan.strategy,
        strategyTranslations
      ) || hasDetails;
    }
    if (hasOwn(plan, "complete")) {
      hasDetails = appendDetail(
        list,
        "État",
        plan.complete === true ? "Complet" : "Incomplet"
      ) || hasDetails;
    }
    if (hasDetails) {
      card.append(list);
    }

    if (Array.isArray(plan.visits)) {
      for (const visit of plan.visits.filter(isRecord)) {
        if (!Array.isArray(visit.items)) {
          continue;
        }
        const visitName = hasOwn(visit, "branch_name")
          ? visit.branch_name
          : "Succursale";
        const visitId = hasOwn(visit, "branch_id")
          ? ` — ${visit.branch_id}`
          : "";
        card.append(
          createElement("h4", "", `${visitName}${visitId}`)
        );
        const rows = visit.items.filter(isRecord).map((item) => [
          hasOwn(item, "external_product_id")
            ? item.external_product_id
            : "",
          hasOwn(item, "requested_quantity")
            ? item.requested_quantity
            : "",
          hasOwn(item, "available_quantity")
            ? item.available_quantity
            : "",
        ]);
        if (rows.length > 0) {
          card.append(
            createTable(["SKU", "Demandée", "Disponible"], rows)
          );
        }
      }
    }
    if (Array.isArray(plan.missing_items) && plan.missing_items.length > 0) {
      const rows = plan.missing_items.filter(isRecord).map((item) => [
        hasOwn(item, "external_product_id")
          ? item.external_product_id
          : "",
        hasOwn(item, "missing_quantity") ? item.missing_quantity : "",
      ]);
      if (rows.length > 0) {
        card.append(
          createElement("h4", "", "Articles manquants"),
          createTable(["SKU", "Quantité manquante"], rows)
        );
      }
    }
    container.append(card);
    return 1;
  }

  function renderSupportedTypes(container, types) {
    if (!Array.isArray(types) || types.length === 0) {
      return 0;
    }
    const card = createElement("section", "detail-card");
    card.append(createElement("h4", "", "Questions prises en charge"));
    const list = createElement("ul", "help-list");
    for (const type of types) {
      list.append(
        createElement(
          "li",
          "",
          translated(questionTypeTranslations, type)
        )
      );
    }
    card.append(list);
    container.append(card);
    return 1;
  }

  function renderStructuredData(bubble, data) {
    if (!isRecord(data)) {
      return 0;
    }
    const details = createElement("div", "structured-details");
    details.append(createElement("h3", "", "Détails"));
    let sections = 0;
    const tools = isRecord(data.tool_results) ? data.tool_results : {};

    if (isRecord(tools.get_product_details)) {
      sections += renderProductDetails(details, tools.get_product_details);
    }
    if (isRecord(tools.get_stock_for_product)) {
      sections += renderBranches(details, tools.get_stock_for_product);
    }
    const names = productNameMap(tools.list_products);
    if (isRecord(tools.list_branch_stock)) {
      sections += renderBranchInventory(
        details,
        tools.list_branch_stock,
        names
      );
    } else if (isRecord(tools.list_products)) {
      sections += renderProductList(details, tools.list_products);
    }
    if (isRecord(tools.find_branches_for_shopping_list)) {
      sections += renderShoppingPlan(
        details,
        tools.find_branches_for_shopping_list
      );
    }
    if (Array.isArray(data.supported_question_types)) {
      sections += renderSupportedTypes(
        details,
        data.supported_question_types
      );
    }
    if (sections > 0) {
      bubble.append(details);
    }
    return sections;
  }

  function appendAssistantResponse(payload, question) {
    const shell = createMessageShell("assistant", "HBntory");
    const badge = createElement(
      "span",
      `message__status message__status--${payload.status}`,
      statusLabels[payload.status]
    );
    const answer = payload.answer.trim()
      ? payload.answer
      : "Le service n’a retourné aucun texte pour cette question.";
    shell.bubble.append(
      badge,
      createElement("p", "message__answer", answer)
    );
    if (renderStructuredData(shell.bubble, payload.data) === 0) {
      shell.bubble.append(
        createElement(
          "p",
          "empty-details",
          "Aucun détail structuré supplémentaire."
        )
      );
    }
    appendRetryAction(shell.bubble, question);
    messageCount += 1;
    updateComposerState();
    scrollToLatest(shell.message);
  }

  function appendErrorMessage(message, question) {
    const shell = createMessageShell(
      "assistant message--error",
      "HBntory"
    );
    shell.bubble.append(
      createElement(
        "span",
        "message__status message__status--error",
        "Erreur"
      ),
      createElement("p", "message__answer", message)
    );
    appendRetryAction(shell.bubble, question);
    messageCount += 1;
    updateComposerState();
    scrollToLatest(shell.message);
  }

  function isPublicResponse(payload) {
    return (
      isRecord(payload) &&
      acceptedStatuses.has(payload.status) &&
      typeof payload.answer === "string" &&
      isRecord(payload.data)
    );
  }

  function publicErrorCode(payload) {
    if (
      !isRecord(payload) ||
      !isRecord(payload.error) ||
      typeof payload.error.code !== "string"
    ) {
      return null;
    }
    return hasOwn(errorMessages, payload.error.code)
      ? payload.error.code
      : null;
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  async function submitQuestion(question) {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion || requestInProgress) {
      updateComposerState();
      return;
    }

    requestInProgress = true;
    appendUserMessage(normalizedQuestion);
    questionInput.value = "";
    updateComposerState();
    announce("Question envoyée. Réponse en cours.", false);
    const loadingMessage = appendLoadingMessage();

    try {
      const response = await fetch("/questions", {
        method: "POST",
        credentials: "omit",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question: normalizedQuestion}),
      });
      const payload = await readJson(response);
      loadingMessage.remove();

      if (!response.ok) {
        const code = publicErrorCode(payload);
        const message = code
          ? errorMessages[code]
          : "Le service n’a pas pu traiter la question.";
        appendErrorMessage(message, normalizedQuestion);
        announce(message, true);
        setServiceState(
          response.status >= 500 ? "unavailable" : "available",
          response.status >= 500 ? "Service indisponible" : "Service disponible"
        );
        return;
      }
      if (!isPublicResponse(payload)) {
        const message = "La réponse reçue ne peut pas être affichée.";
        appendErrorMessage(message, normalizedQuestion);
        announce(message, true);
        setServiceState("unavailable", "Service indisponible");
        return;
      }

      appendAssistantResponse(payload, normalizedQuestion);
      announce(statusLabels[payload.status], false);
      setServiceState("available", "Service disponible");
    } catch (_error) {
      loadingMessage.remove();
      const message =
        "Impossible de joindre le service. Vérifiez votre connexion locale puis réessayez.";
      appendErrorMessage(message, normalizedQuestion);
      announce(message, true);
      setServiceState("unavailable", "Service indisponible");
    } finally {
      requestInProgress = false;
      updateComposerState();
    }
  }

  async function checkHealth() {
    setServiceState("checking", "Vérification du service…");
    try {
      const response = await fetch("/health", {
        method: "GET",
        credentials: "omit",
        headers: {"Accept": "application/json"},
      });
      const payload = await readJson(response);
      if (
        response.ok &&
        isRecord(payload) &&
        payload.status === "ok"
      ) {
        setServiceState("available", "Service disponible");
        return;
      }
    } catch (_error) {
      // L’état visuel est mis à jour ci-dessous sans exposer le détail réseau.
    }
    setServiceState("unavailable", "Service indisponible");
  }

  questionInput.addEventListener("input", updateComposerState);
  questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.ctrlKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitQuestion(questionInput.value);
  });

  clearButton.addEventListener("click", () => {
    if (requestInProgress) {
      return;
    }
    for (const message of Array.from(
      conversationLog.querySelectorAll(".message")
    )) {
      message.remove();
    }
    retryButtons.length = 0;
    messageCount = 0;
    questionInput.value = "";
    showEmptyState();
    updateComposerState();
    announce("Conversation effacée.", false);
    questionInput.focus();
  });

  for (const button of exampleButtons) {
    button.addEventListener("click", () => {
      questionInput.value = button.dataset.question || "";
      updateComposerState();
      questionInput.focus();
    });
  }

  updateComposerState();
  checkHealth();
})();
