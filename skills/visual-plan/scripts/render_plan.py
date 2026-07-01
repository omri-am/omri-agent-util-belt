#!/usr/bin/env python3
"""Render a plan JSON to a self-contained HTML page and open it.

Usage: python3 render_plan.py <path-to-plan.json>
Outputs HTML path on stdout, opens in default browser (macOS `open`).
"""
import json
import sys
import os
import subprocess
import html
import time
from pathlib import Path


def esc(s):
    return html.escape(str(s), quote=True)


def render_before_after(step):
    """Side-by-side current vs proposed state. Content is escaped + shown
    monospace so code snippets read cleanly; omitted if neither present."""
    before = step.get("before")
    after = step.get("after")
    if not before and not after:
        return ""
    before_body = esc(before) if before else "—"
    after_body = esc(after) if after else "—"
    return f"""
      <div class="ba">
        <div class="ba-col ba-before">
          <div class="ba-label">Before</div>
          <div class="ba-body">{before_body}</div>
        </div>
        <div class="ba-arrow">→</div>
        <div class="ba-col ba-after">
          <div class="ba-label">After</div>
          <div class="ba-body">{after_body}</div>
        </div>
      </div>
    """


def render_step(step, idx):
    sid = esc(step.get("id", str(idx + 1)))
    title = esc(step.get("title", ""))
    detail = esc(step.get("detail", ""))
    files = step.get("files", []) or []
    optional = step.get("optional", False)
    files_html = ""
    if files:
        chips = "".join(f'<span class="chip">{esc(f)}</span>' for f in files)
        files_html = f'<div class="files">{chips}</div>'
    opt_badge = '<span class="badge-opt">optional</span>' if optional else ""
    stakes = (str(step.get("stakes", "")) or "").lower()
    stakes_cls = " stakes-high" if stakes == "high" else ""
    stakes_badge = ""
    if stakes == "high":
        reason = esc(step.get("stakes_reason", "hard to reverse once callers/data depend on it"))
        stakes_badge = f'<span class="badge-stakes" title="{reason}">⚠ hard to undo</span>'
    ba_html = render_before_after(step)
    return f"""
    <div class="step{stakes_cls}" data-step-id="{sid}">
      <div class="step-head">
        <div class="step-num">{sid}</div>
        <div class="step-titles">
          <div class="step-title">{title} {opt_badge} {stakes_badge}</div>
          <div class="step-detail">{detail}</div>
          {files_html}
        </div>
        <div class="step-actions">
          <label class="btn approve"><input type="radio" name="dec-{sid}" value="approve" checked>Approve</label>
          <label class="btn reject"><input type="radio" name="dec-{sid}" value="reject">Reject</label>
          <label class="btn modify"><input type="radio" name="dec-{sid}" value="modify">Modify</label>
        </div>
      </div>
      {ba_html}
      <textarea class="modify-note" data-for="{sid}" placeholder="What to change about step {sid}..."></textarea>
    </div>
    """


def render_alternative(alt, idx):
    name = esc(alt.get("name", f"Alternative {idx + 1}"))
    trade = esc(alt.get("tradeoffs", ""))
    steps = alt.get("steps", []) or []
    steps_html = "".join(f"<li>{esc(s)}</li>" for s in steps)
    return f"""
    <div class="alt-card">
      <label class="alt-pick">
        <input type="radio" name="alt-pick" value="{name}">
        <span class="alt-name">{name}</span>
      </label>
      <div class="alt-trade">{trade}</div>
      <ol class="alt-steps">{steps_html}</ol>
    </div>
    """


def render_simulation(sim):
    if not sim or not sim.get("screens"):
        return ""
    screens = sim["screens"]
    start = sim.get("start", screens[0]["id"])
    screens_html = ""
    for sc in screens:
        sid = esc(sc["id"])
        title = esc(sc.get("title", ""))
        body = sc.get("body_html", "")
        actions = sc.get("actions", []) or []
        actions_html = "".join(
            f'<button class="sim-btn" data-next="{esc(a["next"])}">{esc(a["label"])}</button>'
            for a in actions
        )
        if not actions_html:
            actions_html = '<div class="sim-end">— end of flow —</div>'
        screens_html += f"""
        <div class="sim-screen" data-screen="{sid}" style="display:none;">
          <div class="sim-title">{title}</div>
          <div class="sim-body">{body}</div>
          <div class="sim-actions">{actions_html}</div>
        </div>
        """
    return f"""
    <section class="block">
      <h2>Simulation</h2>
      <div class="sim-hint">Click through proposed flow.</div>
      <div class="sim-frame" data-start="{esc(start)}">
        {screens_html}
        <button class="sim-reset" type="button">↺ Restart</button>
      </div>
    </section>
    """


