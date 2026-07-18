#!/usr/bin/env python3
"""Render a Trip Dashboard state JSON into an interactive corkboard/map webpage.

Usage: python3 render_dashboard.py <path-to-dashboard_state.json>
Writes dashboard.html next to the state file and opens it (macOS `open` /
Linux `xdg-open`). Everything here is deterministic templating — no network
calls, no LLM involved — the only network traffic at view time is the
reader's own browser fetching the Leaflet library and OpenStreetMap tiles,
and only when the state actually has coordinates to plot.
"""
import html
import json
import math
import os
import subprocess
import sys
from pathlib import Path

NUM_COLS = 4
COL_WIDTH = 250
GAP = 20


def esc(s):
    return html.escape(str(s), quote=True)


def est_height(text, label_lines=1):
    """Rough card height from text length — good enough for initial packing;
    dragging fixes any visual overlap by hand, so this doesn't need to be exact."""
    chars_per_line = 30
    lines = max(1, math.ceil(len(str(text)) / chars_per_line))
    return 54 + label_lines * 16 + lines * 18


class Packer:
    """Greedy shortest-column masonry packer — places each card in whichever
    column is currently shortest, like scattering notes across a board left
    to right. Pure layout math, computed once at render time."""

    def __init__(self, cols=NUM_COLS, col_width=COL_WIDTH, gap=GAP):
        self.cols = cols
        self.col_width = col_width
        self.gap = gap
        self.heights = [gap] * cols

    def place(self, height):
        idx = min(range(self.cols), key=lambda i: self.heights[i])
        x = idx * (self.col_width + self.gap)
        y = self.heights[idx]
        self.heights[idx] += height + self.gap
        return x, y

    @property
    def board_height(self):
        return max(self.heights) + 40

    @property
    def board_width(self):
        return self.cols * (self.col_width + self.gap) + self.gap


STATUS_META = {
    "confirmed": ("#2f9e6b", "#eef8f2", "confirmed"),
    "pending": ("#c4733a", "#fdf3ea", "pending"),
    "seasonal_conflict": ("#c4733a", "#fdf3ea", "seasonal conflict — see note"),
    "cut": ("#8a8578", "#efece3", "cut"),
}


def note_card(packer, kind, filter_key, label, title, body, color, bg, extra=""):
    h = est_height(f"{title} {body}")
    x, y = packer.place(h)
    rot = ((hash(title) % 7) - 3) * 0.6
    return f"""
    <div class="note note-{kind}" data-filter="{esc(filter_key)}" style="left:{x}px;top:{y}px;width:{COL_WIDTH}px;
         --pin:{color};--rot:{rot:.1f}deg;">
      <div class="note-label" style="color:{color};">{esc(label)}</div>
      <div class="note-title">{esc(title)}</div>
      <div class="note-body">{body}</div>
      {extra}
    </div>
    """


def render_profile_notes(packer, profile):
    fields = [
        ("Travelers", profile.get("travelers")),
        ("Dates", profile.get("dates")),
        ("Budget", profile.get("budget")),
        ("Travel style", profile.get("style")),
        ("Accommodation", profile.get("accommodation")),
    ]
    out = ""
    for label, val in fields:
        if not val:
            continue
        out += note_card(packer, "profile", "profile", "PROFILE", label, esc(val), "#4a6fa5", "#eef2f8")
    return out


def render_wishlist_notes(packer, wishlist):
    out = ""
    for item in wishlist or []:
        status = item.get("status", "pending")
        color, bg, status_label = STATUS_META.get(status, STATUS_META["pending"])
        strike = "text-decoration:line-through;opacity:.65;" if status == "cut" else ""
        body = f'<div style="{strike}">{esc(item.get("note", ""))}</div>' if item.get("note") else ""
        out += note_card(
            packer, "wishlist", f"wishlist-{status}", f"WISHLIST · {status_label}",
            item.get("item", ""), body, color, bg
        )
    return out


