document.addEventListener("DOMContentLoaded", () => {
  const nav = document.querySelector(".site-glass-nav");
  const menu = document.querySelector("#site-category-menu");
  const menuToggle = document.querySelector("#category-menu-toggle");

  if (menu instanceof HTMLDetailsElement && menuToggle) {
    const syncExpandedState = () => {
      menuToggle.setAttribute("aria-expanded", String(menu.open));
    };

    menu.addEventListener("toggle", syncExpandedState);

    document.addEventListener("click", (event) => {
      if (
        menu.open &&
        event.target instanceof Node &&
        !menu.contains(event.target)
      ) {
        menu.open = false;
      }
    });

    menu.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !menu.open) return;
      event.preventDefault();
      menu.open = false;
      menuToggle.focus();
    });

    menu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        menu.open = false;
      });
    });

    syncExpandedState();
  }

  const navSearchForm = document.querySelector("[data-nav-search-form]");
  const navSearchInput = document.querySelector("#nav-search-query");
  const navSearchToggle = document.querySelector("[data-nav-search-toggle]");
  const navSearchClose = document.querySelector("[data-nav-search-close]");
  const mainSearchForm = document.querySelector("#catalogue-search-form");
  const mainSearchInput = document.querySelector("#catalogue-search-query");
  const mainSearchPanel = document.querySelector("#catalogue-search");

  if (
    !nav ||
    !(navSearchForm instanceof HTMLFormElement) ||
    !(navSearchInput instanceof HTMLInputElement) ||
    !(navSearchToggle instanceof HTMLButtonElement) ||
    !(navSearchClose instanceof HTMLButtonElement)
  ) {
    return;
  }

  const normalizedQuery = () =>
    navSearchInput.value.trim().replace(/\s+/g, " ");

  const setMobileSearchOpen = (isOpen, restoreToggleFocus = false) => {
    nav.classList.toggle("nav-search-expanded", isOpen);
    navSearchToggle.setAttribute("aria-expanded", String(isOpen));
    if (isOpen) {
      if (menu instanceof HTMLDetailsElement) menu.open = false;
      navSearchInput.focus();
    } else if (restoreToggleFocus) {
      navSearchToggle.focus();
    }
  };

  const submitThroughMainSearch = (query) => {
    if (
      !(mainSearchForm instanceof HTMLFormElement) ||
      !(mainSearchInput instanceof HTMLInputElement) ||
      !mainSearchPanel
    ) {
      return false;
    }

    mainSearchInput.value = query;
    mainSearchInput.focus({ preventScroll: true });
    setMobileSearchOpen(false);
    mainSearchPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    mainSearchForm.requestSubmit();
    return true;
  };

  navSearchToggle.addEventListener("click", () => {
    setMobileSearchOpen(true);
  });

  navSearchClose.addEventListener("click", () => {
    setMobileSearchOpen(false, true);
  });

  navSearchInput.addEventListener("input", () => {
    navSearchInput.setCustomValidity("");
    navSearchInput.removeAttribute("aria-invalid");
  });

  navSearchInput.addEventListener("keydown", (event) => {
    if (
      event.key !== "Escape" ||
      !nav.classList.contains("nav-search-expanded")
    ) {
      return;
    }
    event.preventDefault();
    setMobileSearchOpen(false, true);
  });

  navSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = normalizedQuery();

    if (query.length < 2) {
      navSearchInput.setCustomValidity("Enter at least 2 non-space characters.");
      navSearchInput.setAttribute("aria-invalid", "true");
      navSearchInput.reportValidity();
      return;
    }

    navSearchInput.setCustomValidity("");
    navSearchInput.removeAttribute("aria-invalid");
    navSearchInput.value = query;

    if (submitThroughMainSearch(query)) return;

    const destination = new URL(navSearchForm.action, window.location.origin);
    destination.searchParams.set("nav_query", query);
    destination.hash = "catalogue-search";
    window.location.assign(destination.href);
  });

  document.addEventListener("click", (event) => {
    if (
      nav.classList.contains("nav-search-expanded") &&
      event.target instanceof Node &&
      !nav.contains(event.target)
    ) {
      setMobileSearchOpen(false);
    }
  });

  const destinationQuery = new URLSearchParams(window.location.search).get(
    "nav_query",
  );
  if (destinationQuery) {
    const query = destinationQuery.trim().replace(/\s+/g, " ");
    if (query.length >= 2 && submitThroughMainSearch(query)) {
      navSearchInput.value = query;
      const cleanedUrl = new URL(window.location.href);
      cleanedUrl.searchParams.delete("nav_query");
      cleanedUrl.hash = "catalogue-search";
      window.history.replaceState(
        null,
        "",
        `${cleanedUrl.pathname}${cleanedUrl.search}${cleanedUrl.hash}`,
      );
    }
  }
});
