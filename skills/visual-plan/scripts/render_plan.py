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
    return f"""
    <div class="step" data-step-id="{sid}">
      <div class="step-head">
        <div class="step-num">{sid}</div>
        <div class="step-titles">
          <div class="step-title">{title} {opt_badge}</div>
          <div class="step-detail">{detail}</div>
          {files_html}
        </div>
        <div class="step-actions">
          <label class="btn approve"><input type="radio" name="dec-{sid}" value="approve" checked>Approve</label>
          <label class="btn reject"><input type="radio" name="dec-{sid}" value="reject">Reject</label>
          <label class="btn modify"><input type="radio" name="dec-{sid}" value="modify">Modify</label>
        </div>
      </div>
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


def render_html(plan):
    title = esc(plan.get("title", "Plan"))
    summary = esc(plan.get("summary", ""))
    steps = plan.get("steps", []) or []
    alts = plan.get("alternatives", []) or []
    sim = plan.get("simulation")

    steps_html = "".join(render_step(s, i) for i, s in enumerate(steps))
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
  <section class="block">
    <h2>Plan steps</h2>
    {steps_html}
  </section>
  {alts_html}
  {sim_html}
</main>

<div class="copybar">
  <div class="copybar-summary" id="summary">…</div>
  <button class="copybtn" id="copybtn">Copy decision</button>
</div>

<script>
  // Step highlight + modify textarea reveal
  document.querySelectorAll('.step').forEach(step => {{
    const radios = step.querySelectorAll('input[type=radio]');
    radios.forEach(r => r.addEventListener('change', () => {{
      step.classList.remove('is-approve', 'is-reject', 'is-modify');
      step.classList.add('is-' + r.value);
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
