---
name: design-doc
description: Turn a design conversation — the problem, architecture, flows, services, decisions, and open questions that were actually discussed — into a complete, standalone Google Doc. Always produces a brand-new doc with a fixed structure (Overview, Architecture, Happy flow sequence diagrams, Services and entities, an optional Key design decisions section, Open questions), with mermaid diagrams included as shaded code blocks. Use whenever the user asks to write up, capture, or turn this conversation into a design doc, wants it "in google docs" or "as a doc", says "let's document this design", or asks to formalize an architecture/flow discussion — even if an older doc or previous revision was pasted into the conversation, since this always creates a fresh, self-contained doc rather than a diff or revision-notes doc (only reference the old doc if the user explicitly asks to). Never invent content, services, entities, or open questions beyond what was actually discussed in the conversation — sections with nothing to draw on are marked "None identified" rather than filled in. Not for revising an existing doc in place, generic meeting-note summaries, or PRDs/requirements docs (those have their own shape).
---

# Design Doc

Distill a design conversation into a Google Doc with a fixed structure. The doc is a **record of what was actually decided and discussed** — not a place to fill gaps with plausible-sounding detail. If the conversation didn't settle something a heading asks for, say so explicitly rather than inventing it. A fabricated service name or a made-up entity field is worse than a gap, because a design doc reads as ground truth to everyone who reads it after the conversation is forgotten.

This is always a **new** doc. If an older revision was pasted into the conversation, treat whatever was actually discussed about it as ordinary input — but the new doc stands alone. Don't write "changes from v1", don't link back to the old doc, don't frame anything as a diff, unless the user explicitly asks for that framing.

## Step 1 — Extract from the conversation

Re-read the conversation (not just the last message) and pull out, for each of the required sections:

- **Problem + proposed solution** — the thing being built and why.
- **Services/components and how they interact** — names and the general action between them (not method signatures or payloads).
- **Main use cases actually walked through** — the happy-path flows, not every edge case mentioned in passing. Error handling and edge cases belong in Open Questions if they were raised as unresolved, not in the happy-flow section — the name is literal.
- **Entities per service** — only ones actually named. If a service's data model wasn't discussed, that's fine; say so, don't guess fields.
- **Settled decisions with real weight** — a call that was actually made, especially where an alternative was explicitly considered and rejected, or a cross-cutting policy that shapes multiple services (e.g. how auth scopes are enforced, how credentials are classified for storage). Don't manufacture a "rationale" for a choice nobody explained — only capture ones the conversation actually justified.
- **Open questions** — things explicitly flagged as undecided or unresolved, technical or product. Don't manufacture a question just to fill the section; an honest "None identified" is a correct, useful signal that nothing was left hanging.

