document.addEventListener("DOMContentLoaded", () => {
  const menu = document.querySelector("#site-category-menu");
  const toggle = document.querySelector("#category-menu-toggle");

  if (!(menu instanceof HTMLDetailsElement) || !toggle) return;

  const syncExpandedState = () => {
    toggle.setAttribute("aria-expanded", String(menu.open));
  };

  menu.addEventListener("toggle", syncExpandedState);

  document.addEventListener("click", (event) => {
    if (menu.open && event.target instanceof Node && !menu.contains(event.target)) {
      menu.open = false;
    }
  });

  menu.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !menu.open) return;
    event.preventDefault();
    menu.open = false;
    toggle.focus();
  });

  menu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      menu.open = false;
    });
  });

  syncExpandedState();
});
