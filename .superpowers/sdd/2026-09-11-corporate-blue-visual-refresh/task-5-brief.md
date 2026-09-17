# Task 5: 完整回归、服务重载与交付验证

This task verifies approved Tasks 1–4 and reloads the local service. Do not dispatch subagents. Do not make production code or CSS changes; report any defect as BLOCKED or DONE_WITH_CONCERNS for a separate fix round.

## Files

- Verify: `web/corporate-theme.css`, `web/index.html`, `server.py`, `tests/test_server.py`
- Create/update report only: `.superpowers/sdd/2026-09-11-corporate-blue-visual-refresh/task-5-report.md`

## Binding requirements

- All existing features, data, fields, menus, import/export, Dify and candidate flows remain intact.
- Theme remains a separate final stylesheet.
- Service remains on `0.0.0.0:8116`; user URL remains `http://172.16.30.81:8116/`.
- No form submission, file upload, data editing, deletion, password use, or login during visual checks.
- Carry-forward from Task 4: inspect `/resume-submit?type=campus` visually and check its console if browser control is available; also inspect the authenticated management page and live QR dialog only if an already-authenticated session is safely available.

## Steps

1. Run the complete suite: `python -m unittest discover -s tests -v`. Record total, failures, errors and exit code.
2. Run syntax verification: `python -m py_compile server.py dify_client.py features/resume_documents/filename_position.py`.
3. Inspect stylesheet load order and server route implementation for correctness. Confirm no production file outside the approved scope changed during theme tasks.
4. Precisely identify the process listening on port 8116 with `netstat -ano`. Confirm it is Python before stopping it. Restart with hidden window:

```powershell
Start-Process -FilePath 'D:\Miniconda\python.exe' -ArgumentList 'server.py','--host','0.0.0.0','--port','8116' -WorkingDirectory 'D:\工作目录\南化建招聘系统' -WindowStyle Hidden
```

5. Verify after restart:
   - `http://127.0.0.1:8116/` returns HTTP 200.
   - `http://127.0.0.1:8116/corporate-theme.css` returns HTTP 200 and contains the theme token `--brand-950`.
   - `netstat -ano` shows `0.0.0.0:8116` LISTENING.
6. If browser control is available, perform read-only visual checks at desktop and approximately 390×844 mobile widths:
   - `/resume-submit?type=campus`
   - `/resume-batch`
   - Current authenticated management page if already authenticated, including recruitment overview, resume collection, talent library, toolbar, table, modal, and QR dialog.
   - Check error-level console logs.
   Do not log in or enter/submit data. If browser control remains unavailable, document the exact limitation and use HTTP/static verification; flag visual checks as a delivery concern.
7. Write `task-5-report.md` with command outputs, service PID before/after, HTTP results, visual checks, console results, scope review, and concerns. Return only status, one-line verification summary, and concerns.
