(() => {
  const widget = document.querySelector("[data-chat-widget]");
  if (!widget) return;

  const panel = document.querySelector("#catalogue-chat-panel");
  const toggleButton = document.querySelector("#catalogue-chat-toggle");
  const closeButton = document.querySelector("#catalogue-chat-close");
  const form = document.querySelector("#catalogue-chat-form");
  const questionInput = document.querySelector("#catalogue-chat-question");
  const submitButton = document.querySelector("#catalogue-chat-submit");
  const submitLabel = submitButton?.querySelector("[data-chat-submit-label]");
  const spinner = submitButton?.querySelector("[data-chat-spinner]");
  const status = document.querySelector("#catalogue-chat-status");
  const emptyState = document.querySelector("#catalogue-chat-empty");
  const suggestedQuestionButtons = emptyState?.querySelectorAll(
    "[data-suggested-question]",
  );
  const messageLog = document.querySelector("#catalogue-chat-messages");
  const scrollRegion = document.querySelector(".catalogue-chat-scroll");

  if (
    !panel ||
    !toggleButton ||
    !closeButton ||
    !form ||
    !questionInput ||
    !submitButton ||
    !submitLabel ||
    !spinner ||
    !status ||
    !emptyState ||
    !suggestedQuestionButtons ||
    !messageLog ||
    !scrollRegion
  ) {
    return;
  }

  const STORAGE_KEY = "maker-swap:catalogue-chat:v2";
  const MAX_STORED_MESSAGES = 12;
  const MAX_HISTORY_MESSAGES = 8;
  const MAX_MESSAGE_LENGTH = 2000;
  let storageAvailable = true;
  let activeRequest = null;

  function cleanMessage(candidate) {
    if (!candidate || !["user", "assistant"].includes(candidate.role)) return null;
    if (typeof candidate.content !== "string") return null;

    const content = candidate.content.trim().slice(0, MAX_MESSAGE_LENGTH);
    if (!content) return null;

    const sources = Array.isArray(candidate.sources)
      ? candidate.sources
          .filter(
            (source) =>
              source &&
              typeof source.id === "string" &&
              typeof source.title === "string" &&
              source.id.length > 0 &&
              source.title.length > 0,
          )
          .slice(0, 4)
          .map((source) => ({
            id: source.id.slice(0, 100),
            title: source.title.slice(0, 160),
          }))
      : [];

    return { role: candidate.role, content, sources };
  }

  function loadMessages() {
    try {
      const saved = window.sessionStorage.getItem(STORAGE_KEY);
      if (!saved) return [];
      const parsed = JSON.parse(saved);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .map(cleanMessage)
        .filter(Boolean)
        .slice(-MAX_STORED_MESSAGES);
    } catch (_) {
      storageAvailable = false;
      return [];
    }
  }

  let messages = loadMessages();

  function saveMessages() {
    if (!storageAvailable) return;
    try {
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch (_) {
      storageAvailable = false;
      setStatus(
        "This browser blocked session storage, so this conversation cannot persist across pages.",
        "error",
      );
    }
  }

  function setStatus(message, state = "idle") {
    status.textContent = message;
    status.dataset.state = state;
  }

  function createMessageElement(message) {
    const article = document.createElement("article");
    article.className = "catalogue-chat-message";
    article.dataset.role = message.role;

    const label = document.createElement("span");
    label.className = "catalogue-chat-message-label";
    label.textContent = message.role === "user" ? "You" : "Maker Swap AI";

    const copy = document.createElement("p");
    copy.className = "catalogue-chat-message-copy";
    copy.textContent = message.content;

    article.append(label, copy);

    if (message.role === "assistant" && message.sources.length > 0) {
      const sources = document.createElement("nav");
      sources.className = "catalogue-chat-sources";
      sources.setAttribute("aria-label", "Listings referenced in this answer");

      message.sources.forEach((source) => {
        const link = document.createElement("a");
        link.className = "catalogue-chat-source";
        link.href = `/listings/${encodeURIComponent(source.id)}`;
        link.textContent = source.title;
        sources.appendChild(link);
      });

      article.appendChild(sources);
    }

    return article;
  }

  function renderConversation() {
    const fragment = document.createDocumentFragment();
    messages.forEach((message) => fragment.appendChild(createMessageElement(message)));
    messageLog.replaceChildren(fragment);
    emptyState.classList.toggle("hidden", messages.length > 0);
    scrollRegion.scrollTop = scrollRegion.scrollHeight;
  }

  function addMessage(message) {
    const cleaned = cleanMessage(message);
    if (!cleaned) return;
    messages = [...messages, cleaned].slice(-MAX_STORED_MESSAGES);
    saveMessages();
    renderConversation();
  }

  function setOpen(isOpen, returnFocus = false) {
    panel.hidden = !isOpen;
    toggleButton.setAttribute("aria-expanded", String(isOpen));
    toggleButton.setAttribute(
      "aria-label",
      isOpen ? "Close catalogue chat" : "Open catalogue chat",
    );
    document.body.classList.toggle("catalogue-chat-open", isOpen);

    if (isOpen) {
      window.requestAnimationFrame(() => {
        scrollRegion.scrollTop = scrollRegion.scrollHeight;
        questionInput.focus();
      });
    } else if (returnFocus) {
      toggleButton.focus();
    }
  }

  function setLoading(isLoading) {
    submitButton.disabled = isLoading;
    questionInput.disabled = isLoading;
    questionInput.setAttribute("aria-busy", String(isLoading));
    spinner.classList.toggle("hidden", !isLoading);
    submitLabel.textContent = isLoading ? "Checking catalogue..." : "Ask the catalogue";
  }

  function providerMessage(payload, responseStatus) {
    const serverMessage = payload?.detail?.message;
    if (typeof serverMessage === "string" && serverMessage.trim()) {
      return serverMessage;
    }
    if (responseStatus === 422) {
      return "That question was not valid. Enter between 2 and 500 characters.";
    }
    return "Catalogue Q&A could not reach the AI provider. Please try again.";
  }

  function userFacingError(message) {
    const error = new Error(message);
    error.isUserFacing = true;
    return error;
  }

  toggleButton.addEventListener("click", () => {
    setOpen(panel.hidden);
  });

  closeButton.addEventListener("click", () => {
    setOpen(false, true);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      setOpen(false, true);
    }
  });

  questionInput.addEventListener("input", () => {
    questionInput.setCustomValidity("");
    questionInput.removeAttribute("aria-invalid");
    if (status.dataset.state === "error") setStatus("");
  });

  questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  suggestedQuestionButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const question = button.dataset.suggestedQuestion;
      if (!question || activeRequest) return;
      questionInput.value = question;
      questionInput.dispatchEvent(new Event("input", { bubbles: true }));
      form.requestSubmit();
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (activeRequest) return;

    const question = questionInput.value.trim().replace(/\s+/g, " ");
    if (question.length < 2) {
      questionInput.setCustomValidity("Enter at least 2 non-space characters.");
      questionInput.setAttribute("aria-invalid", "true");
      questionInput.reportValidity();
      setStatus("Enter at least 2 non-space characters.", "error");
      return;
    }

    const history = messages.slice(-MAX_HISTORY_MESSAGES).map((message) => ({
      role: message.role,
      content: message.content,
    }));
    addMessage({ role: "user", content: question, sources: [] });
    questionInput.value = "";
    questionInput.setCustomValidity("");
    questionInput.removeAttribute("aria-invalid");

    const controller = new AbortController();
    activeRequest = controller;
    setLoading(true);
    setStatus("Reading all 16 listings and asking gpt-4o-mini...", "loading");

    try {
      const response = await fetch("/api/qa", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question, history }),
        signal: controller.signal,
      });

      let payload = {};
      try {
        payload = await response.json();
      } catch (_) {
        // A clear generic provider error is shown below for non-JSON failures.
      }

      if (!response.ok) {
        throw userFacingError(providerMessage(payload, response.status));
      }
      if (
        typeof payload.answer !== "string" ||
        !payload.answer.trim() ||
        !Array.isArray(payload.sources)
      ) {
        throw userFacingError("The AI provider returned an invalid response. Please try again.");
      }

      addMessage({
        role: "assistant",
        content: payload.answer,
        sources: payload.sources,
      });
      const sourceCount = payload.sources.length;
      setStatus(
        sourceCount > 0
          ? `Checked all 16 listings; linked ${sourceCount} directly referenced ${sourceCount === 1 ? "listing" : "listings"}.`
          : "Answered after checking all 16 catalogue listings.",
        "success",
      );
    } catch (error) {
      if (error.name === "AbortError") return;
      setStatus(
        error instanceof Error && error.isUserFacing
          ? error.message
          : "Catalogue Q&A could not reach the AI provider. Please try again.",
        "error",
      );
    } finally {
      if (activeRequest === controller) {
        activeRequest = null;
        setLoading(false);
      }
    }
  });

  renderConversation();
  setOpen(false);
  if (!storageAvailable) {
    setStatus(
      "This browser blocked session storage, so this conversation cannot persist across pages.",
      "error",
    );
  }
})();
