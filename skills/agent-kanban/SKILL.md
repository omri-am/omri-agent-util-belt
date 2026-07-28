---
name: agent-kanban
description: One central Kanban board where agents create, claim, update, and complete tasks, so all agent work across every project is visible in one place. Use this skill whenever the user wants work tracked on the board, is about to start a task, or wants to see what agents are doing. Trigger it when they say "add this to the board", "what's on the board", "what's in progress", "mark that done", "go pick up that card"; when they hand over a design doc, spec, or plan and want the tasks written up ("turn this into tasks", "write up the tasks for this", "I'm starting a new project"); before an agent begins any task the user will want to see tracked; when new work is discovered while working an existing task; and when dispatching subagents whose progress should be visible. Always establish which project the work belongs to first — ask if the user has not said, since a project is not the same thing as a repo. Runs on monday.com by default, with Jira supported for team-tracked work. Prefer this over ad-hoc notes, TodoWrite, or spreadsheets any time the work should outlive the current session or be visible to the user outside this conversation.
---

# Agent Kanban

One board is the shared memory for agent work. The value is not the card — it is that the
user can open one page and see everything every agent is doing, across every project,
without having to ask. Every rule below protects that single property: the board must stay
readable, and it must not lie.

## Read this first if you are a subagent

If your brief contains a card id, you have exactly two jobs on the board, and creating a
card is not one of them:

1. When you start: set the card to In Progress and put your own name in the Agent field.
2. When you stop — done, blocked, or failed: post an update saying what happened, and set
   the final status.

Do not create a new card. Your parent already made one. A second card means the user sees
the same work twice and stops trusting the board. If your brief has no card id, just do the
work and report back in text — the parent owns the board.

