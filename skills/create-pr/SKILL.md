---
name: create-pr
description: Open a PR (GitHub CLI Workflow)
---

# Open a PR (GitHub CLI Workflow)

## Phase 0 — Preflight (abort before mutating anything)

Run these checks first. Each catches a failure that otherwise surfaces only *after* you've committed and pushed.

- **Default branch**: `DEFAULT=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')`. Fall back to `main` if empty.
- **Anything to ship?** Check commits ahead of base *and* working-tree changes:
  `git rev-list --count origin/$DEFAULT..HEAD` and `git status --porcelain`. If both are empty → stop and tell the user "nothing to PR."
- **Account vs repo (multi-account footgun)**: compare the active `gh` account to the repo owner —
  `gh api user -q .login` vs `gh repo view --json owner -q .owner.login`. If they differ and the user isn't a known collaborator, the later `gh pr create` will fail with "must be a collaborator." Note this now and plan to fall back to the browser compare URL (Phase 3).
- **Existing PR?** `gh pr view --json url -q .url 2>/dev/null`. If one already exists for this branch, push any new commits and stop — do not re-create.

## Phase 1 — Branch

Determine the branch name. It must be **meaningful** — derived from the actual changes, never an auto-generated/random slug (e.g. `cheerful-tablecloth`, `galvanized-mandolin`).

- Get the username from git/GitHub, not the filesystem path: `gh api user -q .login` (fall back to `git config user.name` if `gh` is unavailable).
- Inspect the diff and pick a short kebab-case `<feature-name>` describing what changed (e.g. `worktree-remote-diff`, `fix-token-expiry`). Format: `$USERNAME/<feature-name>`.
- **If current branch is `master`, `main`, or `prod`**: create and checkout the new branch: `git checkout -b $USERNAME/<feature-name>`.
- **If current branch is an auto-generated/random name** (common in worktrees): rename it in place: `git branch -m $USERNAME/<feature-name>`.
- **Otherwise** (branch already has a clear, intentional name): keep it as-is.

## Phase 2 — Commit & push

Determine the base ref to diff against:

- Detect a linked worktree: `[ "$(git rev-parse --git-dir)" != "$(git rev-parse --git-common-dir)" ]` is true inside a worktree.
- **If inside a worktree**: the local default branch may be stale, so diff against the remote. Fetch first, then use the remote tracking ref:
  `git fetch origin "$DEFAULT" && git diff origin/$DEFAULT...HEAD`
- **Otherwise**: diff against the local default branch: `git diff $DEFAULT...HEAD`

If there is unstaged or staged work that hasn't been committed:

- Generate a commit message based on the changes.
- Stage only the files relevant to this change — list them explicitly. Do NOT use `git add .` (it sweeps in unrelated/untracked files).
- Commit and push in one step:
  `GIT_EDITOR=true git add <changed-file> [<changed-file> ...] && GIT_EDITOR=true git commit -m "<generated_message>" && git push -u origin HEAD`

## Phase 3 — Create PR

Generate the PR details based on the diff:

- **Title**: `<feature_area>: <Title>` (80 chars or less)
- **Body**:
  ```markdown
  <TLDR> (Max 2 sentences)

  <Description>
  - 1~3 bullet points explaining changes
  ```

Create the PR, passing the base explicitly:

`gh pr create --base "$DEFAULT" --title "<generated_title>" --body "<generated_body>"`

- **On success**:
  - Retrieve the URL explicitly to ensure accuracy: `gh pr view --json url -q .url`
  - Display the link on its own line: `https://github.com/...`
- **On failure** (e.g. "must be a collaborator", auth): do NOT retry blindly and do NOT launch the monitor. Print the manual compare URL on its own line so the user can open the PR in a browser where they're logged in as the repo owner:
  `https://github.com/<owner>/<repo>/compare/<DEFAULT>...<branch>?expand=1`
  Also offer: `gh auth login` as the repo owner, then re-run this skill.

## Phase 4 — Post-create (only if Phase 3 succeeded)

- If the user mentions "skip review", "#skipreview", or "skipreview" in the prompt, immediately comment on the new PR:
  `gh pr comment --body "#skipreview"`

- **Background CI monitor — opt-in only.** It invokes `claude -p` to commit and push fixes to the PR branch unattended, up to 3 times. Launch it *only* if the user explicitly asked for autonomous CI-fixing. If launched:
  `nohup "$CLAUDE_PLUGIN_ROOT/scripts/monitor-pr.sh" "$(pwd)" 3 600 > /dev/null 2>&1 & disown`
  - Inform the user: "Background CI monitor started. It will check every 10 minutes and attempt up to 3 fixes. Check `.claude-pr-monitor.log` for status."

- Invoke the `review` skill (built-in `/review` command) to run a code review on the new PR's diff.
  - Collect the review findings into a single Markdown summary. Format:
    ```markdown
    ## 🤖 Automated Code Review

    <one-line summary of overall assessment>

    ### Findings
    - **<severity>** `<file>:<line>` — <issue>. <suggested fix>

    _If no issues found, state: "No blocking issues found."_
    ```
  - Write the summary to a temp file and post it as a comment (avoids shell-quoting issues with multi-line Markdown):
    ```bash
    gh pr comment --body-file <(cat <<'EOF'
    <generated_review_summary>
    EOF
    )
    ```
    - Alternatively, write the summary to `/tmp/pr-review-$$.md` and run `gh pr comment --body-file /tmp/pr-review-$$.md`.
  - Confirm the comment posted, then display the PR URL again so the user can open the findings on the GitHub PR page.
