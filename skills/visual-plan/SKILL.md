---
name: visual-plan
description: Renders a plan as an interactive HTML page whose centerpiece is a state-evolution model — the system's entities shown going from current state to future state, one step at a time — plus a dependency-flow graph and per-step approve/reject controls. Use when finishing plan mode, when user says "visualize plan", "show plan visually", "render plan", "html plan", or before ExitPlanMode if user wants to review visually instead of in chat.
---

# Visual Plan

Render a plan as a self-contained HTML page the user reviews in a browser, then picks approve/reject/modify per step and pastes the decision back.

**The page must earn its tokens by *showing* what a chat message can't — not by relocating the same text into boxes.** A bulleted plan in HTML is a waste; the point is comprehension you can't get by reading. So the centerpiece is a **state-evolution model**: lay out the *entities* the plan touches (services, datastores, screens, actors, concepts) and let the user step through `Now → step 1 → step 2 → … → Done`, watching each entity appear, change, or disappear. The reviewer *sees* what the change does to the system before approving it.

Keep it conceptual — general lines, not code. "Login endpoint: verifies password → checks rate-limit first," not a diff. The goal is to understand the change and what each step does, not to read the implementation.

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

## Grounding — do this before building the JSON

A plan is only useful if it's anchored in the *real* codebase, not an abstract proposal. Before writing the JSON:

- **Read the real files, schemas, and patterns first.** Name actual files, symbols, and data shapes — don't invent them. Entity labels and file paths must be things that exist (or will) in this repo.
- **Lead with reuse.** For each step, name what it *reuses* (existing modules, helpers, endpoints, tables) before what it genuinely adds. Reuse is signal; it tells the reviewer the change fits the grain of the codebase.
- **Decide the hard-to-reverse bets first.** Wire formats, public IDs, data-model shapes, auth/ownership boundaries — these are expensive to undo once callers or data depend on them. Mark those steps `"stakes": "high"` and, when a bet is genuinely open, raise it in `open_questions`.

For wide exploration, delegate to a sub-agent rather than reading everything inline.

## Workflow

1. **Build plan JSON** — structure plan into the schema below. First identify the 3–7 **entities** the plan touches and their `current` state, then write each step's `changes` as conceptual transitions on those entities (this drives the state model — the part that makes the page worth rendering). Keep `detail` and entity `state` phrases short; skip implementation line-noise and code.
2. **Write JSON to** `/tmp/plan.json` — fixed path; the hook's deny message references it.
3. **Run renderer** — `python3 "$CLAUDE_PLUGIN_ROOT/skills/visual-plan/scripts/render_plan.py" /tmp/plan.json`. Prints the HTML path, opens the browser (macOS `open` / Linux `xdg-open` — desktop only), and drops the sentinel. If it errors or no browser opens, print the path and ask the user to open it manually.
4. **Tell user to review, then stop** — short message: "Plan opened in browser. Click Approve/Reject per step, then paste the decision back here." End the turn — do not call `ExitPlanMode` yet.
5. **Next turn, on the pasted decision** — parse the block, implement approved steps, skip rejected, ask one follow-up on ambiguous `modify` notes, then re-call `ExitPlanMode`.

## Plan JSON schema