Then go to [Operations](#operations).

## Config — read it first, every time

Board coordinates live in `~/.claude/agent-kanban.json`: platform, board id, column ids, status
labels. **Read it before any operation.** Column ids are per-board random strings; they cannot be
guessed, inferred from column titles, or copied from an example — including the examples in the
reference files, which show one particular board's ids.

Config is a file rather than a remembered fact on purpose. A board id has to be read reliably on
every run, and a half-remembered id pointing at a column that no longer exists is worse than
having nothing, because writes to a dead column can fail quietly.

### If the config is missing — run setup, then continue

Do not guess a board and do not silently create one. Walk the user through it:

1. **Ask which board to use.** List their existing boards so they can pick one, and offer
   creating a new board dedicated to agent work as an option. Most people want a dedicated
   board, since agent cards mixed into a live team board get lost and annoy their teammates.
2. **Resolve the columns.**
   - *New board* → create it plus the columns the card contract needs. The reference file has a
     verified recipe; follow it rather than improvising, because several of the column shapes
     are non-obvious and fail confusingly.
   - *Existing board* → read its schema and map the contract onto what is already there,
     matching on title and type. Create only what is genuinely missing.
3. **Show the user the mapping before writing anything.** Name each contract field and the
   column you matched it to. This is where a wrong guess gets caught cheaply — mapping `details`
   onto a column their team already uses for something else would quietly overwrite real data on
   every card you touch.
4. **Write the config file**, then carry on with what the user originally asked for. Setup is a
   detour, not the task; do not stop and report success at having configured a board.

When mapping an existing board, never repurpose a column that clearly belongs to someone else's
workflow just because the type fits. Adding a new column is cheap and reversible; writing agent
data into a team's real field is neither.

### If the config exists but does not match the board

Validate cheaply before trusting it: read the board schema and confirm the column ids in config
are actually present. If any are missing — someone deleted or rebuilt a column — say so, re-map
those fields, and update the config. Do not fall back to writing a partial card, and do not
invent a replacement id.

If the board itself is gone, stop and ask. A card written somewhere the user does not look is
worse than no card, because the work is now invisible *and* believed tracked.

Platform mechanics live in reference files. Read the one matching `platform`:

- monday.com → `references/monday.md` — the default. Note the stringified-JSON trap
  documented there; two of the MCP tools cannot set column values at all.
- Jira → `references/jira.md` — for work that belongs to a team's tracked backlog.

## The card contract

Every card carries these fields. Names differ per platform — the reference file maps them —
but the meaning does not.

| Field | Purpose | Example |
|---|---|---|
| project | Which project this belongs to; the cross-project axis. **Ask, never infer.** | `My Service` |
| `agent_key` | Stable identity for dedupe. **The load-bearing field.** | `my-service/fix-retry-backoff` |
| title | What a human scanning the board needs to understand it | `Fix retry backoff in webhook sender` |
| status | Kanban stage | `In Progress` |
| agent | Which agent holds it now | `agent:builder-a` |
| details | Summary for a human scanning the card. **Hard-capped at 2000 chars.** | `Goal: … / Constraints: … / Done when: … / Depends on: …` |
| brief | The full spec, posted as the card's **first update**. No practical size limit. | the slice of the design doc this card implements |
| link | The primary artifact — PR, branch, doc | `https://github.com/.../pull/42` |
| updates | Append-only progress log | `Ran retry_test.py: 3 failing` |

### project: ask for it, never infer it

A project is a unit of work **the user defines**. It is not a repo. One project can span
several repos, and plenty of trackable work — a migration, a doc rewrite, an ops chore — has
no repo at all. So a repo name is evidence about a project, never a substitute for one.

**If the user has not said which project the work belongs to, ask before creating the card.**
This is the one place in this skill where stopping to ask beats making a reasonable guess,
and it is worth understanding why: the project field is what makes the board navigable. Guess
wrong and you do not get a small error, you get a card filed under a project the user does not
recognise, which they will not find when they go looking. Worse, guessing quietly teaches the
board a project name that was never real, and it shows up in the dropdown forever.

Asking is cheap — one short question — and the answer is reusable for every later card in that
conversation. Read the known project names from the config file's `projects` list (or from the
Project column's existing labels) and offer those, since the user picking an existing name is
the common case and keeps the list from fragmenting into near-duplicates like
`My Service` / `my-service` / `my svc`.

Two exceptions where you should not stop and ask:

- **The user already told you** earlier in the conversation, or it is unambiguous from what
  they said. Do not re-ask what you were just told.
- **You are a subagent.** You cannot reach the user. Your brief must carry the project; if it
  does not, say so in your report rather than inventing one.

### agent_key: derive it, never invent it

`agent_key` must be reproducible from the task itself, so an agent re-running the same work
computes the same key and finds the existing card instead of making a new one. Build it from
stable facts:

- Code work: `<repo>/<branch>` or `<repo>#<issue-number>`
- Other work: `<area>/<slugified-goal>`, e.g. `docs/onboarding-guide-rewrite`

Never use a timestamp, a random id, or the agent's own name. Those change every run, which
defeats the entire point — the key exists to be recomputed.

### Titles are for humans, keys are for machines

Write the title so the user understands the task at a glance without opening the card. Keep
identifiers, branch names, and slugs in `agent_key` and `details`. A board full of titles
like `fix-retry-backoff` forces the user to open every card to know what is happening, which
is exactly the cost the board was supposed to remove.

### details is a summary; the brief is an update

`details` is a monday `long_text` column and monday caps those at 2000 characters. That is
not a choice this skill makes and it cannot be raised. A real brief — the slice of a design
doc the card implements, the files in scope, the interfaces, the acceptance criteria — does
not fit, so putting it there means truncating it, and a truncated brief defeats the only
reason `details` exists.

So the two are split:

- **`details`** carries four labelled lines and nothing else: `Goal:`, `Constraints:`,
  `Done when:`, `Depends on:`. That shape always fits, and it is what the user reads when
  they open the card.
- **The brief** is posted as the card's **first update**, whose body begins with the marker
  `<b>Task Brief</b>`. Updates are append-only, are never clobbered by a later write, and
  are already fetched when an agent picks a card up — so the brief costs no extra round trip
  at the moment it is needed.

The marker matters. An agent reading a card's update history has to tell the spec apart from
the progress log, and it does that by looking for `<b>Task Brief</b>` on the oldest update.
Without the marker it has to guess, and it will read a progress note as the spec.

A file column would also hold an unbounded brief, and a link to a spec in the repo would too.
Neither was chosen: a file column needs a board migration and a base64 round trip to read,
and a repo link stops the card being self-contained the moment someone without the repo opens
it.

## The two flows this exists for

Most real use is one of these. Both start the same way, by establishing the project.

**Starting a project from a plan.** The user has a design doc or spec and wants the work on the
board.

```
ask which project → read the doc → decompose → batch dedupe → create all cards as To Do → report
```

That is operation 6. Nothing goes In Progress here; the point is to get the plan visible.

**Taking on a task.** The user is about to have an agent do something, and wants it tracked.

```
ask which project → create the card (To Do) → claim it (In Progress) → do the work
  → capture anything new you discover as its own card → finish honestly (Done or Blocked)
```

That is operations 1 → 5 → 7 → 3. The order matters: **create the card before starting work**,
not after. A card filed once the work is finished makes the board a changelog, and the user
asking "what are my agents doing right now" gets nothing. Claiming it first is what makes the
board answer that question.

If the task already has a card, skip creating and go straight to claiming it.

## Operations

Seven operations cover everything. The reference file gives exact queries; this is the
decision logic above them.

### 1. Add a task

Subagents write directly to this board, so two agents on the same problem will race. Always
check before creating:

1. Establish the project. Ask if the user has not said (see above).
2. Compute `agent_key`.
3. Search the board for an exact match on it.
4. **Found** → update that card instead. Tell the user "this already existed, updated it" —
   that is normal, not an error.
5. **Not found** → create the card in To Do with the full contract above, setting both the
   Project column and the matching group.
6. **Post the Task Brief** as an update on the new card. A card is not finished until its
   brief is on it — a card with a four-line summary and no brief is *less* useful than the
   old truncated one, because it looks complete while carrying nothing to work from.
7. Report the card id and URL.

Skipping step 2 is the most common way this board degrades. Once duplicates appear the user
cannot tell which card is real, and the board stops answering "what's happening".

Match on `agent_key` exactly — never on the title. Titles get reworded, so a title search
gives both false negatives and false positives, and a near-miss silently creates the
duplicate the check was meant to prevent.

### 2. Update a task

Update by card id, never by title match — a title search can hit the wrong card or several.

Batch related changes into one call. Status, owner, and link are usually one update, not
three.

Long-text fields **replace** on write. To add information rather than overwrite it, post an
update instead. Overwriting `details` destroys the context a future agent needs to pick the
card up cold.

### 3. Complete a task

Completion is a claim about reality, so make it honest:

- Finished **and verified** → Done, plus an update stating what you verified and how (the
  command you ran, the test that passed).
- Stopped for any other reason → **Blocked**, not Done, plus an update naming the blocker.

A card marked Done that isn't done is the worst failure here. Done cards drop out of the
views the user scans, so the work does not just look finished — it disappears.

If you could not verify, say so on the card. "Implemented, tests not run" is useful and
honest; silently marking it Done is neither.

### 4. Post progress

Updates are the audit trail — cheap, append-only, they never clobber a field. Post one when
the fact is something the user would want without having to ask:

- A PR or branch came into existence → the URL
- Tests ran → the result, pass or fail
- The plan changed mid-flight → why
- Something failed → the actual error text, not a summary of it

Short and factual; this is a log, not a narrative. Skip anything that adds no new fact —
"starting work now" is already implied by the status change.

### 5. Pick up a specific task

When the user points at a card:

1. Fetch the card **and its updates**, then read them in two passes:
   - The oldest update marked `<b>Task Brief</b>` is the spec. Read it before anything else;
     `details` is only a summary of it.
   - The rest are the progress log, newest last. This is where an earlier attempt recorded
     why it stopped, which is usually the highest-value context available.

   If there is no Task Brief update, the card predates this convention — work from `details`
   and say in your first update that the card had no brief.
2. Set In Progress, put yourself in Agent.
3. Do the work.
4. Complete per operation 3.

If it is already In Progress under a different agent, say so and ask before taking it. Two
agents on one card produce conflicting updates and duplicated commits.

### 6. Break a plan into tasks

The starting-a-project case: the user has a design doc, a spec, or a plan, and wants the work on
the board. This is operation 1 done in bulk, so the same rules hold — ask for the project once,
dedupe, everything starts in To Do.

1. Ask which project, unless the user already said. One question covers the whole batch.
2. Read the source document properly before decomposing. Tasks invented from a title rather
   than the actual content are the main failure here.
3. Decompose into cards, then dedupe all their keys in **one** batched query rather than one
   query per card.
4. Create them in a single call. The reference file shows how to alias several creates into one
   mutation, which matters because a half-applied plan is worse than none — the user cannot tell
   which parts made it onto the board.
5. Post a Task Brief on each card, carrying **only the slice of the source document that card
   implements** — plus the files in scope, the interfaces it must honour, its acceptance
   criteria, and what is explicitly out of scope. Do not paste the whole document onto every
   card: an agent that has to work out which third of a spec applies to it is back to having
   no brief.
6. Report the list back as titles with ids, and say which project they landed in.

**Getting granularity right is the real work.** Aim for cards a single agent or person could
pick up independently and know when they are finished. Two failure modes to steer between:

- Too coarse ("implement the backend") — nobody can start, and the card sits there meaning
  "the whole project", which the board already tells you.
- Too fine ("add import statement") — the board becomes a checklist, and the cards the user
  actually needs to see get buried in noise.

A useful test: could you write a one-line acceptance check for this card? If not, it is probably
too coarse. Would you feel silly telling a colleague you finished it? Probably too fine.

Sequencing belongs in `details`, not in the board structure. If task B depends on A, say so in
B's details rather than withholding B from the board — the user wants to see the whole plan,
including the parts that cannot start yet.

### 7. Capture work discovered mid-task

Real work uncovers more work. When something surfaces while you are on a card, decide what it is
before touching the board:

| What you found | Where it goes |
|---|---|
| Separate schedulable work, out of scope for this card | **A new card**, To Do, same project |
| Detail, evidence, or a decision about the card in hand | A comment on the current card |
| A trivial fix you can just do now | Do it; mention it in a comment |
| A blocker stopping this card | Comment naming it, and set the card Blocked |

The bar for a new card is "someone could pick this up on its own and know when it is done" — the
same bar as operation 6. Applying it matters because the failure is asymmetric: a missing card
means the work is forgotten, but a board full of micro-cards means the user stops reading the
board, and then *everything* is forgotten.

When you do create one, record where it came from in its details — "found while working card
1234567890" — so the user can trace why it exists. Then carry on with the card you were on.
Discovering work is not a reason to switch tasks; capture it and keep going, unless it blocks
you, in which case operation 3 applies.

Do not silently expand the card you are on to cover what you found. That is how a small task
becomes an unreviewable change, and it is the same scope drift the Blocked-not-Done rule exists
to prevent.

## Dispatching subagents against the board

When you spawn subagents on trackable work, you own the board and they update it. This gives
live visibility without the duplicate-card races that direct creation invites.

Create the card first, then put its id in the brief:

```
Board card: 1234567890  (https://your-org.monday.com/boards/<BOARD_ID>/pulses/1234567890)
Project: My Service
Update this card as you work — the agent-kanban skill explains how.
Do not create a new card; this one is yours.
```

The brief must name the card id. Without it the subagent has nothing to update, and it will
either stay silent or invent a card.

Include the project too. A subagent cannot ask the user which project this is, so if it ever
needs to create or re-file anything, the project has to have travelled with the brief. You
already know it — you asked before creating the card.

### Running a whole plan at once

For a plan large enough that dispatching card by card is the tedious part, a single Workflow
orchestrator can decompose the doc, run an agent per card in its own worktree, review each PR,
and report every result back onto the board. `references/orchestration.md` has the preconditions
and a template script.

**Offer it; never assume it.** The Workflow tool requires explicit user opt-in on every run, so
this skill cannot start one on its own. Write the cards (operation 6), tell the user the
orchestrator exists, and let them choose. Writing the cards is the default behaviour; running
them is the upgrade.

## Never invent a status

Status labels are board configuration, not free text, and writing one that does not exist
either errors or silently does nothing.

- On monday.com the labels are fixed and listed in the config file. Use them verbatim.
- On Jira, ask for the available transitions for that specific card before moving it —
  reachability depends on the card's current status, so a rejection usually means "not from
  here", not "no such status".

When a status change is rejected, report it and stop. Do not cycle through guesses until one
is accepted: you may land the card in a plausible-looking wrong column, and quiet wrongness
is harder to spot than an open error.

## Showing the board

When the user asks what's happening they want to scan, not read. Group by project, order by
most recently updated, and keep it to one line per card:

```
My Service
  ● In Progress   Fix retry backoff in webhook sender     agent:builder-a   PR #42
  ○ To Do         Audit auth middleware                   —                 —

Dev Center
  ✖ Blocked       Migrate config loader to pydantic       agent:builder-c   needs infra approval

4 done in the last day · board: https://your-org.monday.com/boards/<BOARD_ID>
```

Group by project by default, because "which project is this" is how the user thinks about their
work. If they ask a status-shaped question instead ("what's blocked?", "what's in flight?"),
group by status and put the project on each row — answer the axis they asked about rather than
reformatting their question into the default.

Always include the blocker reason on Blocked rows — a blocked card the user cannot act on is
just noise. Collapse Done to a count unless asked for it; finished work crowds out the rows
that actually need attention. Link the board at the end so the user can open the real thing.

If the board is empty, say so plainly. Do not pad the answer with cards that are not there.
