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
if (!plan) throw new Error(`Decomposition agent produced no result for ${doc} — nothing was written to the board.`)

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
if (!created) throw new Error(`Card-creation agent produced no result — some cards may have been partially created or briefed on the board before it died. Check the "${project}" group manually before re-running.`)

const byKey = new Map(created.cards.map((c) => [c.agent_key, c]))
const work = plan.cards
  .map((c) => ({ ...c, ...(byKey.get(c.agent_key) || {}) }))
  .filter((c) => c.id)
const skipped = plan.cards.filter((c) => !byKey.get(c.agent_key) || !byKey.get(c.agent_key).id)
if (skipped.length) log(`${skipped.length} card(s) had no id after creation and will not be dispatched: ${skipped.map((c) => c.agent_key).join(', ')}`)

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
const noFinal = work.filter((c, i) => {
  const r = results[i]
  if (!r || !r.build || !r.build.ok) return false
  if (!r.review) return true // review agent died
  return r.review.blocking.length > 0 && !r.fix // blocking review, but fix agent died
})

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

if (noFinal.length) {
  log(`${noFinal.length} card(s) built successfully but the review or fix agent died — reconciling`)
  await agent(
    `These board cards had a successful build, but the review or fix stage never returned a
     result, so the card's board status may not reflect what actually happened:
     ${JSON.stringify(noFinal.map((c) => ({ id: c.id, title: c.title })))}
     For each: if it is still In Progress, set it to Blocked and post an update saying the
     review or fix agent produced no result and the change was never actually verified.
     Leave any card already Done or Blocked alone.`,
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
        : !final ? 'no-review'
        : final.blocking.length ? 'blocked'
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
important thing in the run and it must not be summarised away. A card with status `no-review`
must be named just as explicitly and never folded into a done count — its review agent died
mid-run, so nobody verified the PR, even though the board itself was never told it was Done.
