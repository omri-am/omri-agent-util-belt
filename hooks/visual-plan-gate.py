#!/usr/bin/env python3
"""PreToolUse gate on ExitPlanMode.

If sentinel /tmp/visual-plan-ready exists -> consume it and allow.
Otherwise deny with instructions to run the visual-plan skill first.
"""
import json
import sys
import os

SENTINEL = "/tmp/visual-plan-ready"


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def allow():
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        allow()
        return
    if data.get("tool_name") != "ExitPlanMode":
        allow()
        return
    if os.path.exists(SENTINEL):
        current_session = data.get("session_id", "")
        sentinel_session = ""
        try:
            with open(SENTINEL) as f:
                sentinel_session = f.readline().strip()
        except OSError:
            pass
        if sentinel_session and sentinel_session == current_session:
            try:
                os.remove(SENTINEL)
            except OSError:
                pass
            allow()
            return
        # Stale sentinel from another session — remove and fall through to deny.
        try:
            os.remove(SENTINEL)
        except OSError:
            pass
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    render_path = (
        f"{plugin_root}/skills/visual-plan/scripts/render_plan.py"
        if plugin_root
        else "<plugin>/skills/visual-plan/scripts/render_plan.py"
    )
    deny(
        "Before calling ExitPlanMode, render the plan visually via the visual-plan skill. "
        "Steps: (1) build plan JSON per the visual-plan SKILL.md schema, "
        "(2) write to /tmp/plan.json, "
        f"(3) run `python3 \"{render_path}\" /tmp/plan.json` "
        "(this opens the page in the browser AND drops a sentinel that clears this gate), "
        "(4) tell user to review + paste back APPROVED/REJECTED/MODIFY decision, "
        "(5) re-call ExitPlanMode only after user has reviewed. "
        "If user already said 'skip visual' or 'no html' this turn, write the sentinel manually: "
        "`echo \"$CLAUDE_CODE_SESSION_ID\" > /tmp/visual-plan-ready` then re-call ExitPlanMode."
    )


if __name__ == "__main__":
    main()