def compute_levels(steps):
    """Assign each step a row (level) = longest dependency chain to a root.

    Edges come from each step's `depends_on`. If NO step declares deps, fall
    back to an implicit linear chain (step N depends on step N-1) so the graph
    still shows order. Unknown dep ids are ignored; cycles fall back to level 0.
    """
    ids = [str(s.get("id", str(i + 1))) for i, s in enumerate(steps)]
    id_set = set(ids)
    deps = {}
    for i, s in enumerate(steps):
        sid = ids[i]
        declared = [str(d) for d in (s.get("depends_on") or []) if str(d) in id_set]
        deps[sid] = declared
    if not any(deps[i] for i in ids):  # no explicit deps -> linear chain
        deps = {ids[i]: ([ids[i - 1]] if i > 0 else []) for i in range(len(ids))}

    level = {}

    def lvl(sid, seen):
        if sid in level:
            return level[sid]
        if sid in seen:  # cycle guard
            return 0
        if not deps.get(sid):
            level[sid] = 0
            return 0
        seen = seen | {sid}
        m = 1 + max(lvl(d, seen) for d in deps[sid])
        level[sid] = m
        return m

    for sid in ids:
        lvl(sid, set())
    edges = [(d, sid) for sid in ids for d in deps.get(sid, [])]
    return ids, level, edges


def render_flow(steps):
    """Inline SVG dependency graph. Nodes carry data-node=<id> so the
    in-browser radio handler recolors them to match each step's decision."""
    if len(steps) < 2:
        return ""
    ids, level, edges = compute_levels(steps)
    titles = {
        str(s.get("id", str(i + 1))): str(s.get("title", "")) for i, s in enumerate(steps)
    }

    rows = {}
    for sid in ids:
        rows.setdefault(level[sid], []).append(sid)
    max_level = max(rows) if rows else 0

    NW, NH = 168, 48          # node box
    GX, GY = 28, 56           # gaps
    MX, MY = 16, 16           # margins
    max_cols = max((len(r) for r in rows.values()), default=1)
    inner_w = max_cols * NW + (max_cols - 1) * GX
    width = inner_w + 2 * MX
    height = (max_level + 1) * NH + max_level * GY + 2 * MY

    pos = {}  # id -> (x, y) of node top-left
    for lv in range(max_level + 1):
        row = rows.get(lv, [])
        row_w = len(row) * NW + (len(row) - 1) * GX
        x0 = MX + (inner_w - row_w) / 2
        y = MY + lv * (NH + GY)
        for j, sid in enumerate(row):
            pos[sid] = (x0 + j * (NW + GX), y)

    # Edges first (under nodes)
    edge_svg = ""
    for src, dst in edges:
        if src not in pos or dst not in pos:
            continue
        sx, sy = pos[src]
        dx, dy = pos[dst]
        x1, y1 = sx + NW / 2, sy + NH
        x2, y2 = dx + NW / 2, dy
        my = (y1 + y2) / 2
        edge_svg += (
            f'<path class="fedge" d="M{x1:.0f},{y1:.0f} '
            f'C{x1:.0f},{my:.0f} {x2:.0f},{my:.0f} {x2:.0f},{y2:.0f}" '
            f'marker-end="url(#arrow)"/>'
        )

    node_svg = ""
    for sid in ids:
        x, y = pos[sid]
        t = titles.get(sid, "")
        if len(t) > 22:
            t = t[:21] + "…"
        node_svg += f"""
        <g class="fnode is-approve" data-node="{esc(sid)}" transform="translate({x:.0f},{y:.0f})">
          <rect class="fnode-box" width="{NW}" height="{NH}" rx="10"/>
          <circle class="fnode-dot" cx="18" cy="{NH/2:.0f}" r="11"/>
          <text class="fnode-num" x="18" y="{NH/2+4:.0f}" text-anchor="middle">{esc(sid)}</text>
          <text class="fnode-title" x="38" y="{NH/2+4:.0f}">{esc(t)}</text>
        </g>
        """

    return f"""
    <section class="block">
      <h2>Plan flow</h2>
      <div class="sim-hint">How the steps connect. Boxes recolor with your approve / reject / modify choices below.</div>
      <div class="flow-wrap">
        <svg class="flow-svg" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}" role="img" aria-label="Plan dependency flow">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#b8b1a4"/>
            </marker>
          </defs>
          {edge_svg}
          {node_svg}
        </svg>
      </div>
    </section>
    """


ENTITY_ICONS = {
    "service": "🧩", "datastore": "🗄️", "db": "🗄️", "database": "🗄️",
    "ui": "🪟", "screen": "🪟", "page": "🪟", "concept": "💡",
    "actor": "🧑", "user": "🧑", "external": "🌐", "thirdparty": "🌐",
    "queue": "📨", "event": "📨", "job": "⏱️", "cron": "⏱️",
    "api": "🔌", "endpoint": "🔌", "file": "📄", "config": "⚙️", "data": "📦",
}


