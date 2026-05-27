# Examples

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

## What user pastes back

```
APPROVED: 1, 3
REJECTED: 2
MODIFY 2: use Cloudflare Worker instead, but skip captcha for now
```

Agent reads → implements steps 1 + 3, swaps step 2 for a worker per modify note.
