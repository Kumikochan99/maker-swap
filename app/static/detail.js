document.addEventListener("DOMContentLoaded", () => {
  const backdrop = document.querySelector("[data-catalogue-backdrop]");
  const listingCard = document.querySelector("[data-listing-card]");

  if (!backdrop || !listingCard) {
    return;
  }

  backdrop.addEventListener("click", (event) => {
    if (listingCard.contains(event.target)) {
      return;
    }

    const interactiveTarget =
      event.target instanceof Element &&
      event.target.closest("a, button, input, select, textarea");

    if (interactiveTarget) {
      return;
    }

    window.location.assign(backdrop.dataset.catalogueUrl);
  });
});

