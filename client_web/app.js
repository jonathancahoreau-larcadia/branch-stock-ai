(() => {
  "use strict";

  const form = document.querySelector("#shopping-form");
  const listElement = document.querySelector("#shopping-list");
  const message = document.querySelector("#message");
  const generateButton = document.querySelector("#generate-button");
  const clearButton = document.querySelector("#clear-button");
  const summaryOutput = document.querySelector("#summary-output");

  const items = [];

  function render() {
    listElement.replaceChildren();

    if (!items.length) {
      const empty = document.createElement("li");
      empty.textContent = "La liste est vide.";
      listElement.append(empty);
      return;
    }

    items.forEach((item, index) => {
      const row = document.createElement("li");
      row.className = "shopping-item";

      const label = document.createElement("span");
      label.textContent = `${item.quantity} × ${item.name}`;

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.textContent = "Retirer";
      removeButton.addEventListener("click", () => {
        items.splice(index, 1);
        render();
        summaryOutput.textContent = "";
      });

      row.append(label, removeButton);
      listElement.append(row);
    });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();

    const formData = new FormData(form);
    const name = String(formData.get("product_name") ?? "").trim();
    const quantity = Number(formData.get("quantity"));

    if (!name || !Number.isInteger(quantity) || quantity < 1) {
      message.textContent = "Produit et quantité positive obligatoires.";
      return;
    }

    const existing = items.find(
      (item) => item.name.toLocaleLowerCase("fr") === name.toLocaleLowerCase("fr")
    );

    if (existing) {
      existing.quantity += quantity;
    } else {
      items.push({ name, quantity });
    }

    form.reset();
    document.querySelector("#product-quantity").value = "1";
    message.textContent = "Produit ajouté.";
    summaryOutput.textContent = "";
    render();
  });

  generateButton.addEventListener("click", () => {
    if (!items.length) {
      summaryOutput.textContent = "Ajoutez au moins un produit.";
      return;
    }

    summaryOutput.textContent = [
      "Liste prête pour la future requête Personne 2 :",
      ...items.map((item) => `- ${item.quantity} × ${item.name}`),
      "",
      "Aucun appel IA n’est effectué avant l’autorisation de Personne 2.",
    ].join("\n");
  });

  clearButton.addEventListener("click", () => {
    items.splice(0, items.length);
    message.textContent = "Liste vidée.";
    summaryOutput.textContent = "";
    render();
  });

  render();
})();