If something is genuinely ambiguous (e.g., you're not sure if a service was proposed as one thing or two), ask the user rather than picking one and writing it down as fact.

## Step 2 — Confirm the doc title

Propose a title based on the feature/project name that came up in conversation (e.g. "Notification Fanout Service — Design Doc") and confirm it with the user before creating anything — this is the one input the doc destination genuinely needs (new docs land in Drive root).

## Step 3 — Write the sections, in this order and only this order

### Overview
Two paragraphs max. First: the problem. Second: the proposed solution. No architecture detail here — that's the next section's job.

### Architecture
One mermaid diagram (`graph` / `flowchart`), high level only:
- Nodes = **only** the proposed/discussed microservices — nothing finer-grained, but also nothing coarser. Don't add a node for the external caller (client, partner, end user), and don't add a node for infrastructure the services use (a queue, a cache, a database, an internal library) — those aren't services either. If one of those matters to an interaction, say so in the edge label instead (e.g. an edge from ingest to processor labeled "via queue"), or drop it if it's not adding information at this altitude.
- Edge labels = a short verb phrase for the action ("publishes event", "reads config", "requests auth") — never method names, field names, or payload shapes.

This is a map for someone skimming, not an API reference. If you find yourself wanting to label an edge with a specific field or endpoint, that detail doesn't belong here — drop it. If you find yourself adding a node that isn't one of the services being designed, drop that too — it belongs in the sequence diagram, where actors, queues, and datastores are expected participants.

### Happy flow in sequence diagram for main use cases
One mermaid `sequenceDiagram` per distinct main use case identified in Step 1 (could be one, could be several — don't force it to exactly one, and don't invent extra use cases to look thorough). Add a short verbal explanation under a diagram only if the diagram alone is genuinely ambiguous (e.g. a branch worth calling out); otherwise let the diagram speak for itself — don't restate it in prose underneath.

### Services and entities
For each service: a 1–2 sentence description of its role, then a bullet list of the entities it owns. If entities were discussed with real shape (fields), include that; if only named, list the name and role only — don't invent fields. If a service holds no entities, write "No entities" rather than skipping it.

### Key design decisions (optional — omit the whole heading if it doesn't apply)
Unlike the other sections, this one doesn't get a "None identified" placeholder — if the conversation never surfaced a settled decision worth explaining, skip the heading entirely rather than forcing content into it. Include it when there's a real "we chose X, not Y, because Z" to record, or a policy that cuts across multiple services (e.g. how something is enforced consistently everywhere rather than per-service). One bullet per decision: the choice, then the rejected alternative(s) and why, in the terms the conversation actually used. This is where the "why", not the "what", lives — the what already has a home in Architecture/Services and entities.

### Open questions
One bullet per question actually raised, each prefixed `[Technical]` or `[Product]`. If none were raised in the whole conversation, write "None identified" — don't leave the heading empty and don't invent a question to avoid saying so. If there are enough questions in both categories that a flat interleaved list gets hard to scan (roughly more than four or five total, with both categories represented), split into `Technical` and `Product` sub-headings instead of prefixing every line — group by what the reader is scanning for. For a short list, the inline `[Technical]`/`[Product]` prefix is enough; don't add sub-headings for their own sake.

## Step 4 — Assemble and create the Google Doc

Each diagram goes in as its **raw mermaid source only** — never as an embedded image. This isn't a stylistic choice: the Drive upload tool only accepts inline text content, so any embedded image has to pass through your own context as a base64 string and get regenerated verbatim as part of the tool call. Base64 has no linguistic structure for a model to lock onto while reproducing it, and long blobs (even a few KB) reliably get corrupted in that regeneration step — silently: the tool call reports success, but the doc ends up with literal `data:image/...` text leaked into it instead of a real image. Don't try to route around this by rendering diagrams to images (e.g. via mermaid-cli) and embedding them — it costs 10-30x the tokens and time of the rest of this task and still isn't reliable. A code block a reader can paste into a mermaid viewer (or that another LLM can edit directly) is the correct output, not a fallback.

Google Docs has no native code-block element, and `<pre><code>` does not survive the HTML-to-Doc conversion — it silently flattens to plain paragraph text with no monospace font or visual boundary, which is exactly what makes a mermaid block hard to tell apart from prose. Use a single-cell table instead, which does convert faithfully: a shaded background and monospace font read as a code block, and the table's border keeps it visually contained. Build each line-break with a literal `<br>` rather than relying on whitespace, since the converter collapses ordinary whitespace like any other HTML renderer would:

```html
<table style="border-collapse:collapse;width:100%;"><tr><td style="background-color:#f5f5f5;border:1px solid #cccccc;padding:10px;font-family:'Courier New',monospace;font-size:9pt;">graph LR<br>&nbsp;&nbsp;&nbsp;&nbsp;A[Service A] --&gt;|does thing| B[Service B]</td></tr></table>
```

Build one HTML string — `<h1>` for the title, `<h2>` per required section (in the fixed order above), `<h3>` per use case under the sequence-diagram section if there's more than one, `<p>` for prose, the table pattern above for each mermaid source block. Set `line-height:1.5` inline on `<body>`, and on every `<p>` and `<li>` — Google's converter applies CSS from inline `style` attributes, not from a `<style>` block or classes, so it has to be repeated per element.

Create it with the Google Drive tool, letting HTML-to-Google-Doc conversion do the work:

```
mcp__claude_ai_Google_Drive__create_file(
  title: "<confirmed title>",
  textContent: "<the HTML string>",
  contentMimeType: "text/html"
)
```

Leave `parentId` unset (root) and `disableConversionToGoogleType` unset — the default conversion is what turns the HTML into a native Google Doc instead of an uploaded HTML file.

Report the doc link back to the user: `https://docs.google.com/document/d/<returned file id>/edit`.
