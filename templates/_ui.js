// Shared foreman UI: escaping, theme toggle, filter keys, drawer, focus animation.
// Text from DATA is escaped; `backticks` become <code>.
// Requires: #canvas, #g (the edge <svg>), #drawer (with .drawer-body and .drawer-close), #filter, #filter-key, #theme.
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
const SEV_RANK = {low: 1, medium: 2, high: 3};
const sevWord = s => `<span class="sev-word sev-${esc(s.severity)}"><span class="dot"></span>${esc(s.severity)}</span>`;
// Card corner badge: worst severity's colour, "!" or the count, every smell in the tooltip.
function smellBadge(list) {
  if (!list || !list.length) return "";
  const worst = list.reduce((w, s) => SEV_RANK[s.severity] > SEV_RANK[w.severity] ? s : w);
  return `<span class="smell-badge sev-${worst.severity}" title="${esc(list.map(s => `${s.severity} ${s.kind}: ${s.title}`).join("\n"))}">${list.length > 1 ? list.length : "!"}</span>`;
}
const forbiddenChip = n => n ? `<span class="chip alert"><b>${n}</b> forbidden</span>` : `<span class="quiet">No forbidden crossings</span>`;
const NO_SMELLS = `<span class="quiet">No structural smells found</span>`;

const NS = "http://www.w3.org/2000/svg", svg = document.getElementById("g");
function el(tag, attrs, parent = svg) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  parent.appendChild(e);
  return e;
}
// A <defs> with a filled arrowhead `#a-<kind>` per kind, sized in canvas px so thick edges don't inflate it.
function markerDefs(kinds, size) {
  const defs = el("defs", {});
  for (const k of kinds) {
    const m = el("marker", {id: "a-" + k, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: size, markerHeight: size,
      markerUnits: "userSpaceOnUse", orient: "auto-start-reverse"}, defs);
    el("path", {d: "M0,1 L10,5 L0,9 z", class: "ah-" + k}, m);
  }
  return defs;
}
// Edge emphasis: state(e) is "on", "dim" or "" for each {path, text?} (text: the edge's label, if any).
function markEdges(list, state) {
  for (const e of list) {
    const st = state(e);
    for (const node of [e.path, e.text]) if (node) { node.classList.toggle("on", st === "on"); node.classList.toggle("dim", st === "dim"); }
  }
}

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

// Card positions by id. slide() eases them to `to` (or snaps when instant), calling redraw() each frame so
// edges stay attached while cards move.
const pos = {};
function slide(to, instant, redraw) {
  const from = instant ? to : {...pos};
  animate(k => {
    for (const id in to) { const a = from[id] || to[id], b = to[id];
      pos[id] = {x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k}; }
    redraw();
  });
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
