# Jira board mechanics

**monday.com is the tested path** (`references/monday.md`). Use Jira only when the work
belongs in a team's tracked backlog rather than on the personal agent board.

Honest status: the Jira MCP tools are present and read access is verified (312 projects
listable). The write path has **not** been exercised against a real card, because there is
no sandbox project with write access — that is exactly why the agent board lives on Monday.
Treat the write sequences below as correct-by-construction but unproven, and expect to
adjust on first real use.

## Setup: first run, when there is no config

1. `jira__list-projects` (paginated, 50 max per call) → let the user pick. Do not guess: on a
   corporate instance there are hundreds, and writing agent cards into the wrong team's backlog is
   noisy and hard to undo.
2. `jira__get-create-meta-data` for that project key → record the `issueTypeId` for Task, plus any
   required custom fields. These differ per project and a missing required field is the usual
   reason a create fails.
3. `jira__get-available-transitions` on any existing issue in the project → record the real status
   names and transition ids. Do not assume To Do / In Progress / Done.
4. Write `board_id`-equivalent details into `~/.claude/agent-kanban.json` under a `jira` key:
   project key, issue type id, and the status/transition mapping.

Jira has no per-board column ids, so setup is lighter than Monday's — the variable parts are the
project key, the issue type, and the workflow's real status names.

## Tools

| Purpose | Tool |
|---|---|
| find the project | `jira__list-projects`, `jira__get-project` |
| required fields + issue type ids | `jira__get-create-meta-data` |
| create | `jira__create-issue`, `jira__bulk-create-issues` |
| edit fields | `jira__update-issue` |
| move status | `jira__get-available-transitions`, then `jira__transition-issue` |
| progress log | `jira__comment-on-issue` |
| read / board view | `jira__get-issues` (takes JQL), `jira__get-issue-changelog` |

## Field mapping

| Card contract field | Jira |
|---|---|
| `agent_key` | a label, `agentkey-<slug>` |
| project | the Jira project, or a component/label |
| title | summary |
| status | status, via a transition id |
| agent | a label `agent-<name>`, since agents have no Jira account |
| details | description (Markdown is accepted) |
| link | a comment containing the URL |
| updates | comments |

Slugify `agent_key` for label use: lowercase, every character outside `[a-z0-9-]` becomes
`-`. Jira labels cannot contain spaces. Keep the `agentkey-` prefix so the dedupe search is
unambiguous and these labels never collide with the team's own.

## Creating a card takes two calls, not one

`create-issue` accepts only `projectKey`, `summary`, `issueTypeId`, `description`, and
`customFields` — **there is no labels parameter.** Since `agent_key` lives in a label, the
sequence is:

1. `get-create-meta-data` for the project → pick the `issueTypeId` for Task, and note any
   required custom fields. Projects differ here, and a missing required field is the usual
   reason a create fails.
2. Dedupe: `get-issues` with JQL `project = KEY AND labels = "agentkey-<slug>"`. Non-empty →
   update that issue instead of creating a second one.
3. `create-issue`.
4. `update-issue` on the new key to attach `agentkey-<slug>` and `agent-managed` labels.

Step 4 is not optional. Until the label is attached the card is invisible to the dedupe
search, so a concurrent agent creating the same task will not find it. Keep the window
between 3 and 4 as tight as possible, and if step 4 fails, say so — an unlabelled card will
be duplicated later and nobody will know why.

## Status: ask, never guess

```
get-available-transitions(issueKey) → pick the transition whose name matches the target
transition-issue(issueKey, transitionId)
```

Transitions are keyed by id, and which ones exist depends on the card's *current* status in
that project's workflow. So a rejected move usually means "not reachable from here", not "no
such status". This is why the board rule is to ask per card rather than assume a
To Do / In Progress / Done trio — real team projects use names like Ready, In Review, or
Shipped, and reachability is genuinely restricted.

Report a rejection and stop. Do not try other transitions until one is accepted.

## Board view

```
get-issues(projectKey: "KEY", jql: "project = KEY AND labels = 'agent-managed' ORDER BY updated DESC",
           fields: ["key","summary","status","assignee","updated"], maxResults: 50)
```

`maxResults` defaults to **1**, which is an easy way to conclude the board is nearly empty
when it is not. Always set it explicitly.

Narrow to live work with `AND statusCategory != Done`.

## Don't delete

There is no delete tool exposed, which is the right default. A wrong card gets transitioned
to a cancelled or done status with a comment explaining why — that keeps the history the
board exists to provide.
