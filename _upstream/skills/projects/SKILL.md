---
name: delapan-projects
description: List cross-repo projects and branches with activity metadata. Use when the user asks what repos/KBs exist or wants to switch context across projects.
---

# Delapan Projects

Discovery surface for all projects and branch-KBs the store knows about.

## Workflow

1. Call **`delapan_projects`** (no project/kb required).
2. Present repos and branches with last-activity hints from the response.
3. If the user picks a target, note `project` + `kb` for subsequent `delapan_resume` / `delapan_search` calls.

## When to use

- "What repos do I have in delapan?"
- "Which branches have findings?"
- Before resuming work in a different repo than the current cwd
