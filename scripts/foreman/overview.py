"""Overview of a reviewed change: the first view of its diagram page, rendered to static HTML."""

import html
import math
import re
import textwrap
from collections import Counter

ROLES = ("neutral", "blue", "green", "purple", "amber", "red")
STYLES = ("solid", "dashed")
WIDTH = 900  # drawing width of a figure that fits the text column at 1:1
MIN_SCALE = 0.95  # a wider figure shrinks only this far (12px text stays ~11.5px), then scrolls
STACK_X = (
    20  # a stacked edge's line runs this far in from its nodes' left edge, its label beside it
)
# Estimated px per character; rounded up so text never outgrows the box drawn for it.
CH, CH_BOLD, CH_CAPS = 6.8, 7.6, 7.4
LINE = 15
ZPAD = 14  # zone padding around its nodes
NODE_GAP = 36  # vertical gap between nodes in a zone with no edge between them
END_PITCH = 18  # least space between edge ends on one side of a node
GAP_MAX = 260  # widest gap between zones; a longer label wraps
INF = math.inf


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


TEXT = (_text, "a non-empty string")
TEXTS = (lambda v: isinstance(v, list) and all(map(_text, v)), "a list of non-empty strings")
COUNT = (lambda v: type(v) is int and v >= 0, "a whole number, 0 or more")
FLAG = (lambda v: isinstance(v, bool), "true or false")
ROLE = (lambda v: v in ROLES, f"one of {list(ROLES)}")
STYLE = (lambda v: v in STYLES, f"one of {list(STYLES)}")
NESTED = None  # checked by its own rules


def _count(where: str, n: int, lo: int, hi: float) -> list[str]:
    if lo <= n <= hi:
        return []
    want = f"at least {lo}" if hi == INF else f"{lo} to {hi}"
    return [f"{where}: needs {want} items, got {n}"]


def _obj(errs: list, where: str, item, required: dict, optional: dict | None = None) -> bool:
    """Checks one object's fields into errs; False when it isn't an object."""
    optional = optional or {}
    if not isinstance(item, dict):
        errs.append(f"{where}: must be an object")
        return False
    errs += [f"{where}: missing '{k}'" for k in required if k not in item]
    errs += [f"{where}: unknown key '{k}'" for k in item.keys() - required.keys() - optional.keys()]
    for k, check in {**required, **optional}.items():
        if check and k in item and not check[0](item[k]):
            errs.append(f"{where}: '{k}' must be {check[1]}")
    return True


def _objs(errs, where, items, lo, hi, required, optional=None) -> list[dict]:
    """Checks a list of objects; returns those that are objects. None means missing (reported)."""
    if items is None:
        return []
    if not isinstance(items, list):
        errs.append(f"{where}: must be a list")
        return []
    errs += _count(where, len(items), lo, hi)
    return [x for i, x in enumerate(items) if _obj(errs, f"{where} #{i}", x, required, optional)]


def _texts(errs: list, where: str, items, lo: int, hi: float) -> None:
    if items is None:
        return
    if not TEXTS[0](items):
        errs.append(f"{where}: must be {TEXTS[1]}")
    else:
        errs += _count(where, len(items), lo, hi)


def _ids(errs: list, where: str, items: list[dict]) -> list[str]:
    ids = [x["id"] for x in items if isinstance(x.get("id"), str)]
    errs += [
        f"{where} id {i!r} is duplicated" for i in sorted({i for i in ids if ids.count(i) > 1})
    ]
    return ids


