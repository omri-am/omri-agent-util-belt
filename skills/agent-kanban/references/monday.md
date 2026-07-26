# monday.com board mechanics

Everything here was verified against a live board. Where the MCP tools misbehave, the working
alternative is given — trust this file over the tool descriptions, which are wrong in three
places (`create_item`, `update_item_column_values`, and `create_column` for status columns).

**Contents**

- [Column ids are examples, not constants](#column-ids-in-this-file-are-examples-not-constants) — read before copying any query
- [The board](#the-board) — current ids, and why project lives in two places
- [Setup: first run](#setup-first-run-when-there-is-no-config) — choosing/creating a board, the status-column recipe, mapping an existing board
- [The stringified-JSON trap](#the-one-trap-that-matters-column-values-must-be-a-stringified-json) — why two MCP tools are unusable, and the column value formats
- Operations: [add](#1-add-a-task) · [add many](#1b-create-several-cards-at-once-breaking-a-plan-into-tasks) · [update](#2-update-a-task) · [complete](#3-complete-a-task) · [post an update](#4-post-an-update-progress-log) · [board view](#5-board-view)
- [Views cannot be created from the API](#board-views-cannot-be-created-from-the-api)
- [Status labels are effectively immutable](#status-labels-are-effectively-immutable--dont-fight-them)

If you are mid-task and just need one query, jump to the operation. Read Setup only when the
config file is missing or stale.

## Every id in this file is a placeholder

All the `<…>` tokens below — `<BOARD_ID>`, `<status_col>`, `<group_id>`, `<item_id>` and friends —
must be substituted with real values before you send a query. Monday generates column ids per
column, so the same logical column on a different board has a completely different id, and none of
them can be guessed from a column's title.

**Take the real values from `~/.claude/agent-kanban.json`**, or from `get_board_schema` when the
config is missing or stale. Sending an id that does not exist on the target board is the single
easiest way to break this skill: some column types reject it with a clear error, but others accept
the write and silently drop it, leaving a card that looks created while missing its project or
status.

## The board

Read `~/.claude/agent-kanban.json` for the real ids. What each placeholder maps to:

| Placeholder | Config key | Purpose |
|---|---|---|
| `<BOARD_ID>` | `monday.board_id` | the board itself |
| `<WORKSPACE_ID>` | `monday.workspace_id` | workspace it lives in |
| `<project_col>` | `columns.project` | dropdown; **source of truth** for the project axis |
| `<status_col>` | `columns.status` | status; the Kanban stage |
| `<agent_key_col>` | `columns.agent_key` | text; dedupe identity |
| `<agent_col>` | `columns.agent` | text; who holds it |
| `<link_col>` | `columns.link` | link; primary artifact |
| `<details_col>` | `columns.details` | long_text; goal/constraints/acceptance |
| `<fallback_group_id>` | `groups.fallback_group_id` | the "Unsorted" group |

Groups mirror the Project label, so a group id is looked up by title rather than stored per
project. Status label names come from `monday.statuses` — do not assume the four defaults.

### Why project lives in two places

Monday's Kanban view can only group by a **status- or dropdown-type column** — never by
groups. So a project that existed only as a group could never drive a Kanban-by-project, which
is why the dropdown column exists. Groups mirror it because groups are what make the default
table view readable at a glance.

The dropdown is authoritative. Set both in the same create call so they cannot drift, and if
you ever find a card whose group and Project label disagree, trust the column and fix the group.

Dropdown was chosen over a status column deliberately: status labels here are effectively
immutable (see the end of this file), while projects are open-ended and appear over time.

Item URLs are `https://your-org.monday.com/boards/<BOARD_ID>/pulses/<item_id>`, and `create_item`
returns the `url` field directly — return it to the user so they can click through.

## Setup: first run, when there is no config

### Let the user choose a board

```graphql
query { me { id name } workspaces(limit: 50) { id name kind } }
query { boards(workspace_ids: [WS_ID], limit: 50) { id name state board_kind items_count } }
```

Present the options and let them pick, or create a dedicated board. `boards(order_by: created_at)`
with no workspace filter also works if they do not know which workspace it lives in.

### Creating a board from scratch

Follow this order. Several of these shapes are counter-intuitive and were established by trial;
improvising here produces confusing validation errors.

```graphql
mutation { create_board(board_name: "Agent Tasks", board_kind: private, workspace_id: WS_ID,
                        board_description: "...") { id } }
```

A newly created board arrives with **only a `name` column** and one group (`topics`), despite the
`create_board` tool description claiming defaults of Name/Person/Status/Date. So create every
column yourself.

Straightforward ones — the MCP `create_column` tool is fine for these:

| Contract field | Type | Title |
|---|---|---|
| `agent_key` | `text` | Agent Key |
| `agent` | `text` | Agent |
| `link` | `link` | Link |
| `details` | `long_text` | Details |

`project` — use a **dropdown**, so its label set can grow as new projects appear:

```graphql
mutation { create_dropdown_column(board_id: ID, title: "Project", description: "...") { id } }
```

Leave its labels empty. `create_labels_if_missing: true` populates them on first use.

`status` — this is the fiddly one, and it must go through `all_monday_api`:

```graphql
mutation ($boardId: ID!, $defaults: JSON!) {
  create_column(board_id: $boardId, title: "Status", column_type: status, defaults: $defaults) { id settings_str }
}
```

```json
{ "defaults": "{\"labels\":{\"0\":\"To Do\",\"1\":\"Done\",\"2\":\"Blocked\",\"3\":\"In Progress\"},\"labels_positions_v2\":{\"0\":0,\"3\":1,\"2\":2,\"1\":3}}" }
```

Three things are load-bearing in that payload:

- **Go through `all_monday_api`, not the MCP `create_column` tool.** The tool imposes a stricter
  schema demanding `labels` as an array of objects each with an integer `color`, and rejects
  Monday's own documented object-map form. Raw GraphQL accepts the documented form.
- **`Done` must sit at index 1.** `done_colors` is pinned to `[1]` regardless of what you pass —
  verified by trying to set it to `[3]` and watching it come back as `[1]`. Whatever label occupies
  index 1 is what Monday treats as complete, so putting an in-flight label there makes progress
  indicators count unfinished work as done.
- **`labels_positions_v2` fixes display order**, since index order would otherwise show
  To Do / Done / Blocked / In Progress. The map is `{label_index: display_position}`.

The default colours that fall out of this are sensible: index 1 green, 2 red, 3 blue, 0 orange.

Finally rename the default group so it reads as a fallback rather than a placeholder:

```graphql
mutation { update_group(board_id: ID, group_id: "topics", group_attribute: title, new_value: "Unsorted") { id title } }
```

### Mapping an existing board instead

```graphql
query { boards(ids: [ID]) { groups { id title } columns { id title type settings_str } } }
```

Match each contract field to a column by **type first, then title**. Type is the binding
constraint: `status` for the stage, `dropdown` or `status` for project, `text` for agent key and
agent, `long_text` for details, `link` for link.

Read `settings_str` on the status column to learn the board's real stage labels, and record those
verbatim in the config — do not assume To Do / In Progress / Blocked / Done. Teams use Ready, In
Review, Shipped, and localised names, and writing a label that does not exist fails.

If a needed column is absent, create it as above. Show the user the full mapping before writing
anything, and never adopt a column that belongs to an existing workflow just because its type
fits — agent writes would overwrite real data on every update.

### Then write the config

Record `board_id`, `board_url`, `workspace_id`, every resolved column id, the real status labels,
and the fallback group id. That file is what makes every later run skip all of the above.

## The one trap that matters: column values must be a stringified JSON

`create_item` and `update_item_column_values` both declare `columnValues` as an *object* in
their MCP schema, but Monday's API requires the whole thing to be a **JSON string**.
Passing an object fails with:

```
Variable $d of type JSON was provided invalid value ... "Invalid type, expected a JSON string"
```

There is no way to express a root-level string through those tools' schemas, so **do not use
them for anything involving column values.** Use `all_monday_api` and pass the stringified
JSON as a variable. Doing it as a variable rather than inlining it into the query text
avoids a second layer of escaping, which is where this otherwise gets painful.

Tools that work fine as-is: `create_update` (comments), `get_board_schema`,
`search_board_items_by_name`, `create_board`, `create_column`, `move_item_to_group`,
`delete_item`.

### Column value formats

Inside that stringified JSON:

| Column type | Format |
|---|---|
| text (`Agent Key`, `Agent`) | plain string — `"agent:builder-a"` |
| status (`Status`) | `{"label": "In Progress"}` — must match a label exactly |
| dropdown (`Project`) | `{"labels": ["My Service"]}` — note the plural and the array |
| link (`Link`) | `{"url": "https://...", "text": "PR #42"}` |
| long_text (`Details`) | plain string, `\n` for newlines |

### New projects need no label management

Pass **`create_labels_if_missing: true`** on `create_item`, `change_multiple_column_values`, or
`change_column_value`, and Monday creates a missing dropdown label for you. So writing a project
that has never appeared before is a single call — there is no separate "register the project"
step, and no need for `update_dropdown_column` (which additionally demands a `revision`
argument and is best left alone).

The flip side is that a typo becomes a new project silently, and **labels outlive the cards that
created them** — deleting every card using a label leaves the label in the dropdown. Verified.
That is the mechanical reason the skill tells you to ask rather than infer: `create_labels_if_missing`
will faithfully create `My Servcie` and it will sit there until someone removes it by hand.
Prefer an existing label whenever one plausibly matches.

### Removing a stale project label

Unlike status labels, dropdown labels *can* be edited — but the call has two non-obvious
requirements, so read the column first:

```graphql
query { boards(ids: [BOARD]) { columns(ids: ["<project_col>"]) { revision settings_str } } }
```

```graphql
mutation ($boardId: ID!, $rev: String!) {
  update_dropdown_column(board_id: $boardId, id: "<project_col>", revision: $rev,
                         settings: {labels: [{id: 1, label: "Platform Maintenance"}]}) { id settings_str }
}
```

- **`revision` is required** and comes from the `revision` field on `Column`. It is an optimistic
  concurrency token, so fetch it immediately before the update.
- **`labels` is a full replacement**, not a patch. List every label you want to keep; anything
  omitted is removed.
- **The write field is `label`, but the read field is `name`.** `settings_str` returns
  `{"id":1,"name":"..."}` while `UpdateDropdownLabelInput` requires `label` — passing `name`
  fails with a missing-required-field error.

**Keep each surviving label's existing `id`.** Card values reference labels by id, so re-listing a
label under a different id would silently detach it from every card using it. Copy the ids
straight from `settings_str`.

Before removing a label, confirm no card still uses it — move those cards to their new project
first. Removing a label that is in use is how a card ends up with an empty project, which drops it
out of the cross-project view.

## 1. Add a task

Dedupe first. The `agent_key` filter is an exact match on the text column, which is why the
key must be derived rather than invented — see SKILL.md.

```graphql
query ($boardId: ID!, $key: String!) {
  boards(ids: [$boardId]) {
    items_page(query_params: {rules: [{column_id: "<agent_key_col>", compare_value: [$key], operator: any_of}]}) {
      items { id name url group { id title } column_values(ids: ["<status_col>", "<agent_col>"]) { id text } }
    }
  }
}
```

Non-empty `items` → the card exists. Update it and tell the user it already existed.

Do **not** use `search_board_items_by_name` for this. It matches on item *name*, which is
the one field that legitimately gets reworded — so it produces both false negatives (title
was edited) and false positives (another card shares words). The dedupe check has to be
exact or it is worse than useless, because a near-miss silently creates the duplicate it
was supposed to prevent.

**Watch the variable type if you check several keys at once.** `compare_value` is a
`CompareValue!`, not a list of strings — declaring `$keys: [String!]` fails schema validation.
Either inline the array as above with a `String!` variable, or type the variable as
`CompareValue!` and pass the whole array through it:

```graphql
query ($boardId: ID!, $keys: CompareValue!) {
  boards(ids: [$boardId]) {
    items_page(query_params: {rules: [{column_id: "<agent_key_col>", compare_value: $keys, operator: any_of}]}) {
      items { id name url }
    }
  }
}
```

Batching keys this way is worth it when dispatching several subagents — one dedupe query
covers every card you are about to create instead of one query per card.

### Make sure the project's group exists

An item cannot be filed into a group that does not exist, and the group title must equal the
Project label. Read the board's groups and create one if this project is new:

```graphql
mutation ($boardId: ID!, $name: String!) {
  create_group(board_id: $boardId, group_name: $name) { id title }
}
```

Use the project name exactly as it appears in the Project dropdown, so cards for one project
always land together instead of splitting across near-duplicates. If the work genuinely has no
project, use the `<fallback_group_id>` ("Unsorted") group — but prefer asking the user, since an
unsorted card is one the cross-project view cannot place.

### Create

```graphql
mutation ($boardId: ID!, $groupId: String!, $name: String!, $cv: JSON!) {
  create_item(board_id: $boardId, group_id: $groupId, item_name: $name,
              column_values: $cv, create_labels_if_missing: true) {
    id name url
  }
}
```

with variables:

```json
{
  "boardId": "<BOARD_ID>",
  "groupId": "group_xxxxxxxx",
  "name": "Fix retry backoff in Slack webhook sender",
  "cv": "{\"<project_col>\":{\"labels\":[\"My Service\"]},\"<agent_key_col>\":\"my-service/fix-retry-backoff\",\"<agent_col>\":\"agent:builder-a\",\"<status_col>\":{\"label\":\"To Do\"},\"<details_col>\":\"Goal: ...\\nConstraints: ...\\nDone when: ...\"}"
}
```

Report the returned `id` and `url`. The id is the handle for every later update; without it
the card is an orphan nobody touches again.

## 1b. Create several cards at once (breaking a plan into tasks)

GraphQL executes top-level mutation fields **serially, in document order**, so several aliased
`create_item` calls are one request that either lands as a unit or fails visibly partway — much
better than N separate calls, where a failure halfway leaves a plan the user cannot audit.

Create the group once first (if the project is new), then:

```graphql
mutation ($boardId: ID!, $groupId: String!, $cv1: JSON!, $cv2: JSON!, $cv3: JSON!) {
  t1: create_item(board_id: $boardId, group_id: $groupId, item_name: "Add signing-secret rotation",
                  column_values: $cv1, create_labels_if_missing: true) { id name url }
  t2: create_item(board_id: $boardId, group_id: $groupId, item_name: "Cover verification.ts with tests",
                  column_values: $cv2, create_labels_if_missing: true) { id name url }
  t3: create_item(board_id: $boardId, group_id: $groupId, item_name: "Remove the debug-message endpoint",
                  column_values: $cv3, create_labels_if_missing: true) { id name url }
}
```

Each `cv` is its own stringified JSON with that card's `agent_key`, project label, `To Do` status,
and details. Every alias must be unique — reusing one silently drops a card from the result.

Dedupe the whole batch in a single query first, using the `CompareValue!` form above with every
key you are about to create. One query, then one mutation, for an entire plan.

Practical ceiling: keep a batch to roughly 20 cards. Beyond that the query text gets unwieldy and
a single validation error costs the whole request — split into two mutations and say so.

## 2. Update a task

```graphql
mutation ($boardId: ID!, $itemId: ID!, $cv: JSON!) {
  change_multiple_column_values(board_id: $boardId, item_id: $itemId, column_values: $cv) {
    id column_values(ids: ["<status_col>", "<agent_col>"]) { id text }
  }
}
```

Status change, ownership change, and adding a link are all this one call — batch them into a
single `cv` rather than firing three mutations.

Asking for `column_values` back in the response is worth it: it confirms the status actually
landed on the label you intended, instead of you assuming it did.

### Moving a card to a different project

Two things must change together, or the board contradicts itself — the Project column and the
group. `move_item_to_group` does not touch columns, and `change_multiple_column_values` does not
touch groups, so do both in one serial mutation:

```graphql
mutation ($boardId: ID!, $itemId: ID!, $cv: JSON!) {
  mv:  move_item_to_group(item_id: $itemId, group_id: "<new_group_id>") { id group { title } }
  upd: change_multiple_column_values(board_id: $boardId, item_id: $itemId,
                                     column_values: $cv, create_labels_if_missing: true) { id }
  rm:  delete_group(board_id: $boardId, group_id: "<old_group_id>") { id }
}
```

Create the destination group first if the project is new — you need its id for the move.

Only include the `delete_group` alias if the old group is now **empty**. Deleting a group deletes
every card still in it, which is a silent way to destroy work: check the group's item count before
adding that alias, and leave it out if you are unsure.

`Details` is a single field, so writing it **replaces** it. To add information without
destroying the context a future agent needs, post an update (operation 4) instead.

## 3. Complete a task

Set `Status` to `Done` only when the work is finished and you verified it, and post an
update saying what you verified and how. Otherwise set `Blocked` and post the blocker.

`Done` is wired to Monday's completion tracking (the status column's `done_colors` points at
the Done label), so it feeds progress indicators and board views. A card marked Done that
isn't done doesn't just mislead a reader — it drops out of the views the user scans, and the
work silently disappears.

## 4. Post an update (progress log)

The MCP tool works here, no GraphQL needed:

`create_update` with `itemId` and `body`. Body supports basic HTML, so `<br>` for line
breaks and `<b>` for emphasis if a log entry needs structure.

Updates are append-only and never clobber a column, which makes them the safe place for
anything evolving: PR links as they appear, test results, why the plan changed, the actual
error text when something fails.

To read the history back — do this before picking up a card, since it is where a previous
attempt recorded why it stopped:

```graphql
query ($itemId: ID!) {
  items(ids: [$itemId]) {
    id name url
    column_values { id text }
    updates(limit: 50) { id body created_at creator { name } }
  }
}
```

## 5. Board view

```graphql
query ($boardId: ID!) {
  boards(ids: [$boardId]) {
    name url
    groups { id title }
    items_page(limit: 100) {
      items {
        id name url updated_at
        group { title }
        column_values(ids: ["<project_col>", "<status_col>", "<agent_col>", "<link_col>"]) { id text }
        updates(limit: 1) { body created_at }
      }
    }
  }
}
```

Select `updates(limit: 1)` in this same query. The board view has to show a blocker reason on
every Blocked row, and that reason lives in the latest update — fetching it here avoids a second
round trip just to explain the Blocked cards. One update per card is enough for the summary
view; read the fuller history only when picking a card up.

`column_values` returns a flat list in arbitrary order, so match on `id` rather than
position — the order is not stable and index-based reads will silently mismatch columns.

Link columns come back as text in the form `PR #42 - https://github.com/...`.

To pull only live work on a busy board, filter by status:

```graphql
items_page(limit: 100, query_params: {rules: [{column_id: "<status_col>", compare_value: ["To Do", "In Progress", "Blocked"], operator: any_of}]})
```

## Board views cannot be created from the API

`create_view` exists, but its `ViewKind` enum offers only `DASHBOARD`, `TABLE`, `FORM`, and
`APP` — there is no `KANBAN`. So a Kanban view has to be added once in the Monday UI, choosing
whether it groups by the Project dropdown or the Status column. Both views can coexist; the
board data supports either, and nothing in this skill depends on which views exist.

If the user asks for a Kanban view, say plainly that it is a UI action and describe it (add a
view, pick Kanban, set "group by" to Project or Status) rather than attempting API calls that
cannot work.

## Status labels are effectively immutable — don't fight them

`change_column_metadata` only accepts `title` and `description` (verified via schema
introspection); there is no mutation for editing status labels. Changing the label set means
deleting and recreating the column, which discards every card's status value.

So treat the four labels as fixed. If the user wants a different set, say that it means
recreating the column and losing current statuses, and let them decide — or point them at
the Monday UI, where renaming a label takes seconds and is non-destructive.

Two related quirks, in case you ever recreate the column:

- The MCP `create_column` tool rejects Monday's documented `defaults` format. It demands
  `labels` as an array of objects with an integer `color`. Going through `all_monday_api`
  with `defaults` as a stringified `{"labels": {"0": "...", ...}}` map works, and is the
  documented Monday shape.
- `done_colors` is pinned to label index `1` no matter what you pass. That is why `Done`
  sits at index 1, with `labels_positions_v2` used to get the display order right. Put a
  non-final label at index 1 and Monday will treat in-flight work as complete.