def render_agent_notes(packer, notes):
    out = ""
    for n in notes or []:
        out += note_card(packer, "agent", "agent", "AGENT NOTE", "", f"<div>{esc(n)}</div>", "#8b6fc4", "#f2eefa")
    return out


def render_rejected_notes(packer, rejected):
    out = ""
    for r in rejected or []:
        body = f'<div class="reason">Why: {esc(r.get("reason", ""))}</div>'
        out += note_card(packer, "rejected", "rejected", "PARKED / REJECTED", r.get("item", ""), body, "#c1453d", "#fdeeed")
    return out


def render_pending_notes(packer, pending):
    out = ""
    for i, p in enumerate(pending or [], 1):
        out += note_card(packer, "pending", "pending", "PENDING DECISION", f"{i}.", esc(p), "#b8952e", "#fbf6e6")
    return out


def render_map(wishlist, architecture):
    legs = (architecture or {}).get("legs") or []
    legs = sorted(legs, key=lambda l: l.get("order", 0))
    route_pts = [[l["lat"], l["lng"]] for l in legs if "lat" in l and "lng" in l]
    candidates = [
        w for w in (wishlist or []) if "lat" in w and "lng" in w and w.get("status") != "cut"
    ]

    if not route_pts and not candidates:
        return """
        <section class="block">
          <h2>Route map</h2>
          <div class="map-placeholder">Map fills in once locations have coordinates — candidate
          pins can appear as early as Discovery, the connected route once a Big Picture path is locked.</div>
        </section>
        """

    markers = []
    for l in legs:
        if "lat" in l and "lng" in l:
            popup = esc(l.get("name", ""))
            if l.get("nights"):
                popup += f" — {esc(l['nights'])} nights"
            if l.get("note"):
                popup += f"<br>{esc(l['note'])}"
            markers.append({"lat": l["lat"], "lng": l["lng"], "popup": popup, "kind": "leg"})
    for w in candidates:
        color, _, status_label = STATUS_META.get(w.get("status", "pending"), STATUS_META["pending"])
        popup = f"{esc(w.get('item',''))} <em>({status_label}, not yet locked)</em>"
        markers.append({"lat": w["lat"], "lng": w["lng"], "popup": popup, "kind": "candidate", "color": color})

    return f"""
    <section class="block">
      <h2>Route map</h2>
      <div class="map-legend">Large purple pin = locked route leg, in order · small colored pin = wishlist candidate, colored by its status above</div>
      <div id="map"></div>
    </section>
    <script>
      (function() {{
        const markers = {json.dumps(markers)};
        const route = {json.dumps(route_pts)};
        const map = L.map('map');
        // Esri's basemap (not raw OSM raster tiles) labels places in English worldwide —
        // plain OSM tiles render each region's local script, which is unreadable for an
        // English-speaking user planning a trip somewhere like Japan or Thailand.
        L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
          maxZoom: 19,
          attribution: 'Tiles &copy; Esri — Esri, HERE, Garmin, FAO, NOAA, USGS'
        }}).addTo(map);
        const bounds = [];
        markers.forEach(m => {{
          const color = m.kind === 'leg' ? '#6b4eff' : m.color;
          const marker = L.circleMarker([m.lat, m.lng], {{
            radius: m.kind === 'leg' ? 9 : 6, color, fillColor: color, fillOpacity: 0.85, weight: 2
          }}).addTo(map);
          marker.bindPopup(m.popup);
          bounds.push([m.lat, m.lng]);
        }});
        if (route.length > 1) {{
          L.polyline(route, {{color: '#6b4eff', weight: 3, dashArray: '6 8'}}).addTo(map);
        }}
        if (bounds.length) {{
          map.fitBounds(bounds, {{padding: [30, 30]}});
        }} else {{
          map.setView([0, 0], 2);
        }}
      }})();
    </script>
    """