def _network_problems(net) -> list[str]:
    errs: list[str] = []
    parts = {"caption": TEXT, "zones": NESTED, "nodes": NESTED, "edges": NESTED}
    if not _obj(errs, "network", net, parts):
        return errs
    zones = _objs(
        errs, "network zones", net.get("zones"), 1, 5, {"id": TEXT, "label": TEXT, "role": ROLE}
    )
    nodes = _objs(
        errs,
        "network nodes",
        net.get("nodes"),
        1,
        INF,
        {"id": TEXT, "zone": TEXT, "title": TEXT},
        {"subtitle": TEXT, "lines": TEXTS},
    )
    edges = _objs(
        errs,
        "network edges",
        net.get("edges"),
        0,
        INF,
        {"from": TEXT, "to": TEXT, "label": TEXT},
        {"sublabel": TEXT, "style": STYLE, "both": FLAG},
    )
    zone_ids, node_ids = _ids(errs, "network zone", zones), _ids(errs, "network node", nodes)
    stacks: dict[str, list] = {z: [] for z in zone_ids}
    for n in nodes:
        if isinstance(n.get("zone"), str) and n["zone"] in stacks:
            stacks[n["zone"]].append(n.get("id"))
        else:
            errs.append(f"network node {n.get('id')!r}: zone {n.get('zone')!r} is not in zones")
    errs += [f"network zone {z!r} has no nodes (drop it)" for z, ids in stacks.items() if not ids]
    place = {i: (z, k) for z, ids in stacks.items() for k, i in enumerate(ids)}
    same_pairs = set()
    for e in edges:
        a, b = e.get("from"), e.get("to")
        name = f"network edge {a!r} -> {b!r}"
        if a not in node_ids or b not in node_ids:
            errs.append(f"{name}: unknown node")
        elif a == b:
            errs.append(f"{name}: points at itself")
        elif (
            a in place
            and b in place
            and place[a][0] == place[b][0]
            and abs(place[a][1] - place[b][1]) == 1
        ):
            # stack neighbours share one short vertical line, so a second edge would hide in it
            if frozenset((a, b)) in same_pairs:
                errs.append(f"{name}: second edge between the same pair (use one with 'both')")
            same_pairs.add(frozenset((a, b)))
    return errs


def _sequence_problems(seq) -> list[str]:
    errs: list[str] = []
    if not _obj(
        errs, "sequence", seq, {"caption": TEXT, "participants": NESTED, "messages": NESTED}
    ):
        return errs
    parts = _objs(
        errs, "sequence participants", seq.get("participants"), 2, 5, {"id": TEXT, "label": TEXT}
    )
    msgs = _objs(
        errs,
        "sequence messages",
        seq.get("messages"),
        1,
        INF,
        {"from": TEXT, "to": TEXT, "label": TEXT},
        {"notes": TEXTS, "role": ROLE},
    )
    ids = _ids(errs, "sequence participant", parts)
    errs += [
        f"sequence message {m.get('label')!r}: unknown participant {m.get(k)!r}"
        for m in msgs
        for k in ("from", "to")
        if m.get(k) not in ids
    ]
    return errs


def validate(data: dict) -> list[str]:
    """Every problem in overview data, so the author can fix them in one pass."""
    errs: list[str] = []
    required = {
        "title": TEXT,
        "branch": TEXT,
        "base": TEXT,
        "head": TEXT,
        "stats": NESTED,
        "summary": TEXT,
        "bullets": NESTED,
        "decisions": NESTED,
        "changes": NESTED,
        "limits": NESTED,
    }
    optional = {"network": NESTED, "sequence": NESTED, "cards": NESTED}
    _obj(errs, "overview", data, required, optional)
    if "stats" in data:
        _obj(errs, "stats", data["stats"], {"commits": COUNT, "added": COUNT, "removed": COUNT})
    _texts(errs, "bullets", data.get("bullets"), 3, 6)
    _texts(errs, "limits", data.get("limits"), 1, INF)
    _objs(errs, "decisions", data.get("decisions"), 1, INF, {"decision": TEXT, "why": TEXT})
    _objs(errs, "changes", data.get("changes"), 1, INF, {"area": TEXT, "change": TEXT})
    for i, card in enumerate(
        _objs(errs, "cards", data.get("cards"), 1, 3, {"title": TEXT, "bullets": TEXTS})
    ):
        if card.get("bullets") == []:
            errs.append(f"cards #{i}: 'bullets' must not be empty")
    if "network" in data:
        errs += _network_problems(data["network"])
    if "sequence" in data:
        errs += _sequence_problems(data["sequence"])
    return errs


