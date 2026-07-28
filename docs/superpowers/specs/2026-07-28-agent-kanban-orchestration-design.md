# agent-kanban: full task briefs and plan orchestration

**Date:** 2026-07-28
**Skill:** `skills/agent-kanban`
**Status:** approved, ready for implementation planning

## Problem

Two related gaps in the current skill.

**1. Briefs do not fit on the card.** The card contract puts everything an agent needs to
pick the task up cold into `details`, a monday `long_text` column. That column is capped at
2000 characters by monday's API — it is not a choice the skill makes and it cannot be raised.
A real task brief carrying the relevant slice of a design doc, the files in scope, the
interfaces, and the acceptance criteria routinely exceeds that. Today the brief gets
truncated, and the card stops being pickupable cold, which is the property `details` exists
to provide.

**2. There is no way to run a whole plan.** The skill can decompose a design doc into cards
(operation 6) and it can hand a card id to a subagent ("Dispatching subagents against the
board"), but nothing connects the two. Running a plan means the user manually dispatches each
card, reviews each PR, and reports each result back onto the board by hand.

## The organising idea: transport is not display

The card is currently doing two jobs at once — it is how work is *described to an agent* and
how work is *shown to the user*. That conflation is why the 2000-character cap hurts.

Split them:

- **Display** stays on the card, sized for a human scanning the board.
- **Transport** is whatever gets the full context into the agent's hands. In-prompt when an
  orchestrator is running; an append-only update on the card when it is not.

The cap then constrains only the summary, which is naturally short anyway.

## Part A — Brief transport

### Card contract change

| Field | Cap | Content |
|---|---|---|
| `details` (long_text) | 2000, hard | Fixed shape: Goal / Constraints / Done when / Depends on. Always fits. |
| **Task Brief** (first update) | none observed | Full context: the relevant slice of the source document, files and directories in scope, interfaces, acceptance criteria, explicit out-of-scope. |

`details` becomes a summary with a known shape rather than a free-form dumping ground. The
brief moves to the card's first update.

### Why an update rather than a file column or a repo link

Three carriers were considered:

- **Update** — append-only, never clobbered, already in the read path (operation 5 fetches
  updates before picking a card up), no board or config migration. Chosen.
- **File column** (`upload_file_to_item`) — genuinely unbounded, but needs a new column on the
  board plus a config key, and agents must fetch and base64-decode to read it.
- **Repo link** — version-controlled and diffable, but the card stops being self-contained and
  breaks for anyone without the repo checked out.

The update also matches an invariant the skill already states: long-text fields replace on
write, so anything that must not be destroyed belongs in the log rather than in a field.

### Mechanics

- The brief update body begins with the marker `<b>Task Brief</b>`. That marker is how an
  agent distinguishes the brief from progress-log updates when reading the update history.
- Monday update bodies accept HTML, not markdown. Use `<b>` for headings, `<br>` for line
  breaks, `<pre>` for code. Emitting raw markdown renders literal `##` and `-` characters.
- No update-body size limit has been observed in practice. Treat splitting as a **fallback**,
  not a routine step: if an update is ever rejected as too large, post a continuation update
  rather than truncating the brief.

### Operation changes

| Operation | Change |
|---|---|
| 1. Add a task | After creating the card, post the Task Brief update. Card creation is not complete until the brief is on it. |
| 5. Pick up a specific task | Read the Task Brief update **first**, then the progress log. The brief is the spec; the log is what happened since. |
| 6. Break a plan into tasks | Every card gets its own brief, carrying only the slice of the source document relevant to that card. |

## Part B — Plan orchestration

Ships as `skills/agent-kanban/references/orchestration.md`, with a short pointer section in
`SKILL.md`. Keeping it inside `agent-kanban` means one skill remains the single source of
truth for the board contract and the config format.

### Constraints that shape the design

- **The Workflow tool requires explicit user opt-in on every run.** A skill cannot fire one on
  its own. Orchestration is therefore a path the skill *offers*, never the default.
- **The orchestrator cannot ask the user anything mid-run.** Everything it needs must be
  settled before the script starts.
- Workflow nesting is one level deep. `Date.now()` and `Math.random()` are unavailable in
  scripts.
- Workflow subagents reach the monday MCP tools through `ToolSearch`, so each agent can update
  its own card directly.

### Preconditions, settled before launch

Project name · design doc path · repo · base branch · board config read and validated.

### Shape

```
phase Plan
  agent: read the doc -> decompose -> cards[], each with agent_key, title,
                                      details (<=2000), and a full brief
  agent: dedupe every key in ONE query -> create the missing cards in ONE
         aliased mutation -> post the Task Brief update on each
         [barrier is correct here: dedupe needs all keys at once]

pipeline(cards)                                  [no barrier between stages]
  Build   agent, isolation: 'worktree'
          claim the card (In Progress + own name) -> work -> run tests
          -> push branch -> open PR -> set link, post an update
  Review  agent, reads the PR diff
          no blocking findings -> card Done + an update stating what was verified
          blocking findings    -> comment them on the card, one fix pass
  Fix     agent, isolation: 'worktree', git fetch && git checkout <branch>
          apply fixes -> push -> re-review
          pass -> Done | fail -> Blocked + the findings as a comment

reconcile
  any card still In Progress whose pipeline result is null (the agent died)
    -> Blocked, with an update saying no result was produced
```

### Three load-bearing details

**State travels via the branch, not the worktree.** `isolation: 'worktree'` gives every agent
a *fresh* worktree, so the Fix agent cannot inherit the Builder's working tree. It fetches and
checks out the pushed branch instead. Getting this wrong silently discards the build and the
fix agent starts from a clean base.

**The reconcile pass is mandatory.** `agent()` returns `null` when a subagent dies on a
terminal error. Without reconcile, those cards sit In Progress indefinitely — the board
reports work in flight that nothing is working on, which is precisely the failure the whole
skill is built to prevent.

**Each agent writes its own card.** The orchestrator does not proxy board writes. This is what
makes status live: the card flips to In Progress when the builder actually starts, not when
the orchestrator queued it.

### Fix policy

One fix round, then stop. Still failing after re-review means Blocked with the findings on the
card. Bounded cost, no unbounded loop.

### Merge policy

Never merge. The orchestrator stops at an open PR with the link on the card. `Done` here means
"PR open, review passed, ready for your review" and the card's final update says so. An
agent-approved agent-written change does not reach the default branch without a human.

## Files to change

```
skills/agent-kanban/
  SKILL.md                      card contract: +brief row, details cap note
                                op 1  +post the Task Brief
                                op 5  +read the Task Brief first
                                op 6  +a brief per card
                                "Dispatching subagents" +pointer, +opt-in rule
  references/monday.md          +the 2000 cap, +update HTML formatting,
                                +the split fallback
  references/orchestration.md   NEW
  evals/evals.json              +an eval for brief-goes-to-update behaviour
.claude-plugin/plugin.json      version bump
```

The frontmatter `description` is left unchanged. Adding orchestration trigger phrases risks
disturbing the skill's current recall, and the orchestrator is reached from inside the skill
rather than triggered directly.

## Out of scope

- Jira orchestration. `references/jira.md` is untouched; the orchestration reference targets
  the monday path only.
- Auto-merge, CI gating, and deploy steps.
- Retrying a dead builder. Reconcile marks it Blocked and stops.
- Migrating existing cards. Cards created before this change keep their truncated `details`
  and simply have no Task Brief update.
