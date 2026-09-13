(() => {
  const carousel = document.querySelector("[data-featured-carousel]");
  if (!carousel) return;

  const track = carousel.querySelector("[data-featured-track]");
  const slides = Array.from(carousel.querySelectorAll("[data-featured-slide]"));
  const previousButton = carousel.querySelector("[data-featured-previous]");
  const nextButton = carousel.querySelector("[data-featured-next]");
  const currentLabel = carousel.querySelector("[data-featured-current]");
  const status = carousel.querySelector("[data-featured-status]");
  const intervalMs = Number.parseInt(carousel.dataset.intervalMs || "", 10);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  if (
    !track ||
    slides.length < 2 ||
    !previousButton ||
    !nextButton ||
    !Number.isFinite(intervalMs)
  ) {
    return;
  }

  let activeIndex = 0;
  let timerId = null;
  let pointerInside = false;
  let focusInside = false;

  function normalizedIndex(index) {
    return (index + slides.length) % slides.length;
  }

  function updateAutoState() {
    const paused =
      pointerInside || focusInside || document.hidden || reducedMotion.matches;
    carousel.dataset.autoState = paused ? "paused" : "running";
    return !paused;
  }

  function stopTimer() {
    if (timerId !== null) {
      window.clearTimeout(timerId);
      timerId = null;
    }
  }

  function render(index, announce = false) {
    activeIndex = normalizedIndex(index);
    track.style.transform = `translate3d(-${activeIndex * 100}%, 0, 0)`;
    track.dataset.activeIndex = String(activeIndex);

    slides.forEach((slide, slideIndex) => {
      const isActive = slideIndex === activeIndex;
      slide.setAttribute("aria-hidden", String(!isActive));
      const link = slide.querySelector("[data-featured-link]");
      if (link) {
        if (isActive) link.removeAttribute("tabindex");
        else link.setAttribute("tabindex", "-1");
      }
    });

    if (currentLabel) currentLabel.textContent = String(activeIndex + 1);
    if (announce && status) {
      const title = slides[activeIndex].querySelector("h3")?.textContent?.trim();
      status.textContent = `Showing featured listing ${activeIndex + 1} of ${slides.length}${title ? `: ${title}` : "."}`;
    }
  }

  function scheduleNext() {
    stopTimer();
    if (!updateAutoState()) return;
    timerId = window.setTimeout(() => {
      render(activeIndex + 1);
      scheduleNext();
    }, intervalMs);
  }

  function showPrevious() {
    render(activeIndex - 1, true);
    scheduleNext();
  }

  function showNext() {
    render(activeIndex + 1, true);
    scheduleNext();
  }

  previousButton.addEventListener("click", showPrevious);
  nextButton.addEventListener("click", showNext);

  carousel.addEventListener("mouseenter", () => {
    pointerInside = true;
    stopTimer();
    updateAutoState();
  });

  carousel.addEventListener("mouseleave", () => {
    pointerInside = false;
    scheduleNext();
  });

  carousel.addEventListener("focusin", () => {
    focusInside = true;
    stopTimer();
    updateAutoState();
  });

  carousel.addEventListener("focusout", () => {
    window.setTimeout(() => {
      focusInside = carousel.contains(document.activeElement);
      scheduleNext();
    }, 0);
  });

  document.addEventListener("visibilitychange", scheduleNext);
  reducedMotion.addEventListener("change", scheduleNext);

  render(0);
  scheduleNext();
})();