# Text: escaped, `backticks` become code, as the diagram's fmt() does.
def _fmt(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(s))


def _svg_fmt(s: str) -> str:
    return re.sub(r"`([^`]+)`", r'<tspan class="code">\1</tspan>', html.escape(s))


def _wrap(text: str, px: float, ch: float = CH) -> list[str]:
    # shortcut: a code span split across lines shows its backticks; fine for short labels
    return textwrap.wrap(text, max(8, int(px // ch))) or [""]


def _texts_svg(x, y, lines, cls, anchor="middle", step=LINE) -> str:
    return "".join(
        f'<text x="{x:.1f}" y="{y + i * step:.1f}" class="{cls}" text-anchor="{anchor}">'
        f"{_svg_fmt(t)}</text>"
        for i, t in enumerate(lines)
    )


def _sweep(labels: list[dict], floor: float) -> None:
    """Pushes labels sharing one gap down until none overlap; each keeps its centre x."""
    bottom = floor
    for lab in sorted(labels, key=lambda b: b["want"]):
        x, _, w, h = lab["box"]
        top = max(lab["want"] - h / 2, bottom + 6)
        lab["box"] = (x, top, w, h)
        bottom = top + h


def _rounded(pts: list[tuple[float, float]], r: float = 8) -> str:
    sign = lambda v: (v > 0) - (v < 0)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for (ax, ay), (bx, by), (cx, cy) in zip(pts, pts[1:], pts[2:]):
        k = min(r, (abs(bx - ax) + abs(by - ay)) / 2, (abs(cx - bx) + abs(cy - by)) / 2)
        d += (
            f" L{bx - k * sign(bx - ax):.1f},{by - k * sign(by - ay):.1f}"
            f" Q{bx:.1f},{by:.1f} {bx + k * sign(cx - bx):.1f},{by + k * sign(cy - by):.1f}"
        )
    return d + f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"


def _edge_lines(e: dict) -> list[str]:
    return [e["label"], *([e["sublabel"]] if e.get("sublabel") else [])]


def _edge_label(e: dict, px: float) -> dict:
    """The label box: the label's lines, then the sublabel's on lines of their own."""
    main = _wrap(e["label"], px)
    sub = _wrap(e["sublabel"], px) if e.get("sublabel") else []
    w = max(len(t) for t in main + sub) * CH + 12
    return {"box": (-w / 2, 0, w, (len(main) + len(sub)) * 14 + 8), "main": main, "sub": sub}


def _place(lab: dict, x: float, y: float) -> dict:
    """Moves a label box so its top-left is (x, y)."""
    lab["box"] = (x, y, *lab["box"][2:])
    return lab


def network_layout(net: dict) -> dict:
    """Places zones as columns, nodes stacked in them, edges between box sides, and labels."""
    zones, nodes, edges = net["zones"], net["nodes"], net["edges"]
    n = len(zones)
    col = {z["id"]: i for i, z in enumerate(zones)}
    zone_of = {nd["id"]: col[nd["zone"]] for nd in nodes}
    stacks = [[nd for nd in nodes if nd["zone"] == z["id"]] for z in zones]
    order = {nd["id"]: k for stack in stacks for k, nd in enumerate(stack)}
    span = lambda e: abs(zone_of[e["from"]] - zone_of[e["to"]])
    # stack neighbours in one zone are joined by a short vertical line between them
    stacked = lambda e: span(e) == 0 and abs(order[e["from"]] - order[e["to"]]) == 1
    # the longest skip gets the highest lane, so shorter ones nest under it without crossing
    skips = sorted((e for e in edges if span(e) > 1), key=span, reverse=True)
    # other same-zone edges run down the gap beside their zone: right, or left for the last zone
    detours = [e for e in edges if span(e) == 0 and not stacked(e)]
    goes_right = lambda e: zone_of[e["from"]] < n - 1 or n == 1
    lanes = skips + detours  # each owns a vertical run, offset from the zone's border
    runs = 10 + 7 * len(lanes)  # room at each side of a gap for those runs
    in_gaps = [e for e in edges if span(e) == 1 or e in detours]
    want = max((len(t) * CH for e in in_gaps for t in _edge_lines(e)), default=0)
    # wide enough for the longest label on one line; past WIDTH the figure scales down to fit
    gap = min(max(want + 14 + 2 * runs, 110), GAP_MAX)  # +2: float slack so it wraps to one line
    # nodes wide enough for a stacked edge's label on one line beside its line, within reason
    beside = max((len(t) * CH for e in edges if stacked(e) for t in _edge_lines(e)), default=0)
    zw = min(360, max(180, (WIDTH - (n - 1) * gap) / n, beside + 12 + STACK_X + 16 + 2 * ZPAD))
    nw = zw - 2 * ZPAD
    zx = [i * (zw + gap) for i in range(n)]
    # a lone zone's detours need a gap of their own on its right
    width = n * zw + (n - 1 + (n == 1 and bool(detours))) * gap
    # each skip gets its own lane above the zones, as tall as its label
    sky_labels, levels, sky = [_edge_label(e, 400) for e in skips], [], 0.0
    for lab in sky_labels:
        levels.append(sky + 8 + lab["box"][3] / 2)
        sky += lab["box"][3] + 8
    sky += 8 if skips else 0

    def right_side(e: dict, end: str) -> bool:
        a, b = zone_of[e["from"]], zone_of[e["to"]]
        if a == b:
            return goes_right(e)
        return b > a if end == "from" else a > b

    sided = [(e, end) for e in edges if not stacked(e) for end in ("from", "to")]
    per_side = Counter((e[end], right_side(e, end)) for e, end in sided)

    heads = [_wrap(z["label"].upper(), nw, CH_CAPS) for z in zones]
    head = 14 + 14 * max(map(len, heads)) + 6
    boxes: dict[str, dict] = {}
    near = {frozenset((e["from"], e["to"])): e for e in edges if stacked(e)}
    heights = []
    for i, stack in enumerate(stacks):
        y = 0.0
        for k, nd in enumerate(stack):
            title = _wrap(nd["title"], nw - 24, CH_BOLD)
            sub = _wrap(nd["subtitle"], nw - 24) if nd.get("subtitle") else []
            more = [w for line in nd.get("lines", []) for w in _wrap(line, nw - 24)]
            h = 14 + 17 * len(title) + LINE * len(sub) + LINE * len(more) + (6 if more else 0)
            # tall enough that arrowheads sharing a side stay apart
            shared = max(per_side[(nd["id"], True)], per_side[(nd["id"], False)])
            h = max(h, END_PITCH * (shared + 1))
            boxes[nd["id"]] = {
                "x": zx[i] + ZPAD,
                "y": y,
                "w": nw,
                "h": h,
                "role": zones[i]["role"],
                "title": title,
                "sub": sub,
                "more": more,
            }
            y += h
            if k + 1 < len(stack):
                link = near.get(frozenset((nd["id"], stack[k + 1]["id"])))
                tall = _edge_label(link, nw - STACK_X - 26)["box"][3] if link else 0
                y += max(NODE_GAP, tall + 16)
        heights.append(y)
    top = sky + head
    for stack in stacks:  # top-aligned: each zone is as tall as its own nodes
        for nd in stack:
            boxes[nd["id"]]["y"] += top

    # spread the ends that share a node side, ordered by where the other end sits
    centre = lambda nid: boxes[nid]["y"] + boxes[nid]["h"] / 2
    sides: dict[tuple, list] = {}
    for idx, e in enumerate(edges):
        if not stacked(e):
            for end, other in (("from", "to"), ("to", "from")):
                sides.setdefault((e[end], right_side(e, end)), []).append(
                    (centre(e[other]), idx, end)
                )
    ends: dict[tuple, tuple] = {}
    for (nid, right), items in sides.items():
        bx = boxes[nid]
        for k, (_, idx, end) in enumerate(sorted(items)):
            x = bx["x"] + (bx["w"] if right else 0)
            ends[(idx, end)] = (x, bx["y"] + bx["h"] * (k + 1) / (len(items) + 1))

    links, gap_labels = [], {}
    for idx, e in enumerate(edges):
        a, b = boxes[e["from"]], boxes[e["to"]]
        if stacked(e):
            down = a["y"] < b["y"]
            x = a["x"] + STACK_X
            y1, y2 = (a["y"] + a["h"], b["y"]) if down else (a["y"], b["y"] + b["h"])
            lab = _edge_label(e, a["w"] - STACK_X - 26)
            _place(lab, x + 8, (y1 + y2) / 2 - lab["box"][3] / 2)["anchor"] = "start"
            d = f"M{x:.1f},{y1:.1f} L{x:.1f},{y2:.1f}"
            links.append({"d": d, "edge": e, "label": lab})
            continue
        (x1, y1), (x2, y2) = ends[(idx, "from")], ends[(idx, "to")]
        ca, cb = zone_of[e["from"]], zone_of[e["to"]]
        # a skip's label sits on its long run over the zones; the others share a gap
        lab = sky_labels[skips.index(e)] if span(e) > 1 else _edge_label(e, gap - 2 * runs - 12)
        w, h = lab["box"][2:]
        if span(e) == 1:
            mx = (x1 + x2) / 2
            d = f"M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
            _place(lab, mx - w / 2, 0)["want"] = (y1 + y2) / 2
            gap_labels.setdefault(min(ca, cb), []).append(lab)
        elif span(e) == 0:
            right = goes_right(e)
            off = 10 + 7 * lanes.index(e)
            run = zx[ca] + zw + off if right else zx[ca] - off
            d = _rounded([(x1, y1), (run, y1), (run, y2), (x2, y2)])
            # beside its own run, on the side away from the zone
            _place(lab, run + 6 if right else run - 6 - w, 0)["want"] = (y1 + y2) / 2
            gap_labels.setdefault(ca if right else ca - 1, []).append(lab)
        else:
            k = lanes.index(e)
            off = 10 + 7 * k
            run_a = zx[ca] + zw + off if cb > ca else zx[ca] - off
            run_b = zx[cb] - off if cb > ca else zx[cb] + zw + off
            level = levels[k]
            d = _rounded(
                [(x1, y1), (run_a, y1), (run_a, level), (run_b, level), (run_b, y2), (x2, y2)]
            )
            _place(lab, (run_a + run_b) / 2 - w / 2, level - h / 2)
        links.append({"d": d, "edge": e, "label": lab})
    for labels in gap_labels.values():
        _sweep(labels, sky)
    labels = [lk["label"] for lk in links]
    zone_boxes = [
        {"x": zx[i], "y": sky, "w": zw, "h": head + h + ZPAD, "role": z["role"], "title": heads[i]}
        for i, (z, h) in enumerate(zip(zones, heights))
    ]
    bottoms = [z["y"] + z["h"] for z in zone_boxes] + [lb["box"][1] + lb["box"][3] for lb in labels]
    height = max(bottoms) + 4
    return {
        "width": width,
        "height": height,
        "head": head,
        "zones": zone_boxes,
        "nodes": boxes,
        "links": links,
        "ends": ends,
    }


def _markers(name: str) -> str:
    return (
        "<defs>"
        + "".join(
            f'<marker id="{name}-{r}" class="role-{r}" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
            '<path d="M0,1 L10,5 L0,9 z" class="arrow-head"/></marker>'
            for r in ROLES
        )
        + "</defs>"
    )


def _label_svg(lab: dict) -> str:
    x, y, w, h = lab["box"]
    anchor = lab.get("anchor", "middle")
    tx = x + 6 if anchor == "start" else x + w / 2
    return (
        f'<g class="label"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="5"/>'
        + _texts_svg(tx, y + 15, lab["main"], "label-main", anchor, 14)
        + _texts_svg(tx, y + 15 + 14 * len(lab["main"]), lab["sub"], "label-sub", anchor, 14)
        + "</g>"
    )


def _figure(svg: str, width: float, height: float, caption: str) -> str:
    return (
        f'<figure class="drawing"><svg viewBox="0 0 {width:.0f} {height:.0f}" '
        f'style="width:{width:.0f}px;min-width:{width * MIN_SCALE:.0f}px" '
        f'role="img" aria-label="{html.escape(caption)}">{svg}</svg>'
        f"<figcaption>{_fmt(caption)}</figcaption></figure>"
    )


def _network_svg(net: dict) -> str:
    lay = network_layout(net)
    out = [_markers("net")]
    for z in lay["zones"]:
        out.append(
            f'<g class="zone role-{z["role"]}"><rect x="{z["x"]:.1f}" y="{z["y"]:.1f}" '
            f'width="{z["w"]:.1f}" height="{z["h"]:.1f}" rx="12"/>'
            + _texts_svg(z["x"] + ZPAD, z["y"] + 22, z["title"], "zone-title", "start", 14)
            + "</g>"
        )
    for lk in lay["links"]:
        e = lk["edge"]
        start = ' marker-start="url(#net-neutral)"' if e.get("both") else ""
        out.append(
            f'<path class="net-link {e.get("style", "solid")}" d="{lk["d"]}" '
            f'marker-end="url(#net-neutral)"{start}/>'
        )
    for b in lay["nodes"].values():
        x, y = b["x"], b["y"]
        ty = y + 22
        out.append(
            f'<g class="node role-{b["role"]}"><rect x="{x:.1f}" y="{y:.1f}" width="{b["w"]:.1f}" '
            f'height="{b["h"]:.1f}" rx="8"/>'
            + _texts_svg(x + 12, ty, b["title"], "node-title", "start", 17)
            + _texts_svg(x + 12, ty + 17 * len(b["title"]) - 1, b["sub"], "node-sub", "start")
            + _texts_svg(
                x + 12,
                ty + 17 * len(b["title"]) + LINE * len(b["sub"]) + 5,
                b["more"],
                "node-line",
                "start",
            )
            + "</g>"
        )
    out += [_label_svg(lk["label"]) for lk in lay["links"]]
    return _figure("".join(out), lay["width"], lay["height"], net["caption"])


def _sequence_svg(seq: dict) -> str:
    parts = seq["participants"]
    step = WIDTH / len(parts)
    x = {p["id"]: step * (i + 0.5) for i, p in enumerate(parts)}
    bw = min(step - 24, 210)
    heads = {p["id"]: _wrap(p["label"], bw - 16, CH_BOLD) for p in parts}
    head_h = 16 + 17 * max(map(len, heads.values()))
    body, y = [], head_h + 24
    for i, m in enumerate(seq["messages"], 1):
        role = m.get("role", "neutral")
        a, b = x[m["from"]], x[m["to"]]
        notes = m.get("notes", [])
        if a == b:  # a step one participant takes alone: a box on its lifeline
            w = min(step - 20, 240)
            lines = _wrap(f"{i}. {m['label']}", w - 16)
            notes = [t for n in notes for t in _wrap(n, w - 16)]
            h = 12 + LINE * len(lines) + 14 * len(notes) + 4
            body.append(
                f'<g class="msg role-{role}"><rect class="self" x="{a - w / 2:.1f}" y="{y:.1f}" '
                f'width="{w:.1f}" height="{h:.1f}" rx="6"/>'
                + _texts_svg(a, y + 18, lines, "msg-label")
                + _texts_svg(a, y + 18 + LINE * len(lines), notes, "msg-note", step=14)
                + "</g>"
            )
            y += h + 18
            continue
        room = abs(b - a) - 28
        lines = _wrap(f"{i}. {m['label']}", room)
        notes = [t for n in notes for t in _wrap(n, room)]
        arrow = y + LINE * len(lines) + 4
        lw = max(len(t) for t in lines) * CH + 10
        # notes get a backing too, or a lifeline the message passes over runs through them
        nw = max((len(t) for t in notes), default=0) * CH + 10
        note_bg = (
            f'<rect class="msg-bg" x="{(a + b) / 2 - nw / 2:.1f}" y="{arrow + 5:.1f}" '
            f'width="{nw:.1f}" height="{14 * len(notes) + 2:.1f}"/>'
            if notes
            else ""
        )
        body.append(
            f'<g class="msg role-{role}">'
            f'<rect class="msg-bg" x="{(a + b) / 2 - lw / 2:.1f}" y="{y:.1f}" width="{lw:.1f}" '
            f'height="{LINE * len(lines):.1f}"/>'
            + _texts_svg((a + b) / 2, y + 12, lines, "msg-label")
            + f'<line x1="{a:.1f}" y1="{arrow:.1f}" x2="{b:.1f}" y2="{arrow:.1f}" '
            f'marker-end="url(#seq-{role})"/>'
            + note_bg
            + _texts_svg((a + b) / 2, arrow + 16, notes, "msg-note", step=14)
            + "</g>"
        )
        y = arrow + 14 * len(notes) + (26 if notes else 20)
    lifelines = "".join(
        f'<line class="lifeline" x1="{x[p["id"]]:.1f}" y1="{head_h:.1f}" x2="{x[p["id"]]:.1f}" '
        f'y2="{y:.1f}"/><g class="actor"><rect x="{x[p["id"]] - bw / 2:.1f}" y="0" width="{bw:.1f}" '
        f'height="{head_h:.1f}" rx="8"/>'
        + _texts_svg(x[p["id"]], 22, heads[p["id"]], "node-title", step=17)
        + "</g>"
        for p in parts
    )
    svg = _markers("seq") + lifelines + "".join(body)
    return _figure(svg, WIDTH, y + 4, seq["caption"])


def _table(head: tuple[str, str], rows: list[tuple[str, str]]) -> str:
    cells = "".join(f"<tr><td>{_fmt(a)}</td><td>{_fmt(b)}</td></tr>" for a, b in rows)
    return f"<table><thead><tr><th>{head[0]}</th><th>{head[1]}</th></tr></thead><tbody>{cells}</tbody></table>"


def _ul(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{_fmt(t)}</li>" for t in items) + "</ul>"


def body(data: dict) -> str:
    """The Overview view's content for valid overview data."""
    s = data["stats"]
    plural = "" if s["commits"] == 1 else "s"
    out = [
        (
            f'<header class="head"><h1>{_fmt(data["title"])}</h1>'
            f'<p class="ov-meta"><code>{html.escape(data["branch"])}</code> · '
            f"<code>{html.escape(data['base'])}</code> → <code>{html.escape(data['head'])}</code> · "
            f"{s['commits']} commit{plural} · +{s['added']} / −{s['removed']} lines</p></header>"
        ),
        f'<section class="callout"><p>{_fmt(data["summary"])}</p>{_ul(data["bullets"])}</section>',
    ]
    if "network" in data:
        out.append(f"<section><h2>Network view</h2>{_network_svg(data['network'])}</section>")
    if "sequence" in data:
        out.append(f"<section><h2>Sequence view</h2>{_sequence_svg(data['sequence'])}</section>")
    out.append(
        '<section><h2>Component view</h2><figure class="link-fig">'
        '<button type="button" class="view-link" data-view="graph">Open the graph view</button>'
        "<figcaption>Modules and interfaces the change touches and their direct neighbours, "
        "with forbidden crossings and smells marked.</figcaption></figure></section>"
    )
    decisions = [(d["decision"], d["why"]) for d in data["decisions"]]
    out.append(
        f"<section><h2>Key design decisions</h2>{_table(('Decision', 'Why'), decisions)}</section>"
    )
    if "cards" in data:
        cards = "".join(
            f'<div class="card-box"><h3>{_fmt(c["title"])}</h3>{_ul(c["bullets"])}</div>'
            for c in data["cards"]
        )
        out.append(f'<section class="cards">{cards}</section>')
    changes = [(c["area"], c["change"]) for c in data["changes"]]
    out.append(f"<section><h2>What changed</h2>{_table(('Area', 'Change'), changes)}</section>")
    out.append(f"<section><h2>Known limits / not done</h2>{_ul(data['limits'])}</section>")
    return '<div class="doc">' + "\n".join(out) + "</div>"
