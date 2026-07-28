# agent-kanban Briefs and Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a card carry a full task brief despite monday's 2000-character `details` cap, and add a Workflow-based orchestrator that runs a whole design doc from decomposition through build, review, and PR.

**Architecture:** Separate transport from display. `details` becomes a fixed-shape summary sized for a human scanning the board; the full brief moves to the card's first update, which is append-only and already in the read path. On top of that, a Workflow script decomposes a design doc into cards and pipelines each one through build → review → one fix round in isolated worktrees, reconciling any card whose agent died.

**Tech Stack:** Markdown skill files (`SKILL.md` + `references/*.md`), monday.com GraphQL via the `all_monday_api` MCP tool, Claude Code's `Workflow` tool (plain JS, not TypeScript).

**Spec:** `docs/superpowers/specs/2026-07-28-agent-kanban-orchestration-design.md`

## Global Constraints

- **This repo is public and personal.** Never write a real board id, workspace id, column id, monday subdomain, or work email into any file. Use `<BOARD_ID>`, `<status_col>`, `your-org.monday.com` — the convention already used in `references/monday.md` and `evals/evals.json`.
- **There is no test runner in this repo.** CI is `.github/workflows/leak-scan.yml` only. Verification for each task is an explicit `grep`/`rg` assertion plus, where stated, a live run against the board.
- **`details` cap is exactly 2000 characters.** Monday-enforced, not configurable.
- **No update-body size limit has been observed.** Splitting a brief is a *fallback* on rejection, never a routine step. Do not document a numeric cap.
- **Workflow scripts are plain JavaScript.** No type annotations, no `Date.now()`, no `Math.random()`, no `new Date()` with no arguments.
- **Prose in skill files is normal English**, not caveman. Skill files are read by agents and by other people.
- The skill's frontmatter `description` is **not** changed by this plan.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `skills/agent-kanban/SKILL.md` | Card contract — what fields exist and what they mean | 1 |
| `skills/agent-kanban/references/monday.md` | The 2000 cap, update HTML formatting, the split fallback | 1 |
| `skills/agent-kanban/SKILL.md` | Operations 1, 5, 6 — when the brief is written and read | 2 |
| `skills/agent-kanban/references/orchestration.md` | **New.** Preconditions, brief-passing contract, template script | 3 |
| `skills/agent-kanban/SKILL.md` | "Dispatching subagents" — pointer to orchestration, opt-in rule | 3 |
| `skills/agent-kanban/evals/evals.json` | Eval 8 — brief goes to an update, not into `details` | 4 |
| `.claude-plugin/plugin.json` | Version bump | 5 |

---

### Task 1: Card contract and the 2000-character cap

**Files:**
- Modify: `skills/agent-kanban/SKILL.md` (the card contract table, ~line 84–93)
- Modify: `skills/agent-kanban/references/monday.md` (new section after "Column value formats", ~line 196)

