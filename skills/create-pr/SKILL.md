---
name: create-pr
description: Open a PR (GitHub CLI Workflow)
---

# Open a PR (GitHub CLI Workflow)

- Check if the current branch is `master`, `main`, or `prod`. If so:
  - Get the username from git/GitHub, not the filesystem path: `gh api user -q .login` (fall back to `git config user.name` if `gh` is unavailable)
  - Check the diff to understand changes
  - Generate a branch name from changes (format: `$USERNAME/<feature-name>`)
  - Create and checkout the branch: `git checkout -b $USERNAME/<branch-name>`

- Check the diff between the current branch and the default branch (`master` or `main`)
- If there is unstaged or staged work that hasn't been committed:
  - Generate a commit message based on the changes
  - Stage only the files relevant to this change — list them explicitly. Do NOT use `git add .` (it sweeps in unrelated/untracked files).
  - Execute the following chained command to Commit and Push in one step:
    `GIT_EDITOR=true git add <changed-file> [<changed-file> ...] && GIT_EDITOR=true git commit -m "<generated_message>" && git push -u origin HEAD`

- Generate the PR details based on the diff using this format:
  - **Title**: `<feature_area>: <Title>` (80 chars or less)
  - **Body**:
    ```markdown
    <TLDR> (Max 2 sentences)

    <Description>
    - 1~3 bullet points explaining changes
    ```

- Create the PR and capture the URL using `gh`:
  `gh pr create --title "<generated_title>" --body "<generated_body>"`

- If the command succeeds:
  - Retrieve the URL explicitly to ensure accuracy: `gh pr view --json url -q .url`
  - Display the link on its own line: `https://github.com/...`

- If the user mentions "skip review", "#skipreview", or "skipreview" in the prompt:
  - Immediately post the comment to the newly created PR:
    `gh pr comment --body "#skipreview"`

- After the PR is successfully created, launch the background CI monitor:
  `nohup "$CLAUDE_PLUGIN_ROOT/scripts/monitor-pr.sh" "$(pwd)" 3 600 > /dev/null 2>&1 & disown`
  - Inform the user: "Background CI monitor started. It will check every 10 minutes and attempt up to 3 fixes. Check `.claude-pr-monitor.log` for status."

- After the PR is created, invoke the `review` skill (built-in `/review` command) to run a code review on the new PR's diff.
  - Collect the review findings into a single Markdown summary. Format:
    ```markdown
    ## 🤖 Automated Code Review

    <one-line summary of overall assessment>

    ### Findings
    - **<severity>** `<file>:<line>` — <issue>. <suggested fix>

    _If no issues found, state: "No blocking issues found."_
    ```
  - Write the summary to a temp file and post it as a comment on the PR (avoids shell-quoting issues with multi-line Markdown):
    ```bash
    gh pr comment --body-file <(cat <<'EOF'
    <generated_review_summary>
    EOF
    )
    ```
    - Alternatively, write the summary to a temp file (e.g. `/tmp/pr-review-$$.md`) and run `gh pr comment --body-file /tmp/pr-review-$$.md`.
  - Confirm the comment posted, then display the PR URL again so the user can open the findings on the GitHub PR page.