def _entity_icon(kind):
    return ENTITY_ICONS.get((kind or "").strip().lower(), "▪️")


def compute_stage(plan):
    """Fold the plan into a sequence of system-state frames.

    Frame 0 = `current`; each subsequent frame applies one step's `changes`
    (add/modify/remove of entities) onto the running state; the final frame
    overlays optional `future` notes. Returns None when no entities are
    declared — the stage only earns its place when there's a system to show.
    """
    entities = plan.get("entities") or []
    if not entities:
        return None
    steps = plan.get("steps", []) or []

    eids, meta = [], {}
    for i, e in enumerate(entities):
        eid = str(e.get("id", e.get("label", f"e{i}")))
        eids.append(eid)
        meta[eid] = {"id": eid, "label": str(e.get("label", eid)), "icon": _entity_icon(e.get("kind"))}

    current = plan.get("current") or {}
    run = {}
    for eid in eids:
        c = current.get(eid) if isinstance(current.get(eid), dict) else {}
        run[eid] = {"present": bool(c.get("present", True)), "state": str(c.get("state", ""))}

    def snapshot(delta):
        return {eid: {"present": run[eid]["present"], "state": run[eid]["state"], "delta": delta.get(eid)} for eid in eids}

    stops = [{
        "key": "now", "label": "Now", "sub": "Current state",
        "caption": str(plan.get("summary", "") or "How things stand today."),
        "states": snapshot({}),
    }]

    for i, s in enumerate(steps):
        sid = str(s.get("id", str(i + 1)))
        delta = {}
        for ch in (s.get("changes") or []):
            eid = str(ch.get("entity", ""))
            if eid not in run:
                continue
            op = (ch.get("op") or "modify").strip().lower()
            run[eid]["present"] = (op != "remove")
            if ch.get("state") is not None:
                run[eid]["state"] = str(ch.get("state"))
            delta[eid] = op
        stops.append({
            "key": sid, "label": f"Step {sid}", "sub": str(s.get("title", "")),
            "caption": str(s.get("detail", "") or s.get("title", "")),
            "states": snapshot(delta),
        })

    future = plan.get("future") or {}
    for eid, fv in future.items():
        if eid in run and isinstance(fv, dict):
            if fv.get("state") is not None:
                run[eid]["state"] = str(fv.get("state"))
            if "present" in fv:
                run[eid]["present"] = bool(fv.get("present"))
    stops.append({
        "key": "done", "label": "Done", "sub": "Future state",
        "caption": str(plan.get("outcome", "") or "The system once every step is done."),
        "states": snapshot({}),
    })

    return {"entities": [meta[eid] for eid in eids], "stops": stops}


def render_stage(stage):
    if not stage:
        return ""
    # Embed as JSON; neutralize "</" so it can't terminate the <script> early.
    data = json.dumps(stage, ensure_ascii=False).replace("</", "<\\/")
    return f"""
    <section class="block stage-block">
      <h2>What changes</h2>
      <div class="sim-hint">Step through the plan and watch the system move from now to done — ◀ / ▶ or Play, or click a point on the timeline.</div>
      <div class="stage">
        <div class="timeline" id="timeline"></div>
        <div class="stage-controls">
          <button class="stage-nav" id="stage-prev" type="button">◀ Back</button>
          <button class="stage-play" id="stage-play" type="button">▶ Play</button>
          <button class="stage-nav" id="stage-next" type="button">Next ▶</button>
          <div class="stage-pos" id="stage-pos"></div>
        </div>
        <div class="stage-caption" id="stage-caption"></div>
        <div class="entity-grid" id="entity-grid"></div>
      </div>
      <script id="stage-data" type="application/json">{data}</script>
    </section>
    """


def _norm_file(f):
    """A step's file may be a bare path string or {path, op}. op ∈ new|edit|delete."""
    if isinstance(f, dict):
        return str(f.get("path", "")), (str(f.get("op")).lower() if f.get("op") else None)
    return str(f), None


