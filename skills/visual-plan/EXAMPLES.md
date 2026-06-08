# Examples

## State-evolution plan (the centerpiece)

This is the shape to reach for by default. Declare the **entities** the plan touches, their **current** state, and what each step **changes** — the renderer turns it into a timeline the reviewer scrubs from `Now` to `Done`, watching entities appear / change / disappear. Conceptual phrases only, never code.

```json
{
  "title": "Add auth rate limiting",
  "summary": "Today any client can hammer /login forever — credential stuffing is wide open.",
  "outcome": "Repeated attempts get throttled with a 429; legit users are unaffected.",
  "entities": [
    {"id": "client",  "label": "Client / attacker", "kind": "actor"},
    {"id": "login",   "label": "Login endpoint",    "kind": "endpoint"},
    {"id": "counter", "label": "Attempt counter",   "kind": "datastore"},
    {"id": "page",    "label": "Throttled page",    "kind": "ui"}
  ],
  "current": {
    "client":  {"present": true,  "state": "unlimited login attempts"},
    "login":   {"present": true,  "state": "verifies password, no limit"},
    "counter": {"present": false},
    "page":    {"present": false}
  },
  "steps": [
    {
      "id": "1", "title": "Add attempt counter",
      "detail": "A per-IP counter with a sliding TTL window.",
      "changes": [{"entity": "counter", "op": "add", "state": "per-IP count, 15-min window"}]
    },
    {
      "id": "2", "title": "Guard the login endpoint",
      "detail": "Login checks the counter before verifying the password.",
      "depends_on": ["1"],
      "changes": [
        {"entity": "login",  "op": "modify", "state": "checks counter, 429 if over limit"},
        {"entity": "client", "op": "modify", "state": "blocked after 5 tries"}
      ]
    },
    {
      "id": "3", "title": "Throttled page", "optional": true,
      "detail": "Friendly retry-after screen instead of a raw error.",
      "depends_on": ["2"],
      "changes": [{"entity": "page", "op": "add", "state": "shows retry-after countdown"}]
    }
  ],
  "future": {
    "login":  {"state": "throttled, then verifies"},
    "client": {"state": "rate-limited"}
  }
}
```

