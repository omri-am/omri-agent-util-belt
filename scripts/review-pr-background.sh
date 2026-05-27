#!/bin/bash
# review-pr-background.sh - Background PR reviewer
# Spawns claude -p to review a PR and post inline comments via gh api.
#
# Usage: review-pr-background.sh <project-dir>
# Launched automatically by /create-pr after PR creation.
# Logs output to <project-dir>/.claude-pr-review.log

set -euo pipefail

PROJECT_DIR="${1:-.}"
LOG_FILE="${PROJECT_DIR}/.claude-pr-review.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

cd "$PROJECT_DIR" || { log "ERROR: Cannot cd to $PROJECT_DIR"; exit 1; }

log "=========================================="
log "PR review started"

# Resolve PR number and repo
PR_NUMBER=$(gh pr view --json number -q .number 2>/dev/null || true)
if [ -z "$PR_NUMBER" ]; then
  log "ERROR: No PR found on current branch. Exiting."
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
if [ -z "$REPO" ]; then
  log "ERROR: Could not determine repo. Exiting."
  exit 1
fi

log "Reviewing PR #$PR_NUMBER in $REPO"

# Get the diff (truncated to ~100K chars to fit in context)
DIFF=$(gh pr diff "$PR_NUMBER" 2>/dev/null | head -c 100000)
if [ -z "$DIFF" ]; then
  log "ERROR: Empty diff. Exiting."
  exit 1
fi

DIFF_SIZE=${#DIFF}
log "Diff size: $DIFF_SIZE chars"

# Build the prompt using a temp file to avoid argument length limits
PROMPT_FILE=$(mktemp)
trap 'rm -f "$PROMPT_FILE"' EXIT

cat > "$PROMPT_FILE" <<PROMPT_EOF
You are a code reviewer. You have been given a PR diff to review.

## Your task:
1. Read the diff below carefully
2. If you need more context on any file, use Read to read the full file
3. Identify issues: bugs, logic errors, missing edge cases, style problems, security concerns
4. Post your review as inline PR comments at the specific lines where issues exist

## How to post the review:

Use this EXACT gh api command format to submit a review with inline comments:

gh api repos/${REPO}/pulls/${PR_NUMBER}/reviews \\
  -X POST \\
  -f event=COMMENT \\
  -f body="<short summary of findings>" \\
  --input <json-file>

Create a temporary JSON file with the comments array. The JSON structure is:
{
  "comments": [
    {"path": "relative/file/path.scala", "line": 42, "body": "Issue description and suggestion"}
  ]
}

Alternatively, if there are 3 or fewer comments, you can use this simpler format:
gh api repos/${REPO}/pulls/${PR_NUMBER}/reviews \\
  -X POST \\
  -f event=COMMENT \\
  -f body="<summary>" \\
  -f 'comments=[{"path":"file.scala","line":42,"body":"Issue description"}]'

## Rules:
- Only comment on lines that are IN the diff (changed/added lines, the + lines)
- The "line" field must be the line number shown on the RIGHT side of the diff (the new file)
- Be specific and actionable - explain what is wrong and suggest a fix
- Do NOT comment on trivial style issues (spacing, import order, formatting)
- Focus on: bugs, logic errors, missing edge cases, security, performance
- If the PR looks clean, submit a review with just a body and no inline comments:
  gh api repos/${REPO}/pulls/${PR_NUMBER}/reviews -X POST -f event=COMMENT -f body="LGTM - no issues found"
- Keep each comment concise (2-4 sentences max)
- Do NOT use position field, use line field only

## Diff:
\`\`\`diff
${DIFF}
\`\`\`
PROMPT_EOF

log "Prompt file created: $PROMPT_FILE ($(wc -c < "$PROMPT_FILE") bytes)"
log "Invoking claude -p..."

# Run claude in non-interactive mode with tool access
claude -p "$(cat "$PROMPT_FILE")" \
  --allowedTools "Bash(gh:*)" "Bash(cat:*)" "Bash(mktemp:*)" "Bash(rm:*)" "Read" "Glob" "Grep" \
  >> "$LOG_FILE" 2>&1 || {
  log "ERROR: claude -p exited with code $?"
  exit 1
}

log "PR review complete"
log "=========================================="
