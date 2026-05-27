# omri-agent-util-belt

Personal cross-tool agent toolkit. Skills, hooks, commands, and scripts that I want available in every repo I work on.

Claude Code is the primary target (plugin format). Skills are portable to Codex / Gemini via manual copy or the `sync-user-skills` skill.

## What's inside

### Skills (`skills/`)

| Skill | What |
|-------|------|
| `visual-plan` | Renders plan-mode output as an interactive HTML page with clickable simulation, alternative paths, and per-step approve/reject controls. Auto-fires before `ExitPlanMode` via the bundled hook. |
| `create-pr` | Open a PR (GitHub CLI workflow). Generates branch name from path, drafts commit + PR description from the diff. |

### Hooks (`hooks/`)

| Hook | Event | Purpose |
|------|-------|---------|
| `visual-plan-gate.py` | `PreToolUse` / `ExitPlanMode` | Blocks `ExitPlanMode` until `visual-plan` has rendered the plan to HTML and the user has reviewed. Sentinel file `/tmp/visual-plan-ready` clears the gate. |

### Commands (`commands/`)

| Command | What |
|---------|------|
| `/monitor-pr` | Background-polls a PR's CI status and notifies on completion. |

### Scripts (`scripts/`)

Shell utilities the commands and hooks shell out to.

- `monitor-pr.sh` — backs `/monitor-pr`
- `review-pr-background.sh` — kicks off a PR review in a detached process

### Memory (`memory/`)

Reference copies of `~/.claude/CLAUDE.md` and `~/.claude/RTK.md`. **Not auto-loaded** by the plugin. Copy or symlink manually if you want them on a new machine.

## Install

### Claude Code (any project)

Add to `.claude/settings.json` in the target repo (or `~/.claude/settings.json` for global):

```json
{
  "extraKnownMarketplaces": {
    "omri-util-belt": {
      "source": {
        "source": "github",
        "repo": "<your-gh-user>/omri-agent-util-belt"
      }
    }
  },
  "enabledPlugins": {
    "omri-agent-util-belt@omri-util-belt": true
  }
}
```

Restart Claude Code. The plugin is installed on first launch.

### Manual one-time install

```
/plugin marketplace add <your-gh-user>/omri-agent-util-belt
/plugin install omri-agent-util-belt@omri-util-belt
```

### Codex / Gemini

Skills in `skills/` are SKILL.md format and portable. Either:

- Symlink the dirs into `~/.codex/skills/` / `~/.gemini/skills/`
- Or use the `sync-user-skills` skill (Claude side) to mirror automatically

Hooks and commands are Claude-specific — no cross-tool path.

## Development

To edit a skill and test locally without re-installing:

```bash
# point the local Claude plugin cache at this checkout
ln -sf "$(pwd)" "$HOME/.claude/plugins/cache/marketplaces/omri-util-belt/omri-agent-util-belt"
```

Then `/plugin reload` (or restart) picks up changes.

### Leak-scan gate (one-time per clone)

```bash
git config core.hooksPath .githooks   # activate versioned pre-commit
brew install gitleaks                 # optional but recommended (fallback is grep)
```

Pattern list lives in `.gitleaks.toml`. CI runs the same scan on every push/PR via `.github/workflows/leak-scan.yml`.

## Layout

```
.claude-plugin/
  marketplace.json    # catalog
  plugin.json         # plugin manifest
skills/               # auto-loaded as plugin skills
hooks/
  hooks.json          # registered with Claude Code
  *.py                # hook scripts (use $CLAUDE_PLUGIN_ROOT)
commands/             # slash commands
scripts/              # plain shell utilities (called by commands/hooks)
memory/               # reference CLAUDE.md / RTK.md (not auto-loaded)
```