The timeline the reviewer scrubs (each frame, what's present + what just changed):

```
 Now      client · login                         "…credential stuffing is wide open."
 Step 1   + counter            (NEW)             "A per-IP counter with a sliding TTL window."
 Step 2   ~ login  ~ client    (CHANGED)         "Login checks the counter before verifying."
 Step 3   + page               (NEW, optional)   "Friendly retry-after screen…"
 Done     client · login · counter · page        "…throttled with a 429; legit users unaffected."
```

Entities that aren't touched at a given step sit quiet; the one(s) a step changes light up green (add) / amber (modify) / red (remove). The reviewer *sees* the system fill in, not reads a list.

## Minimal plan (no alternatives, no simulation)

```json
{
  "title": "Add dark mode toggle",
  "summary": "User wants light/dark switching via prefers-color-scheme with manual override.",
  "steps": [
    {
      "id": "1",
      "title": "Add CSS variables for theme tokens",
      "detail": "Define --bg, --fg, --accent for both themes in a single :root + [data-theme=dark] block.",
      "files": ["src/styles/theme.css"]
    },
    {
      "id": "2",
      "title": "Toggle component in header",
      "detail": "Button writes data-theme attribute on <html>, persists choice in localStorage.",
      "files": ["src/components/Header.tsx"]
    },
    {
      "id": "3",
      "title": "Respect system preference on first load",
      "detail": "If no stored choice, read prefers-color-scheme. Listen for OS changes while unset.",
      "files": ["src/lib/theme.ts"],
      "optional": true
    }
  ]
}
```

## Full plan with alternatives + simulation

```json
{
  "title": "RSVP form for wedding site",
  "summary": "Guests confirm attendance + dietary needs. Submit goes to Google Sheets.",
  "steps": [
    {
      "id": "1",
      "title": "Build form UI",
      "detail": "Name, attending y/n, +1, dietary notes textarea.",
      "files": ["src/RSVPForm.tsx"]
    },
    {
      "id": "2",
      "title": "Wire submit to Google Apps Script webhook",
      "detail": "POST JSON to deployed Apps Script URL. Sheet appends a row.",
      "files": ["src/lib/rsvp-api.ts"]
    },
    {
      "id": "3",
      "title": "Confirmation screen",
      "detail": "Replace form with thank-you on success.",
      "files": ["src/RSVPForm.tsx"]
    }
  ],
  "alternatives": [
    {
      "name": "Use hosted form builder",
      "tradeoffs": "Zero code, but locked to vendor styling. Picks up edits faster, less control.",
      "steps": ["Drop form widget on page", "Map fields to sheet via automation flow"]
    },
    {
      "name": "Custom backend (Cloudflare Worker)",
      "tradeoffs": "Best for spam protection and validation. Adds deploy step.",
      "steps": ["Worker accepts POST", "Worker writes to Sheets API", "Add Turnstile captcha"]
    }
  ],
  "simulation": {
    "start": "form",
    "screens": [
      {
        "id": "form",
        "title": "RSVP form (default state)",
        "body_html": "<div style='padding:12px;'><input placeholder='Your name' style='display:block;margin-bottom:8px;padding:6px;width:100%;'><div style='margin-bottom:8px;'><label><input type=radio name=att> Attending</label> <label style='margin-left:8px;'><input type=radio name=att> Can't make it</label></div><textarea placeholder='Dietary notes' style='width:100%;padding:6px;'></textarea></div>",
        "actions": [
          {"label": "Submit", "next": "loading"}
        ]
      },
      {
        "id": "loading",
        "title": "Submitting...",
        "body_html": "<div style='padding:24px;text-align:center;color:#888;'>⏳ Sending RSVP</div>",
        "actions": [
          {"label": "(simulate success)", "next": "done"}
        ]
      },
      {
        "id": "done",
        "title": "Confirmation",
        "body_html": "<div style='padding:24px;text-align:center;'><div style='font-size:32px;'>🎉</div><div>Thanks! See you there.</div></div>",
        "actions": []
      }
    ]
  }
}
```

## Plan with a dependency graph (fan-out + converge) + before/after

Use `depends_on` when steps aren't a straight line — here one setup step feeds two parallel steps that later converge. The renderer draws this as a diamond instead of a flat list, and `before`/`after` show the actual change on the steps where it matters.

```json
{
  "title": "Add auth rate limiting",
  "summary": "Throttle login + reset attempts to stop credential stuffing.",
  "steps": [
    {
      "id": "1",
      "title": "Add Redis attempt counter",
      "detail": "Per-IP counter with sliding TTL window.",
      "files": ["src/lib/ratelimit.ts"]
    },
    {
      "id": "2",
      "title": "Guard the login handler",
      "detail": "Check + increment before verifying the password.",
      "files": ["src/routes/login.ts"],
      "depends_on": ["1"],
      "before": "POST /login\n  -> verifyPassword(body)",
      "after": "POST /login\n  -> rateLimit.check(ip)   // 429 if over\n  -> verifyPassword(body)"
    },
    {
      "id": "3",
      "title": "Guard the password-reset handler",
      "detail": "Same counter, shared key namespace.",
      "files": ["src/routes/reset.ts"],
      "depends_on": ["1"]
    },
    {
      "id": "4",
      "title": "Throttled (429) page",
      "detail": "Friendly retry-after message instead of a raw error.",
      "files": ["src/views/throttled.tsx"],
      "depends_on": ["2", "3"],
      "optional": true,
      "before": "(raw 429 JSON)",
      "after": "<ThrottledNotice retryAfter={s} />"
    }
  ]
}
```

Renders as:

```
            ┌──────────────────────┐
            │ 1  Redis counter     │          ← shared prerequisite
            └──────────┬───────────┘
            ┌──────────┴───────────┐
            ▼                      ▼
┌──────────────────┐   ┌──────────────────┐
│ 2  Login guard   │   │ 3  Reset guard   │   ← fan out, run in parallel
└─────────┬────────┘   └────────┬─────────┘
          └───────────┬─────────┘
                      ▼
            ┌──────────────────────┐
            │ 4  Throttled page    │ optional  ← converge
            └──────────────────────┘
```

Boxes recolor live (green/red/amber) as the user approves / rejects / modifies the matching step below.

## What user pastes back

```
APPROVED: 1, 3, 4
MODIFY 2: use a Cloudflare Worker for the guard instead of in-process, skip captcha for now
```

Agent reads → implements 1, 3, 4 as planned; reworks step 2 per the modify note. (Each id appears once — a step is approved, rejected, *or* modified, never two at once.)
