# Running the build in Codex — session playbook

The competition judges the work done **in Codex** during the submission period. One
primary thread, small commits, `/feedback` at the end. This file is the operator manual.

## Before the first session

1. Request the free $100 Codex credits (deadline **Fri 2026-07-17 12:00 PT**):
   https://forms.gle/rP8WJgk4D2zQEu1A6
2. `npm install -g @openai/codex@latest`, sign in with the ChatGPT account.
3. `cp .env.example .env` and add your `OPENAI_API_KEY` (Task 2 Step 0 and the live
   smokes need it; unit tests do not).

## Opening the primary thread

```bash
cd ~/Repositories/8star/codex8
codex --ask-for-approval on-request --sandbox workspace-write
```

Select the strongest GPT-5.6 tier with `/model`. Then paste:

> Read AGENTS.md, then SPEC.md, then docs/PLAN.md in full. Execute docs/PLAN.md starting
> at Task 1, strictly in order, one task at a time: failing test → run → implement → green
> → commit, checking off plan checkboxes as you go. `_upstream/` is read-only reference.
> Stop and report after each task's commit.

## Continuing (always the same thread)

```bash
codex resume --last
```

> Continue docs/PLAN.md at the first unchecked task. Re-run the full test suite before
> starting it.

If the thread degrades, prefer compacting/continuing over starting fresh — the `/feedback`
session ID must come from the thread "where the majority of core functionality was built".

## Phase gates (verify before moving on)

- **After Task 8:** `.venv/bin/pytest` fully green — the engine imports and runs end-to-end.
- **After Task 10:** in a NEW Codex session, `codex8_projects` is callable and the four
  `codex8-*` skills are listed. This proves the plugin surface, which is the product.
- **After Task 11:** the demo-KB search command in Task 11 Step 3 returns ranked findings.
- **After Task 12:** SPEC.md acceptance checklist all checked.

## Evidence checklist (submission fields)

- [ ] `/feedback` run in the primary thread → session ID saved to the Devpost draft
- [ ] Repo public on GitHub with LICENSE (or private + shared with testing@devpost.com and
      build-week-event@openai.com)
- [ ] Commit history shows: snapshot commit (prior work) → per-task feature commits (new work)
- [ ] README "Built with Codex" narrative references real tasks/commits
- [ ] Demo video < 3 min, public YouTube: demo-KB recall → live explore → coverage upgrade,
      voiceover naming Codex and GPT-5.6 usage
- [ ] Submission before **Tue 2026-07-21 17:00 PDT**
