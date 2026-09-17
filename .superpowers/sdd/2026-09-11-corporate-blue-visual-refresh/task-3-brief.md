# Task 3: 总览、登录页和公开投递页面

This task builds on approved Tasks 1–2. Do not dispatch subagents. Do not modify JavaScript, Python, schemas, data, or HTML.

## Files

- Modify: `web/corporate-theme.css`
- Read-only tests: `tests/test_qr_cards_ui.py`, `tests/test_candidate_experiences_ui.py`
- Report: `.superpowers/sdd/2026-09-11-corporate-blue-visual-refresh/task-3-report.md`

## Binding requirements

- Use the existing theme tokens and shared component styles.
- Style recruitment overview, login/authentication, public resume submission, public PDF batch import, and education/work/project experience editors.
- Preserve all forms, fields, upload behavior, Dify behavior, menus, data flow, and responsive logic.
- Formal corporate blue with restrained gradients and shadows; public forms must remain clean and low-distraction.

## Steps

1. Run baselines:
   - `python -m unittest tests.test_qr_cards_ui tests.test_candidate_experiences_ui -v`
   Stop and report if a baseline fails.
2. Append grouped rules to `web/corporate-theme.css` for:
   - `.overview-banner`, `.recruitment-overview`, `.stats`, `.stat`, `.pipeline` and overview panels.
   - `.auth`, `.auth-brand`, `.auth-card`, including readable brand copy and login form focus.
   - `.apply`, `.apply-title`, `.apply .panel`, consent, success, and public form hierarchy.
   - `.resume-file-picker-area`, selected files, import results, and upload affordance.
   - `.education-editor`, `.education-list fieldset`, `.candidate-experience-editor`, `.candidate-experience-list fieldset`, `.candidate-project-experience-editor`, and `.candidate-project-experience-list fieldset`.
3. Use these intended anchor rules and extend only as needed for coherent states:

```css
.overview-banner {
  background:linear-gradient(120deg,var(--brand-900),var(--brand-700) 68%,#2177dc);
  border-radius:var(--radius-lg);
  box-shadow:0 18px 45px rgba(9,52,111,.2);
}
.recruitment-overview { margin-bottom:28px; }
.recruitment-overview>.panel-head { border:0; padding:0 2px 14px; }
.stat { transition:transform .18s ease,box-shadow .18s ease; }
.stat:hover { transform:translateY(-2px); box-shadow:0 12px 30px rgba(9,42,88,.11); }
.auth-brand { background:linear-gradient(145deg,var(--brand-950),var(--brand-700)); }
.auth-card { background:#fff; }
.apply { max-width:940px; }
.apply .panel { box-shadow:0 18px 48px rgba(9,42,88,.1); }
.resume-file-picker-area { border:1px dashed #b9c9df; border-radius:var(--radius-md); background:var(--brand-50); padding:18px; }
.education-list fieldset,
.candidate-experience-list fieldset,
.candidate-project-experience-list fieldset {
  border-color:#d6e1ef;
  background:#fbfdff;
  box-shadow:inset 3px 0 var(--brand-100);
}
```

4. Keep existing `.logo` as the simple N mark and do not add imagery.
5. Rerun `python -m unittest tests.test_qr_cards_ui tests.test_candidate_experiences_ui -v`.
6. Self-review for selector accuracy against `web/app.js`, `web/table-tools.css`, `web/candidate.css`, and both feature CSS files; check no rule hides fields or changes layout behavior.
7. Append no mobile breakpoint work here; Task 4 owns responsive overrides.
8. Write report with status, baseline/final test outputs, selectors added, self-review, and concerns. Return only status, one-line test summary, concerns.
