# Monitor PR CI Status

Launch a background process that monitors the current branch's PR for CI failures and autonomously attempts fixes.

## How it works

This skill spawns an **independent background process** that survives even if this Claude session moves on to other work or is closed. The background process:
1. Polls `gh pr checks` every 10 minutes
2. When failures are detected, invokes `claude -p` (a fresh non-interactive Claude session) to diagnose and fix
3. Stops after 3 fix attempts, or when all checks pass, or if it can't understand the error

## To start monitoring

Run this command to launch the background monitor:

```
nohup "$CLAUDE_PLUGIN_ROOT/scripts/monitor-pr.sh" "$(pwd)" 3 600 > /dev/null 2>&1 & disown
```

Then inform the user: "Background CI monitor started. It will check every 10 minutes and attempt up to 3 fixes. Logs are in `.claude-pr-monitor.log`."

## To check monitor status

- View the log: `tail -20 .claude-pr-monitor.log`
- Check if still running: `ps aux | grep monitor-pr.sh | grep -v grep`

## To stop monitoring

- `pkill -f monitor-pr.sh`
