---
name: visual-plan
description: Renders plan-mode output as an interactive HTML page with clickable simulation, alternative paths, and per-step approve/reject controls. Use when finishing plan mode, when user says "visualize plan", "show plan visually", "render plan", "html plan", or before ExitPlanMode if user wants to review visually instead of in chat.
---

# Visual Plan

Render a structured plan as a self-contained HTML page the user reviews in browser. User picks approve/reject/modify per step, copies decision summary back to chat, agent implements approved subset.

## When to invoke

**Default plan-mode exit.** Render the plan visually *before* every `ExitPlanMode` call — full text plans are overwhelming and hard to read. A PreToolUse gate also enforces this, but the gate may silently fail-open (e.g. interpreter resolution, undocumented ExitPlanMode interaction), so do not rely on it: treat visual render as the standard step whether or not the gate fires.

Also invoke when:
- User says "visualize", "show me visually", "render plan as html", "browser plan".
- Plan has alternative paths worth comparing side-by-side.
- Plan affects UI/UX — simulation helps user judge feel before approving.

Skip only when the user explicitly opts out this turn ("skip visual", "no html", "just text"). On opt-out, write the sentinel manually so the gate clears: `touch "/tmp/visual-plan-ready-$CLAUDE_CODE_SESSION_ID"`, then call ExitPlanMode.

## Contract

- The PreToolUse hook denies `ExitPlanMode` until a per-session sentinel exists at `/tmp/visual-plan-ready-$CLAUDE_CODE_SESSION_ID`.
- `render_plan.py` drops that sentinel — so **running the renderer is what unblocks the gate.**
- **The sentinel proves a render happened, not that the user decided.** Do not let the cleared gate trick you into exiting early: after rendering, *end your turn*. Re-call `ExitPlanMode` only in a later turn, after the user has pasted a decision (or has explicitly said to proceed without one).

## Workflow

1. **Build plan JSON** — structure plan into the schema below. Keep `detail` short (1-2 sentences per step). Skip implementation line-noise.
2. **Write JSON to** `/tmp/plan.json` — fixed path; the hook's deny message references it.
3. **Run renderer** — `python3 "$CLAUDE_PLUGIN_ROOT/skills/visual-plan/scripts/render_plan.py" /tmp/plan.json`. Prints the HTML path, opens the browser (macOS `open` / Linux `xdg-open` — desktop only), and drops the sentinel. If it errors or no browser opens, print the path and ask the user to open it manually.
4. **Tell user to review, then stop** — short message: "Plan opened in browser. Click Approve/Reject per step, then paste the decision back here." End the turn — do not call `ExitPlanMode` yet.
5. **Next turn, on the pasted decision** — parse the block, implement approved steps, skip rejected, ask one follow-up on ambiguous `modify` notes, then re-call `ExitPlanMode`.

## Plan JSON schema

```json
{
  "title": "Short plan title",
  "summary": "1-2 sentence why",
  "steps": [
    {
      "id": "1",
      "title": "Step title",
      "detail": "Short what + why. No line numbers.",
      "files": ["src/foo.ts", "src/bar.ts"],
      "optional": false,
      "depends_on": [],
      "before": "current state / code (optional)",
      "after": "proposed state / code (optional)"
    }
  ],
  "alternatives": [
    {
      "name": "Alt approach name",
      "tradeoffs": "Why considered. Why not chosen (or when to prefer).",
      "steps": ["Brief step 1", "Brief step 2"]
    }
  ],
  "simulation": {
    "screens": [
      {
        "id": "s1",
        "title": "Screen / state name",
        "body_html": "<div class='mock'>Whatever HTML mocks the UI state. Inline styles fine.</div>",
        "actions": [
          {"label": "Click Submit", "next": "s2"}
        ]
      }
    ],
    "start": "s1"
  }
}
```

Notes:
- `depends_on` — list of step `id`s this step needs done first. Drives the **Plan flow** graph (steps render as a dependency diagram, not just a list). Omit on every step → the graph falls back to a linear 1→2→3 chain. Use it whenever steps fan out or converge (e.g. two steps both depend on a shared setup step) — that shape is exactly what the graph makes legible. Unknown ids are ignored; don't create cycles.
- `before` / `after` — short current-vs-proposed snippets shown side-by-side under the step. Best for the 2-3 steps where the *change* is the point (a handler gaining a guard, a config flipping). Plain text/code, rendered monospace + escaped. Skip on steps where a diff adds nothing. Either field alone is fine.
- `alternatives` optional — omit if only one approach.
- `simulation` optional — omit for pure-backend plans. If included, must have at least 2 screens.
- `body_html` is freeform and injected **unsanitized** — author it yourself; never embed untrusted/user-supplied content. Use simple boxes/buttons/text; UI needn't match the real product, just convey flow.
- Mark genuinely optional steps with `"optional": true` so user knows they can skip without breaking the plan.

### Picking the right visual aids

Don't fill every field on every step — noise hides signal. Match the aid to the plan:

| Plan shape | Reach for |
|------------|-----------|
| Steps fan out / converge / have a shared prerequisite | `depends_on` (flow graph earns its place) |
| A step's value is a focused code/behavior change | `before` / `after` on *that* step |
| Plan changes UI/UX | `simulation` |
| More than one viable approach | `alternatives` |
| Short, strictly-linear backend plan | none — the plain step list is enough |

## Decision format (what user pastes back)

```
APPROVED: 1, 2, 4
REJECTED: 3
MODIFY 5: <user's note about what to change>
ALT: <name of alternative if user picked one>
```

Each step id appears under exactly one verb — a step is approved, rejected, *or* modified, never two at once. Free-form text after — treat as additional feedback. If user pastes only "approve all" / "looks good", implement everything.

## After decision

- Implement only `APPROVED` steps in order.
- For `MODIFY`, ask one clarifying question if note is ambiguous, otherwise apply.
- If `ALT` picked, re-plan with that alternative — may need a second visual-plan iteration.
- Don't touch `REJECTED` steps even tangentially.

## See also

- [EXAMPLES.md](EXAMPLES.md) — worked plan JSON, including a dependency-graph plan and an ASCII sketch of how it renders.
