---
name: visual-plan
description: Renders plan-mode output as an interactive HTML page with clickable simulation, alternative paths, and per-step approve/reject controls. Use when finishing plan mode, when user says "visualize plan", "show plan visually", "render plan", "html plan", or before ExitPlanMode if user wants to review visually instead of in chat.
---

# Visual Plan

Render a structured plan as a self-contained HTML page the user reviews in browser. User picks approve/reject/modify per step, copies decision summary back to chat, agent implements approved subset.

## When to invoke

- User finishes plan mode and wants visual review (instead of plain text ExitPlanMode).
- User says "visualize", "show me visually", "render plan as html", "browser plan".
- Plan has alternative paths worth comparing side-by-side.
- Plan affects UI/UX — simulation helps user judge feel before approving.

If user just wants a quick text plan, skip this skill. Use only when visual review adds value.

## Workflow

1. **Build plan JSON** — structure plan into the schema below. Keep `detail` short (1-2 sentences per step). Skip implementation line-noise.
2. **Write JSON to temp file** — `/tmp/claude-plan-{timestamp}.json`.
3. **Run renderer** — `python3 "$CLAUDE_PLUGIN_ROOT/skills/visual-plan/scripts/render_plan.py" <json-path>`. Outputs HTML path + auto-opens via `open`.
4. **Tell user to review** — short message: "Plan opened in browser. Click Approve/Reject per step, then paste decision back here."
5. **Wait for pasted decision** — user pastes JSON-like decision block. Parse, implement approved steps, skip rejected, ask follow-up on `modify` notes.

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
      "optional": false
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
- `alternatives` optional — omit if only one approach.
- `simulation` optional — omit for pure-backend plans. If included, must have at least 2 screens.
- `body_html` is freeform — use simple boxes/buttons/text. UI doesn't need to match real product, just convey flow.
- Mark genuinely optional steps with `"optional": true` so user knows they can skip without breaking the plan.

## Decision format (what user pastes back)

```
APPROVED: 1, 2, 4
REJECTED: 3
MODIFY 5: <user's note about what to change>
ALT: <name of alternative if user picked one>
```

Free-form text after — treat as additional feedback. If user pastes only "approve all" / "looks good", implement everything.

## After decision

- Implement only `APPROVED` steps in order.
- For `MODIFY`, ask one clarifying question if note is ambiguous, otherwise apply.
- If `ALT` picked, re-plan with that alternative — may need a second visual-plan iteration.
- Don't touch `REJECTED` steps even tangentially.

## See also

- [EXAMPLES.md](EXAMPLES.md) — example plan JSON + screenshot of rendered output.
