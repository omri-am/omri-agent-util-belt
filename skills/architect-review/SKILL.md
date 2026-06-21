---
name: architect-review
description: Use to get the user's OWN recent code changes critiqued on architecture and design by a tough principal-engineer reviewer before they merge or open a PR. Always use for `/architect-review` (one read-only critique) and `/architect-review N` (N rounds of critique → fix → re-review, stopping early on approval). Also use whenever the user asks to critique, stress-test, push back hard on, be brutal about, or tear apart the design of work they just did — uncommitted edits, a branch, or a diff. Catches "architect review", "review my design/architecture", "is this over-engineered / overkill / am I building a spaceship", "tear this apart before I PR", and "do N rounds of critique-and-fix until it's solid". This is design judgment — soundness, scalability, abstraction level — on recent changes, not fixing a failing test, explaining code, abstract design questions, line/naming/style review, or whole-codebase refactor sweeps.
---

# Architect Review

Run an adversarial architecture review of the current code changes. A fresh-context **Critical Architect** subagent critiques the diff; you (the main thread) apply the fixes you agree with; the architect re-reviews. Repeat until it approves or the round budget is exhausted.

Why this shape: a reviewer that grades its own fixes is a weak reviewer — it rationalizes. Keeping the architect read-only and separate from the fixer keeps every round genuinely adversarial. And spawning it fresh each round means it judges the *current* state of the code, not the conversation that produced it.

## Step 1 — Read the mode

The number decides whether you only critique or also edit:

- **Bare `/architect-review`** (no number, or a natural-language request with no count) → **review-only mode**: run the architect once, report its critique, and **change nothing**. Editing someone's code unattended is a bigger commitment than telling them what's wrong — when the user didn't ask for a fix loop, don't apply one. The user reads the critique and decides.
- **`/architect-review N`** (N ≥ 1) → **fix-loop mode**: run **at most N** critique↔fix rounds, applying fixes between rounds.

In fix-loop mode the loop always stops early the moment the architect returns `VERDICT: APPROVED`. N is a ceiling, not a quota — never burn rounds inventing changes just to use them up.

## Step 2 — Determine what to review (auto-detect)

Figure out the scope before spawning anything:

```
DEFAULT=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'); DEFAULT=${DEFAULT:-main}
git status --porcelain
```

- **Working tree is dirty** (uncommitted/staged/untracked changes present) → review the working changes: `git diff` + `git diff --cached`, plus the content of any untracked files (`git status --porcelain` lines starting with `??`).
- **Working tree is clean** → review the branch against its base: `git diff origin/$DEFAULT...HEAD` (note the three dots — diff against the merge-base, not the tip).

If there is genuinely nothing to review (clean tree *and* no commits ahead of base), stop and tell the user there are no changes to review.

You don't paste the raw diff yourself — the architect runs git in its own context. Your job is to tell it *which* scope to look at.

## Step 3 — Review (and, in fix-loop mode, iterate)

**Review-only mode (bare invocation):** do step (a) once, then go straight to Step 4 and report the architect's critique verbatim. Skip (c)–(e) entirely — you do not edit code. The architect's verdict (`APPROVED` or `CHANGES_REQUIRED`) is reported as-is; it's information for the user, not a trigger to start fixing.

**Fix-loop mode (`/architect-review N`):** run the full loop below for each round (1 … N).

**a. Spawn the architect.** Use the Agent tool. The subagent must be **read-only** — it critiques, it never edits. Construct its prompt as:

1. The full contents of `references/architect-prompt.md` (read it and paste it verbatim — it is the persona, framework, and the `VERDICT:` output contract).
2. The review scope from Step 2, stated concretely, e.g. *"Review the uncommitted working-tree changes in this repo"* or *"Review `git diff origin/main...HEAD`"*, plus the repo path.
3. **Round 2+ only:** the architect's previous-round critique, and a short summary of exactly what you changed in response (and what you deliberately did *not* change, with your reasoning). This is what makes it a real back-and-forth — the architect verifies its earlier concerns were actually resolved rather than re-reviewing from scratch.

Prefer a read-only agent type so edits are impossible by construction (e.g. `Explore`); if you use a general-purpose agent, the pasted persona already forbids edits — honor that.

**b. Parse the verdict.** The architect's final line is `VERDICT: APPROVED` or `VERDICT: CHANGES_REQUIRED`.
- `APPROVED` → exit the loop, go to Step 4.
- `CHANGES_REQUIRED` → continue to (c).

**c. Apply fixes with judgment — do not obey blindly.** You are an engineer receiving review, not a stenographer. For each Critical Flaw:
- If it's right, fix it properly — address the cause the architect named, not just the symptom, or the next round will (correctly) catch it again.
- If you think the architect is wrong, over-reaching, or proposing speculative complexity, **don't make the change.** Record your reasoning; you'll hand it to the architect next round so it can concede or counter. A confident, well-argued pushback is a valid outcome — the architect persona is told to concede sound rebuttals.
- Probing Questions are prompts to think, not always action items. Answer the ones that reveal a real gap.

**d. Verify your fixes** before the next round, proportional to the change: run the relevant tests or a build/typecheck if they're quick. Don't hand the architect changes you haven't confirmed even compile.

**e.** If this was round N and the verdict was still `CHANGES_REQUIRED`, exit the loop — the budget is spent.

## Step 4 — Report back

**Review-only mode:** surface the architect's critique — its Critical Flaws, the better-way alternatives, and the verdict — and stop. Don't soften a `CHANGES_REQUIRED`. End by telling the user they can run `/architect-review N` to have you actually apply fixes across N rounds.

**Fix-loop mode:** give the user a tight summary:
- **Outcome:** approved in round X, or budget (N rounds) exhausted with the architect still requesting changes.
- **What changed:** the concrete fixes you applied across the rounds.
- **Open concerns:** any architect points you pushed back on (with your reasoning) and anything still unresolved when the budget ran out — so the user can decide whether to keep going (`/architect-review N` again) or accept the trade-off.

Don't paper over a non-approval. If the architect still wants changes when you stop, say so plainly and surface what it's still flagging.