**Interfaces:**
- Consumes: nothing.
- Produces: the terms **Task Brief** (the card's first update) and the marker string `<b>Task Brief</b>`. Tasks 2, 3, and 4 all depend on that exact marker string.

- [ ] **Step 1: Replace the `details` row in the card contract table**

In `SKILL.md`, the contract table currently has:

```markdown
| details | Enough context that a fresh agent could pick it up cold | goal, constraints, acceptance check |
```

Replace that single row with two rows:

```markdown
| details | Summary for a human scanning the card. **Hard-capped at 2000 chars.** | `Goal: … / Constraints: … / Done when: … / Depends on: …` |
| brief | The full spec, posted as the card's **first update**. No practical size limit. | the slice of the design doc this card implements |
```

- [ ] **Step 2: Add the explaining subsection**

In `SKILL.md`, immediately after the `### Titles are for humans, keys are for machines` subsection (before `## The two flows this exists for`), add:

```markdown
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
```

- [ ] **Step 3: Add the cap and formatting section to `monday.md`**

In `references/monday.md`, after the `### New projects need no label management` section and
before `### Removing a stale project label`, add:

```markdown
### Details is capped at 2000 characters — the brief goes in an update

`long_text` columns reject anything over 2000 characters. There is no setting for this. Keep
`Details` to the four-line summary (`Goal:` / `Constraints:` / `Done when:` / `Depends on:`)
and post the full brief as the card's first update instead. See SKILL.md for why.

**Update bodies are HTML, not markdown.** `create_update` renders its `body` as HTML, so
markdown passes through literally — `## Context` shows up as the characters `## Context`, and
`- item` as `- item`. Convert before posting:

| You want | Write |
|---|---|
| a heading | `<b>Context</b><br>` |
| a line break | `<br>` |
| a bullet | `<ul><li>…</li></ul>` |
| code or a path | `<pre>src/webhook/retry.py</pre>` |

Begin a brief with `<b>Task Brief</b><br>` so it can be told apart from progress updates.

**No size limit has been observed on update bodies** — briefs many times the size of the
`Details` cap post fine. Do not pre-split on a guessed threshold. If monday ever *does* reject
one as too large, post the remainder as a second update beginning `<b>Task Brief (cont.)</b>`
rather than cutting the brief down.
```

- [ ] **Step 4: Verify the edits landed and leaked nothing**

Run:

```bash
cd skills/agent-kanban
rg -n 'Task Brief' SKILL.md references/monday.md
rg -n '2000' SKILL.md references/monday.md
rg -n 'Enough context that a fresh agent' SKILL.md ; echo "exit=$?"
rg -n '\b\d{8,}\b|\b(text|color|dropdown|link|long_text|group|mirror)_[a-z0-9]{6,}\b' SKILL.md references/monday.md | rg -v '1234567890' ; echo "exit=$?"
rg -n 'monday\.com' SKILL.md references/monday.md | rg -v 'your-org' ; echo "exit=$?"
```

Expected:
- `Task Brief` appears in both files (at least 4 hits total).
- `2000` appears in both files.
- The old `details` row is **gone** — third command prints `exit=1`.
- No real board id or column id — fourth prints `exit=1`.
- No real monday subdomain — fifth prints `exit=1`.

Those last two match on the *shape* of a real id (a long digit run, a
`<type>_<random>` column id, a subdomain that is not the `your-org` placeholder)
deliberately. Never write the actual values into a check — this repo is public,
and a grep pattern leaks just as effectively as a config dump.

- [ ] **Step 5: Commit**

```bash
git add skills/agent-kanban/SKILL.md skills/agent-kanban/references/monday.md
git commit -m "feat(agent-kanban): split the card brief out of the capped details column

Monday caps long_text at 2000 characters, so a brief carrying a slice of a
design doc gets truncated and the card stops being pickupable cold. Details
now holds a fixed four-line summary and the full brief moves to the card's
first update, marked with <b>Task Brief</b> so agents can tell it apart from
the progress log. Also documents that update bodies render as HTML, which
markdown briefs otherwise fail silently on."
```

---

### Task 2: Operations 1, 5, and 6 write and read the brief

**Files:**
- Modify: `skills/agent-kanban/SKILL.md` (operation 1 ~line 172–191, operation 5 ~line 232–243, operation 6 ~line 244–273)

**Interfaces:**
- Consumes: the marker `<b>Task Brief</b>` from Task 1.
- Produces: nothing new. This task wires the contract into the procedures.

- [ ] **Step 1: Add the brief step to operation 1**

In `### 1. Add a task`, the numbered list currently ends:

```markdown
5. **Not found** → create the card in To Do with the full contract above, setting both the
   Project column and the matching group.
6. Report the card id and URL.
```

Replace those two items with:

```markdown
5. **Not found** → create the card in To Do with the full contract above, setting both the
   Project column and the matching group.
6. **Post the Task Brief** as an update on the new card. A card is not finished until its
   brief is on it — a card with a four-line summary and no brief is *less* useful than the
   old truncated one, because it looks complete while carrying nothing to work from.
7. Report the card id and URL.
```

- [ ] **Step 2: Add the brief read to operation 5**

In `### 5. Pick up a specific task`, replace step 1:

```markdown
1. Fetch the card **and its updates**. Prior updates are where an earlier attempt recorded
   why it stopped, which is usually the highest-value context available.
```

with:

```markdown
1. Fetch the card **and its updates**, then read them in two passes:
   - The oldest update marked `<b>Task Brief</b>` is the spec. Read it before anything else;
     `details` is only a summary of it.
   - The rest are the progress log, newest last. This is where an earlier attempt recorded
     why it stopped, which is usually the highest-value context available.

   If there is no Task Brief update, the card predates this convention — work from `details`
   and say in your first update that the card had no brief.
```

- [ ] **Step 3: Add per-card briefs to operation 6**

In `### 6. Break a plan into tasks`, replace step 4:

```markdown
4. Create them in a single call. The reference file shows how to alias several creates into one
   mutation, which matters because a half-applied plan is worse than none — the user cannot tell
   which parts made it onto the board.
```

with:

```markdown
4. Create them in a single call. The reference file shows how to alias several creates into one
   mutation, which matters because a half-applied plan is worse than none — the user cannot tell
   which parts made it onto the board.
5. Post a Task Brief on each card, carrying **only the slice of the source document that card
   implements** — plus the files in scope, the interfaces it must honour, its acceptance
   criteria, and what is explicitly out of scope. Do not paste the whole document onto every
   card: an agent that has to work out which third of a spec applies to it is back to having
   no brief.
```

Then renumber the existing step 5 to 6.

- [ ] **Step 4: Verify**

Run:

```bash
cd skills/agent-kanban
rg -n -A2 'Post the Task Brief' SKILL.md
rg -n 'oldest update marked' SKILL.md
rg -n 'only the slice of the source document' SKILL.md
rg -n '^7\. Report the card id' SKILL.md
```

Expected: one hit each. The last confirms operation 1 was renumbered rather than having a step overwritten.

- [ ] **Step 5: Commit**

```bash
git add skills/agent-kanban/SKILL.md
git commit -m "feat(agent-kanban): wire the Task Brief into operations 1, 5 and 6

Operation 1 now treats a card as unfinished until its brief is posted,
operation 5 reads the brief before the progress log, and operation 6 gives
each card only the slice of the source document it implements. Operation 5
also handles cards created before this convention rather than assuming a
brief is always present."
```

---

### Task 3: The orchestration reference

**Files:**
- Create: `skills/agent-kanban/references/orchestration.md`
- Modify: `skills/agent-kanban/SKILL.md` (the `## Dispatching subagents against the board` section, ~line 301–320)

**Interfaces:**
- Consumes: the marker `<b>Task Brief</b>` (Task 1); operations 1 and 6 as amended (Task 2).
- Produces: the workflow script contract — `args` is `{ doc, project, repo, baseBranch }`, and the script's return value is `{ cards: [{agent_key, id, url, pr_url, status}], dead: [agent_key] }`. Task 5's smoke test relies on both.

- [ ] **Step 1: Create `references/orchestration.md`**

Write the file with exactly this content:

````markdown
# Running a whole plan with a Workflow orchestrator

Operation 6 gets a design doc onto the board. This file gets the board *done*: one orchestrator
decomposes the doc, dispatches an agent per card, reviews each PR, and reports every result back
onto the board as it happens.

Read `monday.md` first — every board call here follows its mechanics.

## The orchestrator is offered, never assumed

The `Workflow` tool requires explicit user opt-in on every run. This skill cannot fire one on
its own, and must not try. When a plan looks big enough to be worth orchestrating, say so and
let the user choose:

> "That's 6 cards. I can run them as a workflow — an agent per card in its own worktree, each
> one reviewed and reported back onto the board — or write the cards and stop there. Which?"

If they decline, or say nothing about it, do operation 6 and stop. Writing the cards is the
default; running them is the upgrade.

## Settle everything before launching

The orchestrator cannot reach the user once it starts. A script that discovers halfway through
that it does not know the project has no way to ask, and its only honest option is to fail. So
confirm all of these first:

| Precondition | Why it cannot wait |
|---|---|
| project name | Operation 1's ask-never-infer rule still applies, and a script cannot ask. |
| design doc path | The decomposer reads it; a wrong path wastes the whole run. |
| repo and base branch | Builders branch from it and open PRs against it. |
| board config validated | Read `~/.claude/agent-kanban.json` and confirm its column ids are still on the board. A dead column id fails *silently* on some column types. |

## Transport is not display

The full brief goes to **two** places, and they are not the same channel:

- **Inline in each `agent()` prompt.** This is transport. It has no size limit and costs no
  board round trip, and it is why the 2000-character `details` cap does not constrain an
  orchestrated run at all.
- **As the card's Task Brief update.** This is display, and cold-start insurance. Tomorrow the
  user may point a plain agent at card 1234567890 with no orchestrator anywhere; the brief has
  to be on the card for that to work.

Every dispatched agent's prompt must carry the card id, the project, and the brief. Missing the
card id is the classic failure — the agent then has nothing to update and either goes silent or
invents a second card.

## Scale

Each card costs 1 build agent, 1 review agent, and sometimes 1 fix agent, on top of 2 planning
agents and possibly 1 reconcile agent. A 5-card plan is therefore ~13–18 agents, which sits at
the edge of the default medium workflow-size guideline. For anything larger, either run it in
batches of five and say so, or tell the user their workflow-size setting needs raising first.
Never silently truncate the card list — a plan that quietly ran two thirds of itself is worse
than one that refused.

## The template

Adapt this per plan; do not treat it as fixed. Pass `args` as
`{ doc, project, repo, baseBranch }`.

```javascript
export const meta = {
  name: 'kanban-plan',
  description: 'Decompose a design doc into board cards, build each in an isolated worktree, review the PR',
  phases: [
    { title: 'Plan', detail: 'decompose the doc, dedupe, create cards and briefs' },
    { title: 'Build', detail: 'one agent per card, isolated worktree, opens a PR' },
    { title: 'Review', detail: 'review each PR, at most one fix round' },
  ],
}

const { doc, project, repo, baseBranch } = args

const PLAN_SCHEMA = {
  type: 'object',
  required: ['cards'],
  properties: {
    cards: {
      type: 'array',
      items: {
        type: 'object',
        required: ['agent_key', 'title', 'details', 'brief'],
        properties: {
          agent_key: { type: 'string' },
          title: { type: 'string' },
          details: { type: 'string', maxLength: 2000 },
          brief: { type: 'string' },
        },
      },
    },
  },
}

const CREATED_SCHEMA = {
  type: 'object',
  required: ['cards'],
  properties: {
    cards: {
      type: 'array',
      items: {
        type: 'object',
        required: ['agent_key', 'id', 'url', 'existed'],
        properties: {
          agent_key: { type: 'string' },
          id: { type: 'string' },
          url: { type: 'string' },
          existed: { type: 'boolean' },
        },
      },
    },
  },
}

const BUILD_SCHEMA = {
  type: 'object',
  required: ['ok', 'branch', 'pr_url', 'summary'],
  properties: {
    ok: { type: 'boolean' },
    branch: { type: 'string' },
    pr_url: { type: 'string' },
    summary: { type: 'string' },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['blocking', 'notes'],
  properties: {
    blocking: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

// ---- Plan -----------------------------------------------------------------
// A barrier is correct here: dedupe needs every key at once, and no card can
// be dispatched before it has an id.

phase('Plan')

const plan = await agent(
  `Read ${doc}. Decompose it into independently pickupable cards for the project "${project}".
   Apply the agent-kanban skill's operation 6 granularity bar: every card needs a one-line
   acceptance check, and nothing so fine you would feel silly reporting it finished.
   For each card produce:
     agent_key  derived from stable facts, e.g. ${repo}/<slugified-goal>. Never a timestamp.
     title      human readable, no slugs
     details    at most 2000 characters, exactly four labelled lines:
                Goal: / Constraints: / Done when: / Depends on:
     brief      the FULL context an agent needs cold: the slice of ${doc} this card
                implements, files and directories in scope, interfaces it must honour,
                acceptance criteria, and what is explicitly out of scope.
                No length limit. Do not summarise, and do not paste the whole document.
   Return data only.`,
  { schema: PLAN_SCHEMA },
)

log(`${plan.cards.length} cards decomposed from ${doc}`)

const created = await agent(
  `Read ~/.claude/agent-kanban.json and the agent-kanban skill's references/monday.md.
   Project: "${project}". Cards:
   ${JSON.stringify(plan.cards)}
   Then, in this order:
     1. Dedupe every agent_key in ONE items_page query, using the CompareValue! variable form.
     2. Create the group titled "${project}" if it does not already exist.
     3. Create the not-found cards in ONE aliased mutation: status To Do, Project dropdown set,
        create_labels_if_missing: true, details from the card's details field.
     4. On every card — newly created or already existing without one — post the brief as an
        update whose body starts with <b>Task Brief</b><br>. Convert the markdown to HTML
        first; update bodies do not render markdown.
   Return one entry per input card: agent_key, item id, url, and whether it already existed.`,
  { schema: CREATED_SCHEMA },
)

const byKey = new Map(created.cards.map((c) => [c.agent_key, c]))
const work = plan.cards
  .map((c) => ({ ...c, ...(byKey.get(c.agent_key) || {}) }))
  .filter((c) => c.id)

log(`${work.length} cards on the board, dispatching`)

// ---- Build -> Review -> Fix ------------------------------------------------
// pipeline, not parallel: card B builds while card A is already in review.

const buildPrompt = (card) => `
Board card: ${card.id}  (${card.url})
Project: ${project}
Repo: ${repo}   Base branch: ${baseBranch}
Update this card as you work — the agent-kanban skill explains how.
Do not create a new card; this one is yours.

Claim it first: set Status to In Progress and put your own agent name in the Agent column.

<brief>
${card.brief}
</brief>

Then: branch from ${baseBranch}, do the work, run the project's tests, push the branch, and
open a PR with \`gh pr create\`. Put the PR URL in the card's Link column and post an update
saying what you ran and what it returned — the actual output, not a summary of it.
If you cannot finish, set the card to Blocked with an update naming the blocker, and return
ok: false. Do not set Done; the reviewer does that.`

const reviewPrompt = (card, build) => `
Review the PR at ${build.pr_url} (branch ${build.branch}) against the brief below.
Board card: ${card.id}. Project: ${project}.

<brief>
${card.brief}
</brief>

Blocking means: it does not meet the brief's acceptance criteria, it breaks something, or it
is unsafe. Style preferences and things you would have done differently are NOT blocking.
Post your findings as an update on the card either way.
If nothing is blocking, set the card to Done and say in that update what you verified and how.
Return the blocking findings as a list — empty if there are none.`

const fixPrompt = (card, build, review) => `
Board card: ${card.id}. Project: ${project}.
The PR at ${build.pr_url} was reviewed and these findings block it:
${review.blocking.map((b, i) => `${i + 1}. ${b}`).join('\n')}

Work on branch ${build.branch}: run \`git fetch\` and \`git checkout ${build.branch}\` — you
are in a FRESH worktree and do not have the builder's working tree. The pushed branch is the
only place that work exists.

<brief>
${card.brief}
</brief>

Fix exactly those findings, push, and re-check them yourself. Post an update on the card
listing which you fixed and which you could not. Then:
  all fixed  -> set the card Done, and say what you verified.
  any left   -> set the card Blocked, and say which remain.
Return the findings that are still blocking — empty if none.`

const results = await pipeline(
  work,
  (card) =>
    agent(buildPrompt(card), {
      label: `build:${card.agent_key}`,
      phase: 'Build',
      isolation: 'worktree',
      schema: BUILD_SCHEMA,
    }),
  async (build, card) => {
    if (!build || !build.ok) return { build, review: null, fix: null }
    const review = await agent(reviewPrompt(card, build), {
      label: `review:${card.agent_key}`,
      phase: 'Review',
      schema: REVIEW_SCHEMA,
    })
    return { build, review, fix: null }
  },
  async (res, card) => {
    if (!res.review || res.review.blocking.length === 0) return res
    const fix = await agent(fixPrompt(card, res.build, res.review), {
      label: `fix:${card.agent_key}`,
      phase: 'Review',
      isolation: 'worktree',
      schema: REVIEW_SCHEMA,
    })
    return { ...res, fix }
  },
)

// ---- Reconcile -------------------------------------------------------------
// agent() returns null when a subagent dies. Those cards are still sitting in
// In Progress with nobody on them, and a board that reports phantom work in
// flight is the exact failure this skill exists to prevent.

const dead = work.filter((c, i) => !results[i] || !results[i].build)

if (dead.length) {
  log(`${dead.length} card(s) produced no result — reconciling`)
  await agent(
    `These board cards were dispatched but their agent produced no result, so they may still
     be sitting in In Progress with nobody working them:
     ${JSON.stringify(dead.map((c) => ({ id: c.id, title: c.title })))}
     For each: if it is still In Progress, set it to Blocked and post an update saying the
     agent produced no result and the work was not attempted to completion. Leave any card
     already Done or Blocked alone.`,
    { label: 'reconcile', phase: 'Review' },
  )
}

return {
  cards: work.map((c, i) => {
    const r = results[i]
    const final = r && (r.fix || r.review)
    return {
      agent_key: c.agent_key,
      id: c.id,
      url: c.url,
      pr_url: (r && r.build && r.build.pr_url) || null,
      status: !r || !r.build ? 'no-result'
        : !r.build.ok ? 'blocked'
        : final && final.blocking.length ? 'blocked'
        : 'done',
    }
  }),
  dead: dead.map((c) => c.agent_key),
}
```

## Four things that break this if you change them

**State travels via the branch, not the worktree.** `isolation: 'worktree'` hands every agent a
*fresh* worktree, so the fix agent cannot inherit the builder's working tree — it has to fetch
and check out the pushed branch. Drop that `git fetch && git checkout` and the fix agent starts
from a clean base, silently discards the build, and "fixes" code that no longer has the feature
in it.

**Reconcile is not optional.** `agent()` returns `null` when a subagent dies on a terminal error
after retries. Skip the reconcile pass and those cards stay In Progress forever. The board then
answers "what are my agents doing" with work nobody is doing, which is worse than an empty
board because the user believes it.

**Each agent writes its own card; the orchestrator does not proxy.** That is what makes the
status live — the card flips to In Progress when the builder actually starts, not when the
script queued it. Batching board writes into the orchestrator would turn the board back into a
changelog.

**Nothing merges.** The run ends at an open PR with its URL on the card. `Done` here means "PR
open, review passed, ready for your review", and the card's final update should say exactly
that. An agent-approved, agent-written change does not reach the default branch without a
human looking at it.

## Reporting back

When the workflow returns, show the user one line per card — title, final status, PR link —
and name every card in `dead` explicitly. A card that produced no result is the single most
important thing in the run and it must not be summarised away.
````

- [ ] **Step 2: Point `SKILL.md` at it**

In `SKILL.md`, at the end of the `## Dispatching subagents against the board` section (after
the paragraph beginning "Include the project too."), append:

