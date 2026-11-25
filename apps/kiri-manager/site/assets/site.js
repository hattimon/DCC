const root = document.documentElement;
const el = (id) => document.getElementById(id);
const buttons = [...document.querySelectorAll("[data-shot]")];
const lightbox = el("lightbox");
let index = 0;
let origin = null;
let startX = null;

function remember(key, value) {
  try { localStorage.setItem("dcc-kiri-site." + key, value); } catch { /* optional preference */ }
}

function preference(key) {
  try { return localStorage.getItem("dcc-kiri-site." + key); } catch { return null; }
}

const languageLink = document.querySelector("[data-language]");
languageLink.addEventListener("click", () => remember("language", languageLink.dataset.language));
if (preference("language") === "pl" && root.lang === "en" && !location.hash) location.replace(languageLink.href);

function theme(value) {
  const light = value === "light";
  root.dataset.theme = light ? "light" : "dark";
  el("theme").setAttribute("aria-pressed", String(light));
  el("theme").textContent = light ? "☀" : "☾";
  const hero = el("hero-image");
  const image = hero.dataset[light ? "light" : "dark"];
  if (hero.getAttribute("src") !== image) hero.setAttribute("src", image);
}
theme(preference("theme") === "light" ? "light" : "dark");
el("theme").addEventListener("click", () => {
  const value = root.dataset.theme === "light" ? "dark" : "light";
  remember("theme", value);
  theme(value);
});

function menu(open) {
  el("menu").setAttribute("aria-expanded", String(open));
  el("navigation").classList.toggle("open", open);
}
el("menu").addEventListener("click", () => menu(el("menu").getAttribute("aria-expanded") !== "true"));
el("navigation").addEventListener("click", (event) => {
  if (event.target.closest("a")) menu(false);
});

function show(n) {
  index = (n + buttons.length) % buttons.length;
  const {src, caption} = buttons[index].dataset;
  el("shot-title").textContent = caption;
  el("large").src = src;
  el("large").alt = caption + " · DEMO";
  el("number").textContent = (index + 1) + " / " + buttons.length;
}
buttons.forEach((button, n) => button.addEventListener("click", () => {
  origin = button;
  show(n);
  lightbox.showModal();
}));
el("close").addEventListener("click", () => lightbox.close());
el("prev").addEventListener("click", () => show(index - 1));
el("next").addEventListener("click", () => show(index + 1));
lightbox.addEventListener("close", () => origin?.focus());
document.addEventListener("keydown", (event) => {
  if (lightbox.open && event.key === "ArrowLeft") show(index - 1);
  if (lightbox.open && event.key === "ArrowRight") show(index + 1);
  if (event.key === "Escape" && el("menu").getAttribute("aria-expanded") === "true") {
    menu(false);
    el("menu").focus();
  }
});
lightbox.addEventListener("pointerdown", (event) => {
  if (event.pointerType === "touch" && event.target === el("large")) startX = event.clientX;
});
lightbox.addEventListener("pointerup", (event) => {
  if (startX !== null && Math.abs(event.clientX - startX) >= 45) show(index + (event.clientX < startX ? 1 : -1));
  startX = null;
});
lightbox.addEventListener("pointercancel", () => { startX = null; });