def render_file_tree(steps):
    """Aggregate every step's files into a real directory tree with new/edit/
    delete markers and the steps that touch each — the plan's blast radius on
    the actual repo layout (grounding: real paths, not abstractions)."""
    entries = {}
    for i, s in enumerate(steps):
        sid = str(s.get("id", str(i + 1)))
        for f in (s.get("files") or []):
            path, op = _norm_file(f)
            if not path:
                continue
            e = entries.setdefault(path, {"op": None, "steps": []})
            if op:
                e["op"] = op
            if sid not in e["steps"]:
                e["steps"].append(sid)
    if not entries:
        return ""

    tree = {}
    for path in sorted(entries):
        parts = [p for p in path.split("/") if p]
        node = tree
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node.setdefault("__files__", []).append((parts[-1] if parts else path, path))

    op_badge = {
        "new": '<span class="ft-op ft-new">+ new</span>',
        "edit": '<span class="ft-op ft-edit">~ edit</span>',
        "delete": '<span class="ft-op ft-del">− delete</span>',
    }

    def render_node(node):
        out = ""
        for name in sorted(k for k in node if k != "__files__"):
            out += f'<li class="ft-dir"><span class="ft-name">{esc(name)}/</span><ul>{render_node(node[name])}</ul></li>'
        for fname, full in node.get("__files__", []):
            e = entries[full]
            badge = op_badge.get(e["op"], "")
            steps_lbl = ", ".join(e["steps"])
            out += (f'<li class="ft-file"><span class="ft-name">{esc(fname)}</span> {badge}'
                    f'<span class="ft-steps">step {esc(steps_lbl)}</span></li>')
        return out

    return f"""
    <section class="block">
      <h2>Files touched</h2>
      <div class="sim-hint">The real repo paths this plan changes — its blast radius.</div>
      <ul class="filetree">{render_node(tree)}</ul>
    </section>
    """


def render_open_questions(qs):
    """Single bottom block of decisions needing the reviewer's judgment.
    Answers are collected into the pasted decision (Q<id>: ...)."""
    if not qs:
        return ""
    rows = ""
    for i, q in enumerate(qs):
        qid = str(q.get("id", f"q{i + 1}"))
        text = esc(q.get("question", ""))
        note = q.get("note", "")
        note_html = f'<div class="oq-note">{esc(note)}</div>' if note else ""
        rows += f"""
        <div class="oq">
          <div class="oq-q"><span class="oq-tag">{esc(qid)}</span>{text}</div>
          {note_html}
          <textarea class="oq-answer" data-qid="{esc(qid)}" placeholder="Your call (leave blank to defer)"></textarea>
        </div>"""
    return f"""
    <section class="block oq-block">
      <h2>Open questions</h2>
      <div class="sim-hint">Decisions that need your judgment. Answers ride back with the decision below.</div>
      {rows}
    </section>
    """


def render_html(plan):
    title = esc(plan.get("title", "Plan"))
    summary = esc(plan.get("summary", ""))
    steps = plan.get("steps", []) or []
    alts = plan.get("alternatives", []) or []
    sim = plan.get("simulation")

    steps_html = "".join(render_step(s, i) for i, s in enumerate(steps))
    flow_html = render_flow(steps)
    stage_html = render_stage(compute_stage(plan))
    tree_html = render_file_tree(steps)
    questions_html = render_open_questions(plan.get("open_questions"))
    alts_html = ""
    if alts:
        cards = "".join(render_alternative(a, i) for i, a in enumerate(alts))
        alts_html = f"""
        <section class="block">
          <h2>Alternative paths</h2>
          <div class="sim-hint">Optional — pick one to swap the plan.</div>
          <div class="alt-grid">{cards}</div>
        </section>
        """
    sim_html = render_simulation(sim) if sim else ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — Visual Plan</title>