```markdown
### Running a whole plan at once

For a plan large enough that dispatching card by card is the tedious part, a single Workflow
orchestrator can decompose the doc, run an agent per card in its own worktree, review each PR,
and report every result back onto the board. `references/orchestration.md` has the preconditions
and a template script.

**Offer it; never assume it.** The Workflow tool requires explicit user opt-in on every run, so
this skill cannot start one on its own. Write the cards (operation 6), tell the user the
orchestrator exists, and let them choose. Writing the cards is the default behaviour; running
them is the upgrade.
```

- [ ] **Step 3: Verify the file is well-formed and leaks nothing**

Run:

```bash
cd skills/agent-kanban
test -f references/orchestration.md && echo "created"
rg -n 'export const meta' references/orchestration.md
rg -n "isolation: 'worktree'" references/orchestration.md | wc -l          # expect 2
rg -n 'git fetch' references/orchestration.md
rg -n 'Task Brief' references/orchestration.md
rg -n 'references/orchestration.md' SKILL.md
rg -n '\b\d{8,}\b|\b(text|color|dropdown|link|long_text|group|mirror)_[a-z0-9]{6,}\b' references/orchestration.md | rg -v '1234567890' ; echo "exit=$?"
rg -n 'Date\.now|Math\.random|: string|: number|interface ' references/orchestration.md ; echo "exit=$?"
```

