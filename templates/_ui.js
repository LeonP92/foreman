// Shared foreman UI: escaping, theme toggle, filter keys, drawer, focus animation.
// Text from DATA is escaped; `backticks` become <code>.
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)");
const THEME_KEY = "foreman-theme";

// Runs step(k) with an eased k from 0 to 1 over ~200 ms; a newer call cancels the older one.
let animation = 0;
function animate(step, ms = 200) {
  const me = ++animation, start = performance.now();
  const tick = now => {
    if (me !== animation) return;
    const t = REDUCED_MOTION.matches ? 1 : Math.max(0, Math.min(1, (now - start) / ms));
    step(t * (2 - t));
    if (t < 1) requestAnimationFrame(tick);
  };
  tick(start);
}

const drawer = document.getElementById("drawer");
function openDrawer(html) {
  drawer.querySelector(".drawer-body").innerHTML = html;
  drawer.querySelector(".drawer-body").scrollTop = 0;
  drawer.classList.add("open");
  drawer.inert = false;
  document.body.classList.add("drawer-open");
}
function closeDrawer() {
  drawer.classList.remove("open");
  drawer.inert = true;
  document.body.classList.remove("drawer-open");
}

// dismiss: clears the view's selection (Esc, drawer close). onFilter(query) / onFilterEnter(query).
function initUI({dismiss, onFilter, onFilterEnter}) {
  const root = document.documentElement, filter = document.getElementById("filter");
  const saved = localStorage.getItem(THEME_KEY);
  if (saved) root.dataset.theme = saved;
  document.getElementById("theme").addEventListener("click", () => {
    const current = root.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    root.dataset.theme = current === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, root.dataset.theme);
  });
  document.getElementById("filter-key").textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘K" : "Ctrl K";
  filter.addEventListener("input", () => onFilter(filter.value.trim().toLowerCase()));
  filter.addEventListener("keydown", ev => {
    if (ev.key === "Enter") onFilterEnter(filter.value.trim().toLowerCase());
    if (ev.key === "Escape" && filter.value) { ev.stopPropagation(); filter.value = ""; onFilter(""); }
  });
  document.addEventListener("keydown", ev => {
    if (/^k$/i.test(ev.key) && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); filter.focus(); filter.select(); }
    else if (ev.key === "Escape") dismiss();
  });
  drawer.querySelector(".drawer-close").addEventListener("click", dismiss);
  closeDrawer();
}
