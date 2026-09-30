# SDD ledger — plan: docs/superpowers/plans/2026-09-30-nocobase-resume-and-talent-cutover.md
Setup: Ruling: bundled Bash workspace scripts cannot create directories through the Windows/MSYS sandbox for this Chinese-path managed worktree — mirror the documented workspace and ledger format with apply_patch and run equivalent commands directly — cost if wrong: only execution bookkeeping automation is affected, not product code or tests.
Pre-flight: Task 1 PreflightReport.resume_fields -> Task 2 mapping: consistent; Task 1 only discovers remote keys, Task 2 owns value translation.
Pre-flight: Task 2 ResumeRepository -> Tasks 4/5/6: consistent stable-key and linked-candidate query interfaces.
Pre-flight: Task 3 ResumeAttachmentRepository -> Tasks 4/5/6: consistent list/read/replace/restore/unreferenced-delete interfaces.
Pre-flight: Tasks 4-6 services -> Task 7 RemoteServices: consistent; service container is deliberately assembled only after all services exist.
Pre-flight: Task 6 RemoteCandidateService.find_by_phone -> Task 8 RemoteCandidateReference: consistent.
Pre-flight: Task 7 RemoteServices -> Tasks 9-11: consistent; runtime and migration receive the same repositories/services without SQLite fallback.
Pre-flight: Task 10 MigrationReport/digests -> Task 11 apply: consistent; apply revalidates both digests before any mutation.
Task 1: complete (commits c71a7af..97b40ec, tests: python -m unittest discover -s tests -p 'test_*.py' → Ran 239 tests, OK)
Task 2: complete (commits 97b40ec..9554273, tests: python -m unittest discover -s tests -p 'test_*.py' → Ran 244 tests, OK)
Task 3: complete (commits 9554273..a58e5de, tests: python -m unittest discover -s tests -p 'test_*.py' → Ran 249 tests, OK)
Task 4: complete (commits a58e5de..49cd2cd, tests: python -m unittest discover -s tests -p 'test_*.py' → Ran 254 tests, OK)
Task 5: complete (commits 49cd2cd..8db4196, tests: python -m unittest discover -s tests -p 'test_*.py' → Ran 260 tests, OK)
Task 6: complete (commits 8db4196..pending, tests: python -m unittest discover -s tests -p 'test_*.py' → Ran 267 tests, OK)