Expected: `created`; `export const meta` present; exactly `2` worktree isolations (build and
fix, not review); `git fetch` present; `Task Brief` present; `SKILL.md` links the file; both
final commands print `exit=1` (no real ids, no TypeScript, no forbidden globals).

- [ ] **Step 4: Check the template script actually parses**

The script is embedded in markdown, so extract and syntax-check it. Run:

```bash
cd skills/agent-kanban
awk '/^```javascript$/{f=1;next} /^```$/{f=0} f' references/orchestration.md > /tmp/kanban-plan.mjs
node --check /tmp/kanban-plan.mjs && echo "parses"
```

Expected: `parses`.

If `node --check` reports `await is only valid in async functions` it is wrong about this file —
Workflow runs the body in an async context. Wrap the extracted copy for the check only:

```bash
{ echo 'export default async function () {'; sed 's/^export const meta/const meta/' /tmp/kanban-plan.mjs; echo '}'; } > /tmp/kanban-check.mjs
node --check /tmp/kanban-check.mjs && echo "parses"
```

Do not change `references/orchestration.md` to satisfy the checker — only the temporary copy.

- [ ] **Step 5: Commit**

```bash
git add skills/agent-kanban/references/orchestration.md skills/agent-kanban/SKILL.md
git commit -m "feat(agent-kanban): add a Workflow orchestrator for running a whole plan

Adds references/orchestration.md: a template workflow that decomposes a design
doc into cards, then pipelines each card through build, review and at most one
fix round, with an agent per card in its own worktree.

The brief travels two ways on purpose. Inline in each agent prompt, which is
transport and has no size limit, and onto the card as a Task Brief update,
which is display and cold-start insurance. That is what makes the 2000-character
details cap stop mattering on an orchestrated run.

Two correctness notes are called out in the file because getting either wrong
fails quietly: fix agents get a fresh worktree and must check out the pushed
branch, and the reconcile pass has to move dead agents' cards out of In
Progress or the board reports work nobody is doing.

The orchestrator is offered, never assumed — Workflow needs explicit user
opt-in on every run, so the skill cannot start one itself."
```

