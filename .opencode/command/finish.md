---
description: Commit and push, clean up ai/temp, and hand off incomplete work
---

Finish the session:

## 1. Inspect

- Run `git status`, `git diff`, and `git log --oneline -10`.
- Identify the changes that belong to the work done in this session.
- Leave unrelated in-progress changes uncommitted and unmodified.

## 2. Commit and push

- Stage only the intended files. Never stage `ai/temp/`.
- Never commit secrets, credentials, or tokens.
- Write a concise commit message matching the repository style: a prefix (`FIX:`, `ADD:`, `CHANGE:`, `CODE:`, `VERSION:`, `REVERT:`) followed by a literal description. Add a short body when the change needs explanation.
- Commit, then push to the current branch's tracking remote.
- If a commit or push fails, fix the cause and create a new commit. Do not amend the failed commit.
- If there is nothing to commit, state that and skip the commit and push.

## 3. Clean up temp files

- Delete every file in `ai/temp/`, including copied logs, probe scripts, and other scratch files.
- Keep `ai/temp/handoff.md` until step 4 has decided whether it is still needed.

## 4. Hand off incomplete work

- If work from this session, or work described by the existing `ai/temp/handoff.md`, remains incomplete, write `ai/temp/handoff.md`.
- `ai/temp/handoff.md` contains only the description of the incomplete work and starts with a `Read when:` line.
- If no work remains incomplete, delete `ai/temp/handoff.md` and do not recreate it.

## 5. Report

Report the commit hash and push result, what was removed from `ai/temp`, and whether `ai/temp/handoff.md` was written or deleted.
