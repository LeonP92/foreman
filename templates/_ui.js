// Shared foreman UI: escaping, theme toggle, filter keys, drawer, focus animation.
// Text from DATA is escaped; `backticks` become <code>.
// Requires: .view, #canvas, #g (the edge <svg>), #drawer (with .drawer-body and .drawer-close), #filter, #filter-key, #theme.
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
// Sizes the stage (the edge <svg>'s parent) and the <svg> together.
function setStage(width, height) {
  svg.parentNode.style.width = width + "px";
  svg.parentNode.style.height = height + "px";
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
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
// Edge emphasis: state(e) is "out" / "in" (lit, coloured by direction), "on", "dim" or "" for each
// {path, kind, text?} (text: the edge's label, if any). Problem edges keep their own colour when lit.
// Direction colours bring up the on-canvas key.
function markEdges(list, state) {
  let directed = false;
  for (const e of list) {
    if (!e.path) continue;  // never drawn (a map opened as a matrix)
    let st = state(e);
    const towardsFocus = st === "out" || st === "in";
    directed ||= towardsFocus;
    if (towardsFocus && PROBLEM_KINDS.includes(e.kind)) st = "on";
    const dir = st === "out" || st === "in", on = dir || st === "on";
    for (const node of [e.path, e.text]) if (node) { node.classList.toggle("on", on); node.classList.toggle("dim", st === "dim"); }
    e.path.classList.toggle("out", st === "out");
    e.path.classList.toggle("in", st === "in");
    e.path.setAttribute("marker-end", `url(#a-${dir ? st : e.kind})`);
  }
  document.body.classList.toggle("directed", directed);
}
const towards = id => e => e.a === id ? "out" : e.b === id ? "in" : "dim";

// Neighbourhood ("ego") layout: what imports `id` in the columns to its left, what it imports to its right, `hops`
// deep; each column sorted by edge weight to the previous column, then name. Each id appears once, nearest first.
// Returns positions `to`, the column of every id shown, and the stage size.
function egoLayout(id, edges, hops, name, {size: [w, h], gap: [gx, gy], pad, top}) {
  const col = new Map([[id, 0]]), weight = new Map();
  for (let d = 1; d <= hops; d++) for (const side of [1, -1]) for (const e of edges) {
    const [from, to] = side > 0 ? [e.a, e.b] : [e.b, e.a];
    if (col.get(from) !== side * (d - 1)) continue;
    if (!col.has(to)) col.set(to, side * d);
    if (col.get(to) === side * d) weight.set(to, (weight.get(to) || 0) + (e.count || 1));
  }
  const cols = {};
  col.forEach((c, n) => (cols[c] ||= []).push(n));
  const keys = Object.keys(cols).map(Number).sort((a, b) => a - b), rows = Math.max(...keys.map(c => cols[c].length));
  const to = {}, byWeight = (a, b) => weight.get(b) - weight.get(a) || (name(a) < name(b) ? -1 : 1);
  keys.forEach((c, i) => cols[c].sort(byWeight).forEach((n, j) =>
    to[n] = {x: pad + i * (w + gx), y: top + ((rows - cols[c].length) / 2 + j) * (h + gy)}));
  return {to, col, width: 2 * pad + keys.length * (w + gx) - gx, height: top + rows * (h + gy) - gy + pad};
}
// Only edges one column to the right are drawn, so direction is position.
const egoEdge = (col, e) => col.has(e.a) && col.get(e.b) === col.get(e.a) + 1;
const flowPath = (p, [pw, ph], q, [, qh]) => {
  const x1 = p.x + pw, y1 = p.y + ph / 2, x2 = q.x, y2 = q.y + qh / 2, mid = (x1 + x2) / 2;
  return `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`;
};
const EGO_BUTTON = `<div class="actions"><button type="button" class="icon-btn" data-ego>Neighbourhood</button><kbd>N</kbd></div>`;

// The neighbourhood bar over the canvas: a way back (the breadcrumb) and the +1 hop toggle.
const egoBar = Object.assign(document.createElement("nav"), {className: "ego-bar crumbs", hidden: true});
egoBar.setAttribute("aria-label", "Neighbourhood");
document.querySelector(".view").appendChild(egoBar);
function showEgoBar(back, label, hops, onBack, onHops) {
  egoBar.innerHTML = `<button type="button" class="link">${esc(back)}</button><span class="quiet">/</span>`
    + `<span>Neighbourhood of <b>${esc(label)}</b></span><label class="quiet hop"><input type="checkbox"${hops > 1 ? " checked" : ""}> +1 hop</label>`;
  egoBar.querySelector("button").addEventListener("click", ev => { ev.stopPropagation(); onBack(); });
  egoBar.querySelector("input").addEventListener("change", ev => onHops(ev.target.checked ? 2 : 1));
  egoBar.hidden = false;
  document.body.classList.add("ego");
}
const hideEgoBar = () => { egoBar.hidden = true; document.body.classList.remove("ego"); };

const dirKey = Object.assign(document.createElement("div"), {className: "dir-key"});
dirKey.innerHTML = `<span><svg width="26" height="8"><line class="edge on out" x1="0" y1="4" x2="26" y2="4"/></svg>outgoing</span>`
  + `<span><svg width="26" height="8"><line class="edge on in" x1="0" y1="4" x2="26" y2="4"/></svg>incoming</span>`
  + `<span><svg width="26" height="8"><line class="edge on forbidden" x1="0" y1="4" x2="26" y2="4"/></svg>problems keep their colour</span>`;
document.querySelector(".view").appendChild(dirKey);

// Floating tooltip for things a native title can't serve (keyboard focus): showTip(element, text) / hideTip().
const tipEl = Object.assign(document.createElement("div"), {className: "tip", role: "tooltip"});
document.body.appendChild(tipEl);
function showTip(target, text) {
  const r = target.getBoundingClientRect();
  tipEl.textContent = text;
  tipEl.style.left = r.left + r.width / 2 + "px";
  tipEl.style.top = r.top - 6 + "px";
  tipEl.classList.add("on");
}
const hideTip = () => tipEl.classList.remove("on");

// Top-bar "Edges · k of n" menu over the kinds in `counts` ({kind: n}). An unchecked kind sets `hide-<kind>` on
// <body>, which the theme turns into hidden edges and dimmed matrix cells. Remembered per page.
const EDGE_MENU = {import: "Imports", call: "Calls", impl: "Implements", cycle: "Cycles", forbidden: "Forbidden", twin: "Twin"};
const PROBLEM_KINDS = ["cycle", "forbidden", "twin"];
function edgeMenu(counts) {
  const kinds = Object.keys(EDGE_MENU).filter(k => counts[k]), key = "foreman-edges:" + location.pathname;
  const hidden = new Set(JSON.parse(localStorage.getItem(key) || "[]").filter(k => kinds.includes(k)));
  const wrap = Object.assign(document.createElement("div"), {className: "menu-wrap"});
  wrap.innerHTML = `<button class="icon-btn" type="button" id="edges" aria-haspopup="menu" aria-expanded="false">Edges · <b></b> ▾</button>`
    + `<div class="menu" id="edges-menu" role="menu" aria-label="Edge kinds" hidden>`
    + kinds.map(k => `<div class="menu-item" role="menuitemcheckbox" tabindex="-1" data-kind="${k}"><span class="check"></span>`
      + `<svg width="22" height="8" class="sev-medium" aria-hidden="true"><line class="edge ${k}" x1="1" y1="4" x2="22" y2="4"/></svg>`
      + `<span>${EDGE_MENU[k]}</span><span class="n">${counts[k].toLocaleString()}</span></div>`).join("")
    + `<div class="menu-actions"><div class="menu-item" role="menuitem" tabindex="-1" data-set="all">Select all</div>`
    + `<div class="menu-item" role="menuitem" tabindex="-1" data-set="problems">Problems only</div></div></div>`;
  document.querySelector("[popovertarget=legend]").before(wrap);
  const button = wrap.querySelector("#edges"), menu = wrap.querySelector("#edges-menu");
  const entries = [...menu.querySelectorAll(".menu-item")];
  const apply = () => {
    kinds.forEach(k => {
      document.body.classList.toggle("hide-" + k, hidden.has(k));
      menu.querySelector(`[data-kind="${k}"]`).setAttribute("aria-checked", !hidden.has(k));
    });
    button.querySelector("b").textContent = `${kinds.length - hidden.size} of ${kinds.length}`;
    localStorage.setItem(key, JSON.stringify([...hidden]));
  };
  const toggleMenu = open => {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", open);
    (open ? entries[0] : button).focus();
  };
  const activate = item => {
    const k = item.dataset.kind, set = item.dataset.set;
    if (k) hidden.has(k) ? hidden.delete(k) : hidden.add(k);
    else { hidden.clear(); if (set === "problems") kinds.filter(x => !PROBLEM_KINDS.includes(x)).forEach(x => hidden.add(x)); }
    apply();
  };
  button.addEventListener("click", ev => { ev.stopPropagation(); toggleMenu(menu.hidden); });
  menu.addEventListener("click", ev => { ev.stopPropagation(); const item = ev.target.closest(".menu-item"); if (item) activate(item); });
  menu.addEventListener("keydown", ev => {
    const i = entries.indexOf(document.activeElement), move = {ArrowDown: 1, ArrowUp: -1}[ev.key];
    if (move) entries[(i + move + entries.length) % entries.length].focus();
    else if (ev.key === "Home" || ev.key === "End") entries.at(ev.key === "Home" ? 0 : -1).focus();
    else if ((ev.key === " " || ev.key === "Enter") && i >= 0) activate(entries[i]);
    else if (ev.key === "Escape") toggleMenu(false);
    else if (ev.key === "Tab") { menu.hidden = true; button.setAttribute("aria-expanded", false); return; }
    else return;
    ev.preventDefault();
    ev.stopPropagation();
  });
  document.addEventListener("click", () => { if (!menu.hidden) { menu.hidden = true; button.setAttribute("aria-expanded", false); } });
  apply();
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
// neighbourhood: switches to the neighbourhood view (key N, the drawer's Neighbourhood button).
// layout(instant): re-places the view in availableWidth(); animated when the drawer opens or closes,
// snapped on resize (debounced, then one frame).
function initUI({dismiss, onFilter, onFilterEnter, layout, neighbourhood}) {
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
    else if (/^n$/i.test(ev.key) && !ev.metaKey && !ev.ctrlKey && !ev.altKey && !(ev.target instanceof HTMLInputElement)) neighbourhood();
  });
  drawer.addEventListener("click", ev => { if (ev.target.closest("[data-ego]")) neighbourhood(); });
  drawer.querySelector(".drawer-close").addEventListener("click", dismiss);
  closeDrawer();
  relayout = layout;
  let timer;
  // Border box only: the drawer's padding transition must not count as a resize.
  new ResizeObserver(() => { clearTimeout(timer); timer = setTimeout(() => requestAnimationFrame(() => layout(true)), 100); })
    .observe(document.getElementById("canvas"), {box: "border-box"});
}
