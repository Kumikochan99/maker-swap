(() => {
  const grid = document.querySelector("#listing-grid");
  const buttons = Array.from(
    document.querySelectorAll("[data-listing-view-button]"),
  );
  const status = document.querySelector("#listing-view-status");
  const storageKey = "maker-swap-listing-view";
  const validViews = new Set(["list", "gallery"]);

  if (!grid || buttons.length !== 2) return;

  function storedView() {
    try {
      const value = window.sessionStorage.getItem(storageKey);
      return validViews.has(value) ? value : "list";
    } catch (_) {
      return "list";
    }
  }

  function applyView(view, announce = false) {
    const normalizedView = validViews.has(view) ? view : "list";
    grid.dataset.listingView = normalizedView;
    buttons.forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.listingViewButton === normalizedView),
      );
    });

    if (announce && status) {
      status.textContent = `${normalizedView === "list" ? "List" : "Gallery"} view selected.`;
    }
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const requestedView = button.dataset.listingViewButton;
      applyView(requestedView, true);
      try {
        window.sessionStorage.setItem(storageKey, requestedView);
      } catch (_) {
        // The view still switches when browser storage is unavailable.
      }
    });
  });

  applyView(storedView());
})();
