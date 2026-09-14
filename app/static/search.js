(() => {
  const form = document.querySelector("#catalogue-search-form");
  if (!form) return;

  const input = document.querySelector("#catalogue-search-query");
  const submitButton = document.querySelector("#catalogue-search-submit");
  const buttonLabel = submitButton.querySelector("[data-search-button-label]");
  const spinner = submitButton.querySelector("[data-search-spinner]");
  const clearButton = document.querySelector("#catalogue-search-clear");
  const browseAllLink = document.querySelector("#browse-all-items");
  const suggestedQueryButtons = document.querySelectorAll("[data-suggested-query]");
  const status = document.querySelector("#search-status");
  const grid = document.querySelector("#listing-grid");
  const emptyState = document.querySelector("#catalogue-empty-state");
  const emptyHeading = emptyState.querySelector("[data-empty-heading]");
  const emptyDescription = emptyState.querySelector("[data-empty-description]");
  const heading = document.querySelector("#catalogue-heading");
  const cardTemplate = document.querySelector("#listing-card-template");
  const money = new Intl.NumberFormat("en-SG", { maximumFractionDigits: 0 });
  let activeRequest = null;
  let searchStateActive = false;
  let resetInProgress = false;

  function setStatus(message, state = "idle") {
    status.textContent = message;
    status.dataset.state = state;
  }

  function setLoading(isLoading) {
    submitButton.disabled = isLoading;
    input.setAttribute("aria-busy", String(isLoading));
    grid.setAttribute("aria-busy", String(isLoading));
    spinner.classList.toggle("hidden", !isLoading);
    buttonLabel.textContent = isLoading ? "Searching..." : "Find matches";
  }

  function returnToFullCatalogue() {
    if (resetInProgress) return;
    resetInProgress = true;

    if (activeRequest) {
      activeRequest.abort();
      activeRequest = null;
    }
    input.value = "";
    setLoading(false);
    window.history.replaceState(null, "", "/#listings");
    window.location.reload();
  }

  function populateCard(listing) {
    const card = cardTemplate.content.firstElementChild.cloneNode(true);
    const link = card.querySelector("[data-card-link]");
    const image = card.querySelector("[data-card-image]");
    const statusBadge = card.querySelector("[data-card-status]");
    const listingStatus = listing.status || "Available";
    const statusLabel = listingStatus === "Available" ? "" : `, status ${listingStatus}`;

    card.dataset.listingId = listing.id;
    card.dataset.listingStatus = listingStatus;
    link.href = `/listings/${encodeURIComponent(listing.id)}`;
    link.setAttribute(
      "aria-label",
      `View ${listing.title} for S$${money.format(listing.price)}${statusLabel}`,
    );
    image.src = listing.image;
    image.alt = `Illustration for ${listing.title}`;
    statusBadge.textContent = listingStatus;
    statusBadge.dataset.status = listingStatus;
    statusBadge.classList.toggle("hidden", listingStatus === "Available");
    card.querySelector("[data-card-category]").textContent = listing.category;
    card.querySelector("[data-card-condition]").textContent = listing.condition;
    card.querySelector("[data-card-title]").textContent = listing.title;
    card.querySelector("[data-card-description]").textContent = listing.description;
    card.querySelector("[data-card-price]").textContent = `S$${money.format(listing.price)}`;
    card.querySelector("[data-card-pickup]").textContent = listing.pickup_area;
    return card;
  }

  function renderResults(results, query) {
    searchStateActive = true;
    heading.textContent = "AI search matches";
    clearButton.classList.remove("hidden");

    if (results.length === 0) {
      grid.replaceChildren();
      grid.classList.add("hidden");
      emptyHeading.textContent = "No catalogue matches came back.";
      emptyDescription.textContent = "Try describing the project, tool or feature in a different way.";
      emptyState.classList.remove("hidden");
      setStatus(`No matches returned for “${query}”.`, "success");
      return;
    }

    const fragment = document.createDocumentFragment();
    results.forEach((listing) => fragment.appendChild(populateCard(listing)));
    grid.replaceChildren(fragment);
    grid.classList.remove("hidden");
    emptyState.classList.add("hidden");
    const noun = results.length === 1 ? "match" : "matches";
    setStatus(`${results.length} ${noun} for “${query}”, ranked by meaning.`, "success");
  }

  function providerMessage(code) {
    const messages = {
      search_not_configured: "AI search is not configured on this server. The catalogue below is still available.",
      search_timeout: "The AI search provider timed out. The catalogue below is unchanged; please try again.",
      search_model_unavailable: "The embedding model is currently unavailable through the AI provider. The catalogue below is unchanged.",
      search_gateway_unavailable: "The AI search provider is unavailable. The catalogue below is unchanged; please try again.",
    };
    return messages[code] || "AI search could not complete. The catalogue below is unchanged; please try again.";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = input.value.trim().replace(/\s+/g, " ");

    if (query.length === 0) {
      returnToFullCatalogue();
      return;
    }

    if (query.length < 2) {
      input.setCustomValidity("Enter at least 2 non-space characters.");
      input.setAttribute("aria-invalid", "true");
      input.reportValidity();
      setStatus("Enter at least 2 non-space characters to search.", "error");
      return;
    }

    input.setCustomValidity("");
    input.removeAttribute("aria-invalid");
    if (activeRequest) activeRequest.abort();
    const controller = new AbortController();
    activeRequest = controller;
    setLoading(true);
    setStatus("Embedding your request and comparing all 16 listings...", "loading");

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch (_) {
        // The generic failure state below remains truthful for a non-JSON response.
      }

      if (!response.ok) {
        if (response.status === 422) {
          input.setAttribute("aria-invalid", "true");
          throw new Error("validation");
        }
        const error = new Error("provider");
        error.code = payload.detail?.code;
        throw error;
      }
      if (!Array.isArray(payload.results)) throw new Error("invalid-response");

      renderResults(payload.results, payload.query || query);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.message === "validation") {
        setStatus("That search was not valid. Enter between 2 and 200 characters.", "error");
      } else if (error.message === "provider") {
        setStatus(providerMessage(error.code), "error");
      } else {
        setStatus("Maker Swap could not reach AI search. The catalogue below is unchanged; please try again.", "error");
      }
    } finally {
      if (activeRequest === controller) {
        activeRequest = null;
        setLoading(false);
      }
    }
  });

  input.addEventListener("input", () => {
    input.setCustomValidity("");
    input.removeAttribute("aria-invalid");

    if (input.value.trim().length === 0) {
      if (searchStateActive || activeRequest || window.location.search) {
        returnToFullCatalogue();
        return;
      }
      setStatus("");
    }
  });

  clearButton.addEventListener("click", () => {
    returnToFullCatalogue();
  });

  suggestedQueryButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const query = button.dataset.suggestedQuery;
      if (!query) return;
      input.value = query;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus({ preventScroll: true });
      form.requestSubmit();
    });
  });

  browseAllLink.addEventListener("click", (event) => {
    event.preventDefault();
    returnToFullCatalogue();
  });
})();
