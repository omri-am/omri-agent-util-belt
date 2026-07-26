# Design: Agent Run History

Status: draft
Author: a.dev

## Problem

We run a lot of agents and have no durable record of what any of them did. When someone asks
"why did the bot say that" or "did we already try this", the only answer is to dig through Slack
scrollback. Logs exist but are per-request and expire after 14 days, so they cannot answer
questions about a run as a unit.

## Goal

Persist one record per agent run, and expose enough of it to answer three questions:

1. What runs happened for a given channel or user, most recent first?
2. For one run, what did the agent actually do — tools called, model, outcome?
3. Which runs failed, and why?

Out of scope for v1: any UI. This is an API plus storage. A dashboard may come later but should
not shape the schema now.

## Storage

New table `agent_runs`, one row per run:

- `run_id` (uuid, pk)
- `channel_id`, `user_hash` — never the raw user id, reuse the existing hashing helper
- `started_at`, `finished_at`
- `outcome` enum: `ok`, `error`, `refused`, `timeout`
- `model` — the resolved model id, not the alias
- `tool_calls` (jsonb) — name, duration, and whether it errored. **No tool arguments**, since
  those can contain user content.
- `error_code` (nullable)

Retention: 90 days, enforced by a nightly job. We deliberately keep this longer than the 14-day
log retention because that gap is the reason this exists.

Index on `(channel_id, started_at desc)` for question 1, and on `(outcome, started_at desc)`
for question 3.

## API

Three read endpoints, all behind the existing admin token guard:

- `GET /runs?channel_id=&limit=&cursor=` — cursor pagination, newest first
- `GET /runs/{run_id}` — the full record
- `GET /runs/failures?since=` — failures only

Writes are internal: the orchestrator emits a record at the end of every run. It must be
fire-and-forget — a storage failure must never fail the user's request, only log a warning.

## Migration and rollout

The table needs to exist before the orchestrator writes to it, obviously. Roll out behind a
config flag `agent-run-history-enabled` so we can turn it off if write latency shows up in the
p99. Backfill is not possible and not wanted.

## Open questions

- Should `tool_calls` be a separate table instead of jsonb? Leaning jsonb for v1 since we never
  query inside it, but this is the decision most likely to be wrong.
- Do we need per-channel retention overrides? Nobody has asked, so assume no.

## Notes

We should probably tidy up the config-loading code at some point, it has grown organically.
