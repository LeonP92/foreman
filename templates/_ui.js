// Shared foreman UI: escaping, theme toggle, filter keys, drawer, focus animation.
// Text from DATA is escaped; `backticks` become <code>.
// Requires: #canvas, #drawer (with .drawer-body and .drawer-close), #filter, #filter-key, #theme.
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
let drawerOpener = null, relayout = () => {};
// Width the view may lay out in: the canvas minus the drawer's reserved strip while it is open.
const availableWidth = canvas => canvas.clientWidth - (drawer.classList.contains("open") ? drawer.offsetWidth : 0);
// opener: the element focus returns to if the drawer closes while holding focus.
function openDrawer(html, opener) {
  drawerOpener = opener;
  const was = drawer.classList.contains("open");
  drawer.querySelector(".drawer-body").innerHTML = html;
  drawer.querySelector(".drawer-body").scrollTop = 0;
  drawer.classList.add("open");
  drawer.inert = false;
  document.body.classList.add("drawer-open");
  if (!was) relayout();
}
function closeDrawer() {
  if (drawer.contains(document.activeElement) && drawerOpener && drawerOpener.isConnected) drawerOpener.focus();
  const was = drawer.classList.contains("open");
  drawer.classList.remove("open");
  drawer.inert = true;
  document.body.classList.remove("drawer-open");
  if (was) relayout();
}

// dismiss: clears the view's selection (Esc, drawer close). onFilter(query) / onFilterEnter(query).
// layout(instant): re-places the view in availableWidth(); animated when the drawer opens or closes,
// snapped on resize (debounced, then one frame).
function initUI({dismiss, onFilter, onFilterEnter, layout}) {
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
  relayout = layout;
  let timer;
  // Border box only: the drawer's padding transition must not count as a resize.
  new ResizeObserver(() => { clearTimeout(timer); timer = setTimeout(() => requestAnimationFrame(() => layout(true)), 100); })
    .observe(document.getElementById("canvas"), {box: "border-box"});
}