```json
{
  "title": "Short plan title",
  "summary": "1-2 sentence why — also the caption shown at the 'Now' frame",
  "outcome": "1 sentence describing the end state — caption at the 'Done' frame",
  "entities": [
    {"id": "login", "label": "Login endpoint", "kind": "endpoint"},
    {"id": "counter", "label": "Attempt counter", "kind": "datastore"}
  ],
  "current": {
    "login": {"present": true, "state": "verifies password, no limit"},
    "counter": {"present": false}
  },
  "future": {
    "login": {"state": "throttled, then verifies"}
  },
  "steps": [
    {
      "id": "1",
      "title": "Step title",
      "detail": "Short what + why. No line numbers.",
      "files": ["src/foo.ts", {"path": "src/bar.ts", "op": "new"}],
      "optional": false,
      "stakes": "high",
      "stakes_reason": "public wire format — callers depend on it",
      "depends_on": [],
      "changes": [
        {"entity": "counter", "op": "add", "state": "per-IP count, 15-min window"}
      ],
      "before": "current state / code (optional, rarely needed)",
      "after": "proposed state / code (optional, rarely needed)"
    }
  ],
  "open_questions": [
    {"id": "q1", "question": "Decision that needs the reviewer's judgment?", "note": "optional context / the trade-off"}
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

Notes — the state model (the centerpiece):
- `entities` — the things the plan touches that are worth watching change: services, datastores, endpoints, screens, actors, concepts. Each has an `id`, a human `label`, and a `kind` (drives the icon: `service`, `datastore`, `endpoint`, `ui`, `actor`, `external`, `queue`, `job`, `api`, `config`, `concept`, …). Aim for 3–7 — the few entities whose change *is* the story, not every file.
- `current` — map of `entityId → {present, state}`. `present` (default `true`) is whether the entity exists today; `state` is a short conceptual phrase of how it is now. Omit an entity here to mean "exists, nothing notable about its current state."
- step `changes` — list of `{entity, op, state}`. `op` is `add` | `modify` | `remove` (drives the green/amber/red highlight + NEW/CHANGED/REMOVED badge at that frame); `state` is the new conceptual phrase after this step. This is what makes the timeline move — each step's `changes` are the transitions the reviewer watches. Keep `state` general ("checks rate-limit before verifying"), never code.
- `future` — optional `entityId → {state, present}` overrides applied at the final "Done" frame, for end-state phrasing that's cleaner than the last step's wording. `outcome` is the one-line caption at that frame.
- Unknown entity ids in `changes`/`current`/`future` are ignored. If a plan has no `entities`, the stage is omitted — so always provide them unless the plan genuinely has no system to show (e.g. a pure doc edit).

Notes — grounding & decisions:
- `files` — real repo paths the step touches. A path can be a bare string, or `{"path", "op"}` where `op` is `new` | `edit` | `delete`. All steps' files aggregate into a **Files touched** tree (the blast radius on the real layout), with per-file op markers and the steps that touch each. Use real paths — this is grounding, not decoration.
- `stakes` — set `"high"` on a step whose choice is expensive to undo (wire format, public IDs, data-model shape, auth boundary). Adds a ⚠ "hard to undo" badge + red accent so the reviewer's attention lands there. Add `stakes_reason` for the one-line why. Use sparingly — if everything's high-stakes, nothing is.
- `open_questions` — plan-level list of decisions needing the reviewer's judgment (`id`, `question`, optional `note` with the trade-off). Renders as a single block at the bottom; the reviewer types an answer per question and it rides back in the pasted decision as `Q1: …`. Raise the genuinely-open hard-to-reverse bets here rather than silently picking.

Notes — secondary aids:
- `depends_on` — step `id`s this step needs first. Drives the **Plan flow** graph. Omit everywhere → linear 1→2→3 chain. Use when steps fan out or converge. Unknown ids ignored; no cycles.
- `before` / `after` — rarely needed now. Only when a *literal* code snippet is the clearest way to show one step's change; otherwise model it with entity `changes` instead. Plain text, escaped, monospace.
- `alternatives` — omit if only one approach.
- `simulation` — a separate clickable UI mock (≥2 screens). Use for UI/UX flows; distinct from the entity stage.
- `body_html` is injected **unsanitized** — author it yourself; never embed untrusted/user-supplied content.
- Mark genuinely optional steps with `"optional": true`.

### Picking the right visual aids

Don't fill every field — noise hides signal. The state model is the default; the rest are situational:

| Plan shape | Reach for |
|------------|-----------|
| **Almost any plan that changes a system** | `entities` + `current` + per-step `changes` (the state model — this is the point) |
| Steps fan out / converge / have a shared prerequisite | `depends_on` (flow graph) |
| Plan changes UI/UX and you want to feel the screens | `simulation` |
| More than one viable approach | `alternatives` |
| Any step touches real files | `files` (feeds the Files-touched tree) |
| A step's choice is expensive to undo | `stakes: "high"` on that step |
| A decision genuinely needs the reviewer's call | `open_questions` |
| A single step is clearest as a literal code snippet | `before` / `after` on that step (rare) |
| Pure doc/config edit with no system to model | minimal — just steps |

## Decision format (what user pastes back)

```
APPROVED: 1, 2, 4
REJECTED: 3
MODIFY 5: <user's note about what to change>
ALT: <name of alternative if user picked one>
Q1: <answer to open question q1>
Q2: <answer to open question q2>
```

Each step id appears under exactly one verb — a step is approved, rejected, *or* modified, never two at once. `Q<id>:` lines are the reviewer's answers to `open_questions` (only the ones they answered appear). Free-form text after — treat as additional feedback. If user pastes only "approve all" / "looks good", implement everything.

## After decision

- Implement only `APPROVED` steps in order.
- For `MODIFY`, ask one clarifying question if note is ambiguous, otherwise apply.
- If `ALT` picked, re-plan with that alternative — may need a second visual-plan iteration.
- For each `Q<id>:` answer, apply the reviewer's decision to the relevant steps. If a hard-to-reverse question was left unanswered, ask it before building that part.
- Don't touch `REJECTED` steps even tangentially.

## See also

- [EXAMPLES.md](EXAMPLES.md) — worked plan JSON: the flagship state-evolution plan (with an ASCII sketch of the timeline frames), a dependency-graph plan, and simpler shapes.
