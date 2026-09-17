# SDD ledger — plan: docs/superpowers/plans/2026-09-16-nocobase-playwright-sync.md

## Execution environment

- Spec: `docs/superpowers/specs/2026-09-16-nocobase-playwright-sync-design.md`
- Workspace: current project directory (repository has no `.git`)
- Ruling: do not initialize Git or create a worktree — the approved plan explicitly requires direct execution in the current non-Git workspace; review packages use pre-task snapshots plus `git diff --no-index`. Cost if wrong: changes are not isolated by branch, so every task must preserve user data and pass a scoped review before continuing.
- Ruling: historical-sync verification requires successful audit entries for both supported entities whose archive numbers start with `PWTEST-` — this implements the approved two-test-record gate without storing personal data. Cost if wrong: users choosing a different test prefix would need to repeat the two controlled tests with the documented prefix.
- Ruling: Task 2's configuration CLI imports `browser.test_login` lazily inside the explicit test-connection action because Task 4 creates the browser adapter later. Cost if wrong: direct connection testing is unavailable until Task 4, while credential save/load remains independently usable.

## Preflight interface matrix

| Producer | Consumer | Shared interface/file | Finding |
|---|---|---|---|
| Task 1 | Tasks 7, 8, 9 | `queue.py`, queue tables and lifecycle functions | Clean; later tasks consume the exact named functions. |
| Task 1 | Task 8 | `features/nocobase_sync/__init__.py` | Clean; Task 8 may extend exports without changing queue signatures. |
| Task 2 | Tasks 4, 7, 11 | `NocoBaseConfig`, config file, CLI | Ruling above resolves the Task 2/4 lazy dependency. |
| Task 3 | Task 7 | `SyncRecord`, `load_record` | Clean; worker consumes immutable mapped records. |
| Task 4 | Tasks 5, 6, 7 | `NocoBaseBrowser` primitives | Clean; adapters own field-specific behavior. |
| Task 4 | Tasks 5, 6 | `tests/nocobase_fixture.py` | Clean; later tasks extend the same fixture sequentially. |
| Task 5 | Task 7 | `ResumeDocumentsAdapter` | Clean. |
| Task 5 | Task 6 | `tests/test_nocobase_adapters.py` | Clean; candidate tests extend rather than replace resume tests. |
| Task 6 | Task 7 | `CandidatesAdapter` | Clean. |
| Task 7 | Task 11 | `worker.py`, worker CLI and stop lifecycle | Clean; Task 11 adds process-level locking without changing run-once behavior. |
| Task 8 | Task 9 | `server.py`, initialized queue tables | Clean; API routes build on the integrated schema. |
| Task 9 | Task 10 | `/api/nocobase-sync/*` contracts | Clean; Task 10 consumes exact routes. |
| Task 10 | Task 12 | UI labels and workflow documentation | Clean. |
| Task 11 | Task 12 | startup lifecycle | Clean. |
| Tasks 1–11 | Task 12 | full system and generated Word manual | Clean; final task verifies all prior outputs. |

## Task status

- Task 1 — 持久化同步队列、任务合并和租约：COMPLETE。最终独立审查 APPROVED；Task 1 测试 24/24、全套测试 157/157、`py_compile` 通过。审查记录：`task-1-migration-review.md`。