def render_memory_log(log, total=None, archive_path=None):
    if not log:
        return ""
    entries = sorted(log, key=lambda e: e.get("turn", 0), reverse=True)
    rows = "".join(
        f'<div class="log-row"><span class="log-turn">Turn {esc(e.get("turn", "?"))}</span>'
        f'<span class="log-summary">{esc(e.get("summary", ""))}</span></div>'
        for e in entries
    )
    archive_note = ""
    if total and total > len(entries):
        older = total - len(entries)
        where = f" — full history in {esc(archive_path)}" if archive_path else ""
        archive_note = f'<div class="log-archive-note">+{older} earlier entries archived{where}</div>'
    return f"""
    <section class="block">
      <details class="log">
        <summary>Memory log — showing {len(entries)}{f' of {total}' if total else ''} entries (most recent first)</summary>
        <div class="log-body">{rows}{archive_note}</div>
      </details>
    </section>
    """


def render_html(state):
    title = esc(state.get("trip_title", "Trip Dashboard"))
    version = esc(state.get("version", "1.0"))
    phase = state.get("phase", {}) or {}
    phase_html = (
        f'Phase {esc(phase.get("number", "?"))}: {esc(phase.get("name", ""))}'
        f' — {esc(phase.get("note", ""))}'
    )
    architecture = state.get("architecture") or {}
    chosen_path = architecture.get("chosen_path")
    arch_html = (
        f'<div class="arch-banner">Locked path: <b>{esc(chosen_path)}</b></div>'
        if chosen_path
        else '<div class="arch-banner muted">No Big Picture path locked yet.</div>'
    )

    packer = Packer()
    notes_html = (
        render_profile_notes(packer, state.get("profile", {}))
        + render_wishlist_notes(packer, state.get("wishlist", []))
        + render_agent_notes(packer, state.get("agent_notes", []))
        + render_rejected_notes(packer, state.get("rejected", []))
        + render_pending_notes(packer, state.get("pending_decisions", []))
    )
    map_html = render_map(state.get("wishlist", []), architecture)
    log_html = render_memory_log(
        state.get("memory_log", []),
        total=state.get("memory_log_total"),
        archive_path=state.get("memory_log_archive_path"),
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — Trip Dashboard</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {{
    --bg: #f4ede1; --ink: #2b2620; --muted: #746b5c; --line: #ddd2bc;
    --cork: #cf9f6f;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
    background: var(--bg); color: var(--ink); line-height: 1.45;
  }}
  header {{ padding: 28px 40px 16px; border-bottom: 1px solid var(--line); }}
  header h1 {{ margin: 0 0 4px; font-size: 24px; }}
  .phase-banner {{ color: var(--muted); font-size: 14px; }}
  .version {{ float: right; color: var(--muted); font-size: 12px; }}
  .arch-banner {{
    margin-top: 10px; font-size: 14px; background: #eef8f2; color: #2f7a52;
    display: inline-block; padding: 6px 14px; border-radius: 999px;
  }}
  .arch-banner.muted {{ background: var(--line); color: var(--muted); }}

  main {{ padding: 20px 40px 60px; max-width: 1200px; margin: 0 auto; }}
  h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin: 24px 0 10px; }}
  .block {{ margin-bottom: 8px; }}

  #map {{ height: 360px; border-radius: 12px; border: 1px solid var(--line); }}
  .map-legend {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
  .map-placeholder {{
    height: 120px; display: flex; align-items: center; justify-content: center;
    border: 1px dashed var(--line); border-radius: 12px; color: var(--muted); font-size: 13px; padding: 0 24px; text-align: center;
  }}

  .board-wrap {{
    overflow-x: auto; margin-top: 8px; border-radius: 14px; border: 6px solid #8a6238;
    box-shadow: inset 0 0 30px rgba(0,0,0,.25);
  }}
  #board {{
    position: relative; padding: 24px;
    background: var(--cork);
    background-image: radial-gradient(rgba(0,0,0,.08) 1px, transparent 1.5px);
    background-size: 14px 14px;
  }}
  .note {{
    position: absolute; background: #fffdf5; border-radius: 3px;
    padding: 12px 14px 14px; box-shadow: 2px 4px 10px rgba(0,0,0,.25);
    transform: rotate(var(--rot, 0deg)); cursor: grab; user-select: none;
    transition: box-shadow .15s;
  }}
  /* Applied only during a filter-triggered reflow, never while dragging —
     dragging sets left/top on every mousemove and would feel laggy if animated. */
  .note.reflow-anim {{ transition: left .25s ease, top .25s ease, box-shadow .15s; }}
  .note:active {{ cursor: grabbing; box-shadow: 4px 10px 18px rgba(0,0,0,.35); z-index: 50; }}
  .note::before {{
    content: ""; position: absolute; top: -7px; left: 50%; transform: translateX(-50%);
    width: 12px; height: 12px; border-radius: 50%; background: var(--pin, #999);
    box-shadow: 0 2px 3px rgba(0,0,0,.4);
  }}
  .note-label {{ font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 4px; }}
  .note-title {{ font-weight: 600; font-size: 14px; margin-bottom: 2px; }}
  .note-body {{ font-size: 12.5px; color: #46402f; }}
  .note-rejected .note-title {{ text-decoration: line-through; color: #8a5a56; }}
  .note .reason {{ font-style: italic; color: #7a4a46; margin-top: 4px; }}

  h2 {{ display: flex; align-items: center; gap: 12px; }}
  .show-all-btn {{
    text-transform: none; letter-spacing: normal; font-size: 12px; cursor: pointer;
    color: var(--muted); text-decoration: underline; display: none;
  }}
  .show-all-btn.visible {{ display: inline; }}
  .legend-hint {{ font-size: 11px; color: var(--muted); margin-bottom: 6px; }}
  .legend {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 0 0 4px; font-size: 12px; color: var(--muted); }}
  .legend span {{
    display: inline-flex; align-items: center; gap: 5px; cursor: pointer; user-select: none;
    padding: 3px 9px 3px 7px; border-radius: 999px; border: 1px solid transparent;
    transition: opacity .15s, background .15s;
  }}
  .legend span:hover {{ background: #fff; border-color: var(--line); }}
  .legend span.off {{ opacity: .4; text-decoration: line-through; }}
  .legend i {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0; }}

  .log {{ background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 12px 16px; }}
  .log summary {{ cursor: pointer; font-size: 13px; color: var(--muted); }}
  .log-body {{ margin-top: 10px; max-height: 260px; overflow-y: auto; }}
  .log-row {{ display: flex; gap: 10px; font-size: 13px; padding: 4px 0; border-bottom: 1px solid #f1ebdd; }}
  .log-turn {{ color: var(--muted); flex-shrink: 0; width: 70px; }}
  .log-archive-note {{ font-size: 12px; color: var(--muted); font-style: italic; padding: 8px 0 2px; }}

  .hint {{ margin-top: 14px; font-size: 12px; color: var(--muted); text-align: center; }}
</style>
</head>
<body>
<header>
  <span class="version">v{version}</span>
  <h1>{title}</h1>
  <div class="phase-banner">{phase_html}</div>
  {arch_html}
</header>
<main>
  {map_html}
  <h2>Corkboard <span class="show-all-btn" id="show-all">show all</span></h2>
  <div class="legend-hint">Click a category to hide/show those notes.</div>
  <div class="legend" id="legend">
    <span data-filter="profile"><i style="background:#4a6fa5"></i>Profile</span>
    <span data-filter="wishlist-confirmed"><i style="background:#2f9e6b"></i>Wishlist — confirmed</span>
    <span data-filter="wishlist-pending,wishlist-seasonal_conflict"><i style="background:#c4733a"></i>Wishlist — pending / seasonal flag</span>
    <span data-filter="wishlist-cut"><i style="background:#8a8578"></i>Wishlist — cut</span>
    <span data-filter="agent"><i style="background:#8b6fc4"></i>Agent note</span>
    <span data-filter="rejected"><i style="background:#c1453d"></i>Parked / rejected</span>
    <span data-filter="pending"><i style="background:#b8952e"></i>Pending decision</span>
  </div>
  <div class="board-wrap">
    <div id="board" style="width:{packer.board_width}px;height:{packer.board_height}px;">
      {notes_html}
    </div>
  </div>
  <div class="hint">Drag any note to rearrange (toggling a filter re-packs the board and resets manual dragging). This board is a snapshot of dashboard_state.json — ask your assistant to update it any time and re-render.</div>
  {log_html}
</main>
<script>
  let z = 50;
  document.querySelectorAll('.note').forEach(note => {{
    note.addEventListener('mousedown', (e) => {{
      const board = note.parentElement;
      const boardRect = board.getBoundingClientRect();
      const startLeft = parseFloat(note.style.left);
      const startTop = parseFloat(note.style.top);
      const startX = e.clientX, startY = e.clientY;
      note.style.zIndex = ++z;
      function onMove(ev) {{
        note.style.left = (startLeft + ev.clientX - startX) + 'px';
        note.style.top = (startTop + ev.clientY - startY) + 'px';
      }}
      function onUp() {{
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      }}
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }});
  }});

  // Corkboard filter: click a legend chip to hide/show its category of notes.
  // Hidden notes are removed from layout, and the rest re-pack upward into a
  // fresh masonry so filtering actually declutters instead of leaving gaps
  // where the hidden notes used to sit. This overrides any manual dragging —
  // reflow always recomputes from scratch on every filter change.
  const legend = document.getElementById('legend');
  const showAllBtn = document.getElementById('show-all');
  const board = document.getElementById('board');
  const NUM_COLS = {packer.cols};
  const COL_WIDTH = {packer.col_width};
  const GAP = {packer.gap};

  function reflow() {{
    const visible = [...board.querySelectorAll('.note')].filter(n => n.style.display !== 'none');
    const colHeights = new Array(NUM_COLS).fill(GAP);
    visible.forEach(note => note.classList.add('reflow-anim'));
    visible.forEach(note => {{
      let idx = 0;
      for (let i = 1; i < NUM_COLS; i++) {{
        if (colHeights[i] < colHeights[idx]) idx = i;
      }}
      note.style.left = (idx * (COL_WIDTH + GAP)) + 'px';
      note.style.top = colHeights[idx] + 'px';
      colHeights[idx] += note.offsetHeight + GAP;
    }});
    board.style.height = (Math.max(...colHeights) + 40) + 'px';
    setTimeout(() => visible.forEach(note => note.classList.remove('reflow-anim')), 300);
  }}

  function applyFilters() {{
    const offKeys = new Set();
    legend.querySelectorAll('span.off').forEach(chip => {{
      chip.dataset.filter.split(',').forEach(k => offKeys.add(k));
    }});
    document.querySelectorAll('.note').forEach(note => {{
      note.style.display = offKeys.has(note.dataset.filter) ? 'none' : '';
    }});
    showAllBtn.classList.toggle('visible', offKeys.size > 0);
    reflow();
  }}
  legend.querySelectorAll('span[data-filter]').forEach(chip => {{
    chip.addEventListener('click', () => {{
      chip.classList.toggle('off');
      applyFilters();
    }});
  }});
  showAllBtn.addEventListener('click', () => {{
    legend.querySelectorAll('span.off').forEach(chip => chip.classList.remove('off'));
    applyFilters();
  }});
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        print("usage: render_dashboard.py <dashboard_state.json>", file=sys.stderr)
        sys.exit(2)
    state_path = Path(sys.argv[1])
    state = json.loads(state_path.read_text())
    out = state_path.with_name("dashboard.html")
    out.write_text(render_html(state))
    print(str(out))
    if sys.platform == "darwin":
        subprocess.run(["open", str(out)], check=False)
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", str(out)], check=False)


if __name__ == "__main__":
    main()
