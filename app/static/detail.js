document.addEventListener("DOMContentLoaded", () => {
  const backdrop = document.querySelector("[data-catalogue-backdrop]");
  const listingCard = document.querySelector("[data-listing-card]");

  if (backdrop && listingCard) {
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
  }

  document.querySelectorAll("[data-gallery]").forEach((gallery) => {
    const mainImage = gallery.querySelector("[data-gallery-main]");
    const previousButton = gallery.querySelector("[data-gallery-previous]");
    const nextButton = gallery.querySelector("[data-gallery-next]");
    const counter = gallery.querySelector("[data-gallery-counter]");
    const liveRegion = gallery.querySelector("[data-gallery-live]");
    const thumbnails = Array.from(
      gallery.querySelectorAll("[data-gallery-thumbnail]"),
    );

    if (!(mainImage instanceof HTMLImageElement) || thumbnails.length === 0) return;

    let currentIndex = Math.max(
      0,
      thumbnails.findIndex((thumbnail) => thumbnail.getAttribute("aria-pressed") === "true"),
    );

    const showImage = (requestedIndex, options = {}) => {
      const index = (requestedIndex + thumbnails.length) % thumbnails.length;
      const activeThumbnail = thumbnails[index];
      currentIndex = index;
      mainImage.src = activeThumbnail.dataset.gallerySrc;
      mainImage.alt = `Illustrated view ${index + 1} of ${thumbnails.length} for ${document.querySelector("h1")?.textContent.trim() || "this listing"}`;

      thumbnails.forEach((thumbnail, thumbnailIndex) => {
        const isActive = thumbnailIndex === index;
        thumbnail.classList.toggle("is-active", isActive);
        thumbnail.setAttribute("aria-pressed", String(isActive));
      });

      if (counter) counter.textContent = `${index + 1} / ${thumbnails.length}`;
      if (liveRegion && options.announce !== false) {
        liveRegion.textContent = `Showing illustrated view ${index + 1} of ${thumbnails.length}`;
      }
      if (options.focusThumbnail) activeThumbnail.focus();
    };

    previousButton?.addEventListener("click", () => showImage(currentIndex - 1));
    nextButton?.addEventListener("click", () => showImage(currentIndex + 1));

    thumbnails.forEach((thumbnail, index) => {
      thumbnail.addEventListener("click", () => showImage(index));
      thumbnail.addEventListener("keydown", (event) => {
        const keyboardTargets = {
          ArrowLeft: currentIndex - 1,
          ArrowRight: currentIndex + 1,
          Home: 0,
          End: thumbnails.length - 1,
        };
        if (!(event.key in keyboardTargets)) return;
        event.preventDefault();
        showImage(keyboardTargets[event.key], { focusThumbnail: true });
      });
    });

    showImage(currentIndex, { announce: false });
  });
});