---

### Task 4: Eval for brief-goes-to-update

**Files:**
- Modify: `skills/agent-kanban/evals/evals.json`

**Interfaces:**
- Consumes: the marker `<b>Task Brief</b>` (Task 1) and operation 1 step 6 (Task 2).
- Produces: nothing.

- [ ] **Step 1: Update the `notes` field**

Replace the existing `notes` value with:

```
Iteration 3. Adds eval 8 for the details/brief split: details is a capped four-line summary and the full brief is posted as a Task Brief update. Iteration 2 rebuilt the skill around the two real use cases: bootstrapping a project from a design doc, and taking on a task with emergent-work capture. Runs against live Monday board <BOARD_ID> ('Agent Tasks', private). Project is a user-defined concept distinct from a repo, so the correct behaviour when it is unstated is to ASK. Evals 3 and 4 are a sequenced pair. Reset the board between iterations by deleting test items and the groups they created.
```

- [ ] **Step 2: Append eval 8**

Add this object as the last entry of the `evals` array (comma after eval 7's closing brace):

```json
{
  "id": 8,
  "name": "brief-goes-to-update-not-details",
  "prompt": "put the agent run history work on the board for the observability project — the design is at evals/fixtures/design-doc-run-history.md in the agent-kanban skill dir. i want each card to have enough on it that i can hand it to a fresh agent tomorrow without re-explaining anything",
  "expected_output": "THE BRIEF TEST. Project is stated ('observability'), so no question needed. Every card's Details column must hold the four-line summary (Goal / Constraints / Done when / Depends on) and stay under 2000 characters. The full brief must arrive as a separate update on each card whose body starts with <b>Task Brief</b> and is HTML, not raw markdown — a body containing literal '## ' or leading '- ' bullets is a failure. Each brief carries only the slice of the design doc that card implements, not the whole document copied onto every card. Cramming the brief into Details, truncating it to fit the cap, or creating cards with no brief at all are the three failures this catches. All cards land in To Do.",
  "files": ["evals/fixtures/design-doc-run-history.md"]
}
```

- [ ] **Step 3: Verify it is valid JSON and self-consistent**

Run:

```bash
cd skills/agent-kanban
python3 -c "
import json
d = json.load(open('evals/evals.json'))
ids = [e['id'] for e in d['evals']]
assert ids == list(range(1, 9)), ids
e8 = d['evals'][-1]
assert e8['name'] == 'brief-goes-to-update-not-details'
assert 'Task Brief' in e8['expected_output']
assert 'Iteration 3' in d['notes']
print('ok', len(d['evals']), 'evals')
"
```

Expected: `ok 8 evals`.

- [ ] **Step 4: Commit**

```bash
git add skills/agent-kanban/evals/evals.json
git commit -m "test(agent-kanban): add eval 8 for the details/brief split

Catches the three ways the split fails: cramming the brief into Details,
truncating it to fit the 2000-character cap, and creating cards with no brief
at all. Also checks the update body is HTML rather than raw markdown, since
markdown posts without error and only looks wrong afterwards."
```

---

### Task 5: Version bump and live smoke test

**Files:**
- Modify: `.claude-plugin/plugin.json`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Bump the plugin version**

In `.claude-plugin/plugin.json`, change `"version": "0.7.0"` to `"version": "0.8.0"`. Minor
bump: new capability, no breaking change to the existing card contract.

- [ ] **Step 2: Smoke-test the brief path against the real board**

This is the one check that cannot be done with `grep`. In a fresh session:

1. Invoke the skill and ask it to add one card, giving it a brief that is clearly over 2000
   characters (paste a long section of the spec).
2. Confirm on the board:
   - `Details` holds the four labelled lines and nothing more.
   - The card's first update starts with a bold **Task Brief** and renders as formatted HTML,
     not literal `##` characters.
   - The full brief is present and **not** truncated.
3. In a second fresh session, point an agent at that card id and confirm it reads the brief
   before the progress log.
4. Delete the test card.

Record the outcome — pass or fail, with what you actually saw — before committing. If the
update renders literal markdown, that is Task 1 Step 3's conversion table not being followed;
fix the reference file rather than working around it in the card.

- [ ] **Step 3: Verify the version and that nothing leaked across the whole change**

Run:

```bash
rg -n '"version"' .claude-plugin/plugin.json
git diff main --stat
git diff main | rg -n '\b\d{8,}\b|\b(text|color|dropdown|link|long_text|group|mirror)_[a-z0-9]{6,}\b' | rg -v '1234567890' ; echo "exit=$?"
git diff main | rg -n 'monday\.com|@' | rg -v 'your-org|omry\.amit@gmail\.com' ; echo "exit=$?"
```

Expected: version `0.8.0`; the diff touches only the five files in the File Structure table
plus the two docs files; both scans print `exit=1`.

If either scan hits, a real board id, column id, subdomain, or work email has reached a public
repo — fix it before committing, and check whether it also reached an earlier commit on this
branch.

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "chore(plugin): bump version to 0.8.0"
```

- [ ] **Step 5: Open the PR**

```bash
gh pr create --title "feat(agent-kanban): full task briefs and plan orchestration" --body "$(cat <<'EOF'
## What

Two changes to the agent-kanban skill.

**Full task briefs.** Monday caps `long_text` columns at 2000 characters, so a brief carrying a
slice of a design doc was getting truncated and the card stopped being pickupable cold.
`Details` now holds a fixed four-line summary and the full brief moves to the card's first
update, marked `<b>Task Brief</b>`. Operations 1, 5 and 6 are wired accordingly, and
`monday.md` documents the cap plus the fact that update bodies render as HTML rather than
markdown.

**Plan orchestration.** New `references/orchestration.md` with a template Workflow that
decomposes a design doc into cards, then pipelines each card through build, review and at most
one fix round, one agent per card in its own worktree. It stops at an open PR; merging stays a
human action.

## Notes

- The orchestrator is offered, never assumed. Workflow needs explicit user opt-in on every run.
- Two failure modes are called out in the reference because they fail quietly: fix agents get a
  fresh worktree and must check out the pushed branch, and the reconcile pass has to move dead
  agents' cards out of In Progress.
- The skill's frontmatter description is unchanged, to avoid disturbing its current recall.

Spec: `docs/superpowers/specs/2026-07-28-agent-kanban-orchestration-design.md`
Plan: `docs/superpowers/plans/2026-07-28-agent-kanban-orchestration.md`
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| Part A — card contract change | 1 |
| Part A — why an update, not a file column or link | 1 |
| Part A — HTML formatting, split fallback | 1 |
| Part A — operation changes (1, 5, 6) | 2 |
| Part B — opt-in rule | 3 |
| Part B — preconditions | 3 |
| Part B — brief-passing contract | 3 |
| Part B — template script, all three phases + reconcile | 3 |
| Part B — branch-not-worktree, reconcile, per-agent writes | 3 |
| Part B — fix policy (one round) | 3 |
| Part B — merge policy (never) | 3 |
| Files to change — evals | 4 |
| Files to change — version bump | 5 |
| Frontmatter description unchanged | Global Constraints |

No gaps.

**Type consistency:** `agent_key`, `title`, `details`, `brief` are the four card fields
throughout Task 3's schemas and prompts. `BUILD_SCHEMA` produces `{ok, branch, pr_url,
summary}` and `buildPrompt`, `reviewPrompt`, `fixPrompt` consume exactly those names.
`REVIEW_SCHEMA` produces `{blocking, notes}`; the pipeline branches on
`review.blocking.length` and the return block reads `final.blocking.length`. The marker string
is `<b>Task Brief</b>` in Tasks 1, 2, 3 and 4 with no variants.

**Out of scope, per the spec:** Jira orchestration, auto-merge, retrying a dead builder, and
migrating pre-existing cards. Operation 5's "no Task Brief update" fallback (Task 2, Step 2) is
the only concession to old cards, and it is a read-side default rather than a migration.