<style>
  :root {{
    --bg: #faf7f2;
    --panel: #fff;
    --ink: #1f1d29;
    --muted: #6b6678;
    --line: #e7e2d8;
    --accent: #6b4eff;
    --ok: #2f9e6b;
    --warn: #c4733a;
    --bad: #c1453d;
    --chip: #efe9dd;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
    background: var(--bg); color: var(--ink); line-height: 1.5;
  }}
  header {{
    padding: 32px 48px 16px; border-bottom: 1px solid var(--line);
    background: linear-gradient(180deg, #fffdf8 0%, var(--bg) 100%);
  }}
  header h1 {{ margin: 0 0 6px; font-size: 26px; }}
  header .summary {{ color: var(--muted); max-width: 720px; }}
  main {{ padding: 24px 48px 120px; max-width: 1100px; }}
  h2 {{ font-size: 16px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 28px 0 12px; }}
  .block {{ margin-bottom: 8px; }}

  .step {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 16px 18px; margin-bottom: 10px;
  }}
  .step-head {{ display: grid; grid-template-columns: 32px 1fr auto; gap: 14px; align-items: start; }}
  .step-num {{
    width: 28px; height: 28px; border-radius: 8px; background: var(--accent); color: #fff;
    display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 13px;
  }}
  .step-title {{ font-weight: 600; font-size: 15px; }}
  .step-detail {{ color: var(--muted); font-size: 14px; margin-top: 2px; }}
  .badge-opt {{
    background: var(--chip); color: var(--muted); font-size: 11px;
    padding: 1px 8px; border-radius: 999px; margin-left: 6px; font-weight: 500;
  }}
  .files {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }}
  .chip {{
    background: var(--chip); color: var(--ink); font-family: ui-monospace, Menlo, monospace;
    font-size: 11px; padding: 2px 8px; border-radius: 4px;
  }}

  .step-actions {{ display: flex; gap: 4px; }}
  .step-actions .btn {{
    cursor: pointer; padding: 6px 10px; border: 1px solid var(--line);
    border-radius: 6px; font-size: 12px; background: #fff;
    display: inline-flex; align-items: center; gap: 4px; user-select: none;
  }}
  .step-actions input {{ accent-color: var(--accent); }}
  .step.is-approve {{ border-color: var(--ok); box-shadow: inset 3px 0 0 var(--ok); }}
  .step.is-reject {{ border-color: var(--bad); box-shadow: inset 3px 0 0 var(--bad); opacity: 0.7; }}
  .step.is-modify {{ border-color: var(--warn); box-shadow: inset 3px 0 0 var(--warn); }}
  .modify-note {{
    display: none; width: 100%; margin-top: 10px; padding: 8px 10px;
    border: 1px solid var(--line); border-radius: 6px; font: inherit; resize: vertical; min-height: 60px;
  }}
  .step.is-modify .modify-note {{ display: block; }}

  /* Before / after */
  .ba {{
    display: grid; grid-template-columns: 1fr 20px 1fr; gap: 8px; align-items: stretch;
    margin: 12px 0 2px;
  }}
  .ba-col {{ border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
  .ba-label {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.07em;
    padding: 4px 10px; color: var(--muted); border-bottom: 1px solid var(--line);
  }}
  .ba-before .ba-label {{ background: #fdf3f1; color: var(--bad); }}
  .ba-after  .ba-label {{ background: #eef8f2; color: var(--ok); }}
  .ba-body {{
    padding: 8px 10px; font-family: ui-monospace, Menlo, monospace; font-size: 12px;
    white-space: pre-wrap; word-break: break-word; color: var(--ink);
  }}
  .ba-arrow {{ align-self: center; text-align: center; color: var(--muted); font-size: 16px; }}

  /* Plan flow graph */
  .flow-wrap {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 16px; overflow-x: auto;
  }}
  .flow-svg {{ display: block; max-width: 100%; height: auto; }}
  .fedge {{ fill: none; stroke: #cfc8ba; stroke-width: 1.6; }}
  .fnode-box {{ fill: #fff; stroke: var(--line); stroke-width: 1.5; transition: stroke .15s, fill .15s; }}
  .fnode-dot {{ fill: var(--accent); transition: fill .15s; }}
  .fnode-num {{ fill: #fff; font-size: 12px; font-weight: 600; }}
  .fnode-title {{ fill: var(--ink); font-size: 12px; font-weight: 500; }}
  .fnode.is-approve .fnode-box {{ stroke: var(--ok); }}
  .fnode.is-approve .fnode-dot {{ fill: var(--ok); }}
  .fnode.is-reject  .fnode-box {{ stroke: var(--bad); opacity: 0.85; }}
  .fnode.is-reject  .fnode-dot {{ fill: var(--bad); }}
  .fnode.is-reject  .fnode-title {{ fill: var(--muted); text-decoration: line-through; }}
  .fnode.is-modify  .fnode-box {{ stroke: var(--warn); }}
  .fnode.is-modify  .fnode-dot {{ fill: var(--warn); }}

  .alt-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
  .alt-card {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
  }}
  .alt-pick {{ display: flex; align-items: center; gap: 8px; cursor: pointer; }}
  .alt-name {{ font-weight: 600; }}
  .alt-trade {{ color: var(--muted); font-size: 13px; margin: 8px 0; }}
  .alt-steps {{ margin: 6px 0 0 18px; padding: 0; font-size: 13px; color: var(--ink); }}
  .alt-card:has(input:checked) {{ border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }}

  .sim-frame {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 18px; min-height: 220px; position: relative;
  }}
  .sim-title {{ font-weight: 600; margin-bottom: 8px; font-size: 14px; color: var(--muted); }}
  .sim-body {{ padding: 12px; background: #fbf9f4; border-radius: 8px; border: 1px dashed var(--line); margin-bottom: 14px; }}
  .sim-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .sim-btn {{
    cursor: pointer; padding: 8px 14px; border: 1px solid var(--accent);
    background: var(--accent); color: #fff; border-radius: 6px; font: inherit; font-size: 13px;
  }}
  .sim-btn:hover {{ filter: brightness(1.08); }}
  .sim-end {{ color: var(--muted); font-style: italic; font-size: 13px; }}
  .sim-reset {{
    position: absolute; top: 12px; right: 12px; background: transparent; border: none;
    color: var(--muted); cursor: pointer; font-size: 12px;
  }}
  .sim-hint {{ color: var(--muted); font-size: 13px; margin-bottom: 8px; }}

  /* State-evolution stage (the hero) */
  .stage {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px;
  }}
  .timeline {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }}
  .tl-pill {{
    display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line);
    background: #fff; color: var(--muted); border-radius: 999px; padding: 5px 12px;
    font: inherit; font-size: 12px; cursor: pointer; transition: all .15s;
  }}
  .tl-pill .tl-dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--line); transition: background .15s; }}
  .tl-pill.active {{ border-color: var(--accent); color: var(--ink); font-weight: 600; box-shadow: 0 0 0 2px rgba(107,78,255,.12); }}
  .tl-pill.active .tl-dot {{ background: var(--accent); }}
  .stage-controls {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }}
  .stage-nav, .stage-play {{
    border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 7px 12px;
    font: inherit; font-size: 13px; cursor: pointer;
  }}
  .stage-play {{ border-color: var(--accent); color: var(--accent); font-weight: 600; }}
  .stage-pos {{ margin-left: auto; color: var(--muted); font-size: 12px; }}
  .stage-caption {{
    color: var(--ink); font-size: 14px; min-height: 22px; margin-bottom: 14px;
    padding: 6px 0 6px 12px; border-left: 3px solid var(--accent);
    background: linear-gradient(90deg, rgba(107,78,255,.06), transparent);
  }}
  .entity-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; }}
  .ent-card {{
    position: relative; display: flex; gap: 10px; align-items: flex-start;
    border: 1px solid var(--line); border-radius: 10px; padding: 12px; background: #fff;
    transition: opacity .35s ease, border-color .35s ease, box-shadow .35s ease, transform .2s ease;
  }}
  .ent-ico {{ font-size: 20px; line-height: 1; }}
  .ent-label {{ font-weight: 600; font-size: 14px; }}
  .ent-state {{ color: var(--muted); font-size: 13px; margin-top: 3px; transition: color .35s; }}
  .ent-badge {{
    position: absolute; top: 8px; right: 10px; font-size: 9px; font-weight: 700;
    letter-spacing: .06em; padding: 2px 6px; border-radius: 999px;
  }}
  .ent-card.absent {{ opacity: .4; border-style: dashed; }}
  .ent-card.d-add {{ border-color: var(--ok); box-shadow: 0 0 0 2px rgba(47,158,107,.18); transform: translateY(-1px); }}
  .ent-card.d-add .ent-badge {{ background: var(--ok); color: #fff; }}
  .ent-card.d-modify {{ border-color: var(--warn); box-shadow: 0 0 0 2px rgba(196,115,58,.18); }}
  .ent-card.d-modify .ent-badge {{ background: var(--warn); color: #fff; }}
  .ent-card.d-remove {{ border-color: var(--bad); }}
  .ent-card.d-remove .ent-badge {{ background: var(--bad); color: #fff; }}
  .ent-card.d-remove .ent-label {{ text-decoration: line-through; }}

  /* Hard-to-reverse flag */
  .badge-stakes {{
    background: var(--bad); color: #fff; font-size: 11px; font-weight: 600;
    padding: 1px 8px; border-radius: 999px; margin-left: 6px; white-space: nowrap;
  }}
  .step.stakes-high {{ box-shadow: inset 3px 0 0 var(--bad), 0 0 0 1px rgba(193,69,61,.25); }}

  /* File tree */
  .filetree, .filetree ul {{ list-style: none; margin: 0; padding-left: 16px; }}
  .filetree {{ padding-left: 2px; font-family: ui-monospace, Menlo, monospace; font-size: 13px; }}
  .ft-dir > .ft-name {{ color: var(--muted); font-weight: 600; }}
  .ft-file {{ display: flex; align-items: center; gap: 8px; padding: 1px 0; }}
  .ft-file .ft-name {{ color: var(--ink); }}
  .ft-op {{ font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px; }}
  .ft-new {{ background: #eef8f2; color: var(--ok); }}
  .ft-edit {{ background: #fdf6ee; color: var(--warn); }}
  .ft-del {{ background: #fdf3f1; color: var(--bad); }}
  .ft-steps {{ color: var(--muted); font-size: 11px; }}

  /* Open questions */
  .oq-block {{ border-top: 1px dashed var(--line); padding-top: 8px; }}
  .oq {{
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 10px;
  }}
  .oq-q {{ font-size: 14px; font-weight: 500; }}
  .oq-tag {{
    display: inline-block; background: var(--accent); color: #fff; font-size: 11px; font-weight: 700;
    padding: 1px 7px; border-radius: 999px; margin-right: 8px; text-transform: uppercase;
  }}
  .oq-note {{ color: var(--muted); font-size: 13px; margin: 6px 0 0; }}
  .oq-answer {{
    display: block; width: 100%; margin-top: 8px; padding: 8px 10px; border: 1px solid var(--line);
    border-radius: 6px; font: inherit; resize: vertical; min-height: 44px;
  }}

  .copybar {{
    position: fixed; bottom: 0; left: 0; right: 0; background: var(--ink); color: #fff;
    padding: 14px 48px; display: flex; gap: 14px; align-items: center; justify-content: space-between;
    box-shadow: 0 -2px 12px rgba(0,0,0,0.12);
  }}
  .copybar-summary {{ font-size: 13px; opacity: 0.85; }}
  .copybar-summary b {{ color: #fff; }}
  .copybtn {{
    background: var(--accent); color: #fff; border: none; padding: 10px 18px;
    border-radius: 8px; font: inherit; font-weight: 600; cursor: pointer; font-size: 14px;
  }}
  .copybtn.copied {{ background: var(--ok); }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="summary">{summary}</div>
</header>
<main>
  {stage_html}
  {flow_html}
  <section class="block">
    <h2>Plan steps</h2>
    {steps_html}
  </section>
  {tree_html}
  {alts_html}
  {sim_html}
  {questions_html}
</main>

<div class="copybar">
  <div class="copybar-summary" id="summary">…</div>
  <button class="copybtn" id="copybtn">Copy decision</button>
</div>

<script>
  // State-evolution stage: render system-state frames, driven by timeline / play
  (function() {{
    const dataEl = document.getElementById('stage-data');
    if (!dataEl) return;
    let STAGE;
    try {{ STAGE = JSON.parse(dataEl.textContent); }} catch (e) {{ return; }}
    const stops = STAGE.stops || [], ents = STAGE.entities || [];
    if (!stops.length || !ents.length) return;

    const tl = document.getElementById('timeline');
    const grid = document.getElementById('entity-grid');
    const cap = document.getElementById('stage-caption');
    const posEl = document.getElementById('stage-pos');
    const playBtn = document.getElementById('stage-play');
    let idx = 0, timer = null;

    // Timeline pills
    stops.forEach((s, i) => {{
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'tl-pill';
      const dot = document.createElement('span'); dot.className = 'tl-dot';
      b.appendChild(dot); b.appendChild(document.createTextNode(s.label || ('#' + i)));
      b.addEventListener('click', () => {{ stopPlay(); go(i); }});
      tl.appendChild(b);
    }});

    // Entity cards (built once; textContent only — no injection)
    const cards = {{}};
    ents.forEach(e => {{
      const card = document.createElement('div'); card.className = 'ent-card';
      const ico = document.createElement('div'); ico.className = 'ent-ico'; ico.textContent = e.icon || '▪️';
      const body = document.createElement('div'); body.className = 'ent-body';
      const lab = document.createElement('div'); lab.className = 'ent-label'; lab.textContent = e.label || e.id;
      const stt = document.createElement('div'); stt.className = 'ent-state';
      body.appendChild(lab); body.appendChild(stt);
      const badge = document.createElement('div'); badge.className = 'ent-badge';
      card.appendChild(ico); card.appendChild(body); card.appendChild(badge);
      grid.appendChild(card);
      cards[e.id] = {{ card: card, state: stt, badge: badge }};
    }});

    function render() {{
      const stop = stops[idx];
      cap.textContent = stop.caption || '';
      posEl.textContent = (idx + 1) + ' / ' + stops.length + '  ·  ' + (stop.sub || '');
      Array.from(tl.children).forEach((p, i) => p.classList.toggle('active', i === idx));
      ents.forEach(e => {{
        const st = (stop.states && stop.states[e.id]) || {{}};
        const ref = cards[e.id];
        ref.card.classList.toggle('absent', !st.present);
        ref.card.classList.remove('d-add', 'd-modify', 'd-remove');
        if (st.delta === 'add') {{ ref.card.classList.add('d-add'); ref.badge.textContent = 'NEW'; }}
        else if (st.delta === 'modify') {{ ref.card.classList.add('d-modify'); ref.badge.textContent = 'CHANGED'; }}
        else if (st.delta === 'remove') {{ ref.card.classList.add('d-remove'); ref.badge.textContent = 'REMOVED'; }}
        else {{ ref.badge.textContent = ''; }}
        ref.state.textContent = st.state || (st.present ? '' : '—');
      }});
    }}
    function go(i) {{ idx = Math.max(0, Math.min(stops.length - 1, i)); render(); }}
    function stopPlay() {{ if (timer) {{ clearInterval(timer); timer = null; playBtn.textContent = '▶ Play'; }} }}

    document.getElementById('stage-prev').addEventListener('click', () => {{ stopPlay(); go(idx - 1); }});
    document.getElementById('stage-next').addEventListener('click', () => {{ stopPlay(); go(idx + 1); }});
    playBtn.addEventListener('click', () => {{
      if (timer) {{ stopPlay(); return; }}
      if (idx >= stops.length - 1) go(0);
      playBtn.textContent = '⏸ Pause';
      timer = setInterval(() => {{ if (idx >= stops.length - 1) stopPlay(); else go(idx + 1); }}, 1500);
    }});
    render();
  }})();

  // Keep the flow-graph node for a step in sync with its decision color
  function syncFlowNode(id, value) {{
    const node = document.querySelector('.fnode[data-node="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]');
    if (!node) return;
    node.classList.remove('is-approve', 'is-reject', 'is-modify');
    node.classList.add('is-' + value);
  }}

  // Step highlight + modify textarea reveal + flow-node sync
  document.querySelectorAll('.step').forEach(step => {{
    const radios = step.querySelectorAll('input[type=radio]');
    radios.forEach(r => r.addEventListener('change', () => {{
      step.classList.remove('is-approve', 'is-reject', 'is-modify');
      step.classList.add('is-' + r.value);
      syncFlowNode(step.dataset.stepId, r.value);
      updateSummary();
    }}));
    step.classList.add('is-approve');
  }});

  // Alternatives pick updates summary
  document.querySelectorAll('input[name="alt-pick"]').forEach(r =>
    r.addEventListener('change', updateSummary));

  // Simulation navigation
  const frame = document.querySelector('.sim-frame');
  if (frame) {{
    const start = frame.dataset.start;
    const screens = frame.querySelectorAll('.sim-screen');
    function show(id) {{
      screens.forEach(s => s.style.display = s.dataset.screen === id ? 'block' : 'none');
    }}
    show(start);
    frame.querySelectorAll('.sim-btn').forEach(b =>
      b.addEventListener('click', () => show(b.dataset.next)));
    frame.querySelector('.sim-reset').addEventListener('click', () => show(start));
  }}

  // Decision summary builder
  function buildDecision() {{
    const approved = [], rejected = [], modified = [];
    document.querySelectorAll('.step').forEach(step => {{
      const id = step.dataset.stepId;
      const picked = step.querySelector('input[type=radio]:checked');
      if (!picked) return;
      if (picked.value === 'approve') approved.push(id);
      else if (picked.value === 'reject') rejected.push(id);
      else if (picked.value === 'modify') {{
        const note = step.querySelector('.modify-note').value.trim() || '(no note)';
        modified.push({{ id, note }});
      }}
    }});
    const altPick = document.querySelector('input[name="alt-pick"]:checked');
    let out = '';
    out += 'APPROVED: ' + (approved.join(', ') || '(none)') + '\\n';
    out += 'REJECTED: ' + (rejected.join(', ') || '(none)') + '\\n';
    modified.forEach(m => out += `MODIFY ${{m.id}}: ${{m.note}}\\n`);
    if (altPick) out += 'ALT: ' + altPick.value + '\\n';
    document.querySelectorAll('.oq-answer').forEach(t => {{
      const v = t.value.trim();
      if (v) out += (t.dataset.qid || 'Q').toUpperCase() + ': ' + v + '\\n';
    }});
    return out.trim();
  }}
  function updateSummary() {{
    const d = buildDecision();
    const first = d.split('\\n').slice(0, 2).join(' · ');
    document.getElementById('summary').innerHTML = first;
  }}
  updateSummary();

  document.getElementById('copybtn').addEventListener('click', async () => {{
    const txt = buildDecision();
    try {{
      await navigator.clipboard.writeText(txt);
      const b = document.getElementById('copybtn');
      b.textContent = 'Copied — paste in chat';
      b.classList.add('copied');
      setTimeout(() => {{ b.textContent = 'Copy decision'; b.classList.remove('copied'); }}, 2400);
    }} catch (e) {{
      prompt('Copy this:', txt);
    }}
  }});
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        print("usage: render_plan.py <plan.json>", file=sys.stderr)
        sys.exit(2)
    plan_path = Path(sys.argv[1])
    plan = json.loads(plan_path.read_text())
    out_dir = Path("/tmp")
    ts = int(time.time())
    out = out_dir / f"claude-plan-{ts}.html"
    out.write_text(render_html(plan))
    # Sentinel for PreToolUse gate on ExitPlanMode — agent has visualized, allow exit.
    # Path is per-session so concurrent sessions never clobber each other's pass.
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    (out_dir / f"visual-plan-ready-{session_id}").write_text(str(out))
    print(str(out))
    if sys.platform == "darwin":
        subprocess.run(["open", str(out)], check=False)
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", str(out)], check=False)


if __name__ == "__main__":
    main()
