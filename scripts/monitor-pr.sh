#!/bin/bash
# monitor-pr.sh - Background PR CI monitor
# Spawned after PR creation. Polls CI status every 10 minutes.
# When checks fail, invokes `claude -p` to diagnose and fix (up to 3 attempts).
#
# Usage: monitor-pr.sh <project-dir> [max-fix-attempts] [check-interval-seconds]

set -euo pipefail

PROJECT_DIR="${1:-.}"
MAX_FIX_ATTEMPTS="${2:-3}"
CHECK_INTERVAL="${3:-600}"
FIX_COUNT=0
LOG_FILE="${PROJECT_DIR}/.claude-pr-monitor.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

cd "$PROJECT_DIR" || { log "ERROR: Cannot cd to $PROJECT_DIR"; exit 1; }

# Get PR info
PR_NUMBER=$(gh pr view --json number -q .number 2>/dev/null || true)
if [ -z "$PR_NUMBER" ]; then
  log "No PR found on current branch. Exiting."
  exit 1
fi

# Single-instance guard: only one monitor per PR. mkdir is atomic across processes.
LOCK_DIR="${PROJECT_DIR}/.claude-pr-monitor-${PR_NUMBER}.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "Another monitor is already running for PR #$PR_NUMBER (lock: $LOCK_DIR). Exiting."
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

BRANCH=$(git rev-parse --abbrev-ref HEAD)
log "Started monitoring PR #$PR_NUMBER (branch: $BRANCH, max fixes: $MAX_FIX_ATTEMPTS, interval: ${CHECK_INTERVAL}s)"

FIRST=1
while true; do
  # Check immediately on the first pass; sleep between subsequent checks.
  if [ "$FIRST" -eq 1 ]; then
    FIRST=0
  else
    log "Sleeping ${CHECK_INTERVAL}s before next check..."
    sleep "$CHECK_INTERVAL"
  fi

  # Re-check that the PR still exists and is open
  PR_STATE=$(gh pr view --json state -q .state 2>/dev/null || true)
  if [ "$PR_STATE" != "OPEN" ]; then
    log "PR is no longer open (state: $PR_STATE). Stopping monitor."
    exit 0
  fi

  # Check CI status (human-readable, for logs + the fixer prompt)
  CHECKS_OUTPUT=$(gh pr checks "$PR_NUMBER" 2>&1 || true)
  log "Checks output:\n$CHECKS_OUTPUT"

  # Count states from the structured `bucket` enum (pass|fail|pending|skipping|cancel)
  # via gh's built-in jq engine — avoids false matches on check names/URLs.
  COUNTS=$(gh pr checks "$PR_NUMBER" --json bucket -q \
    '"\([.[]|select(.bucket=="fail")]|length) \([.[]|select(.bucket=="pass")]|length) \([.[]|select(.bucket=="pending")]|length)"' \
    2>/dev/null || true)
  read -r FAIL_COUNT PASS_COUNT PENDING_COUNT <<< "${COUNTS:-0 0 0}"
  FAIL_COUNT=${FAIL_COUNT:-0}; PASS_COUNT=${PASS_COUNT:-0}; PENDING_COUNT=${PENDING_COUNT:-0}

  if [ "$FAIL_COUNT" -eq 0 ] && [ "$PASS_COUNT" -gt 0 ] && [ "$PENDING_COUNT" -eq 0 ]; then
    log "All checks passed! Monitoring complete."
    exit 0
  fi

  if [ "$FAIL_COUNT" -eq 0 ]; then
    log "No failures yet ($PENDING_COUNT checks still running). Continuing to wait..."
    continue
  fi

  # We have failures
  if [ "$FIX_COUNT" -ge "$MAX_FIX_ATTEMPTS" ]; then
    log "Reached max fix attempts ($MAX_FIX_ATTEMPTS). Stopping monitor."
    exit 1
  fi

  FIX_COUNT=$((FIX_COUNT + 1))
  log "CI failure detected. Fix attempt $FIX_COUNT/$MAX_FIX_ATTEMPTS"

  # Gather failure details for Claude
  FAILED_CHECKS_JSON=$(gh pr checks --json name,state,link 2>/dev/null || echo "[]")

  # Get failed run IDs
  FAILED_RUN_IDS=$(gh run list --branch "$BRANCH" --status failure --json databaseId -q '.[].databaseId' 2>/dev/null | head -3 || true)

  PROMPT=$(cat <<PROMPT_EOF
You are an autonomous CI fixer for PR #$PR_NUMBER on branch "$BRANCH".

## Current CI status:
$CHECKS_OUTPUT

## Failed checks (JSON):
$FAILED_CHECKS_JSON

## Failed run IDs (use with 'gh run view <id> --log-failed'):
$FAILED_RUN_IDS

This is fix attempt $FIX_COUNT of $MAX_FIX_ATTEMPTS. Each attempt runs in a FRESH session
with no memory of earlier ones — the ONLY record of prior attempts is on the PR itself.

## Your task:
1. FIRST, review what has already been tried so you do not repeat it:
   - Read prior automated fix-attempt comments: 'gh pr view $PR_NUMBER --comments'
   - Read recent fix commits on this branch: 'git log --oneline -10'
2. Read the failure logs: run 'gh run view <run-id> --log-failed' for each failed run ID above
3. Analyze the root cause. If the failure matches a fix already attempted (per step 1), do NOT repeat it —
   output exactly "CANNOT_FIX: prior fix '<summary>' did not resolve this" and stop.
4. If you CLEARLY understand the issue AND it differs from prior attempts: make a minimal fix, then run:
   git add <specific-files> && git commit -m "fix: <description>" && git push
   Then record this attempt as a PR comment so the next session can see it:
   gh pr comment $PR_NUMBER --body "🤖 CI fix attempt $FIX_COUNT/$MAX_FIX_ATTEMPTS — diagnosis: <root cause>. Changed: <files>."
5. If you CANNOT read the logs or CANNOT understand the error: output exactly "CANNOT_FIX: <reason>" and stop.

## Rules:
- Only fix what the CI error points to. Do NOT touch unrelated code.
- Do NOT retry a fix already recorded in the PR comments or commit log from step 1.
- Be surgical and minimal.
PROMPT_EOF
  )

  log "Invoking Claude to diagnose and fix..."
  CLAUDE_OUTPUT=$(claude -p "$PROMPT" --verbose 2>&1 || true)
  log "Claude output:\n$CLAUDE_OUTPUT"

  if echo "$CLAUDE_OUTPUT" | grep -q "CANNOT_FIX"; then
    log "Claude could not fix the issue. Stopping monitor."
    exit 1
  fi

  log "Fix attempt $FIX_COUNT complete. Will re-check after next interval."
done
