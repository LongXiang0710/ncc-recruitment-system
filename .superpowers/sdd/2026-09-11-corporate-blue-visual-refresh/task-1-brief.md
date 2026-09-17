# Task 1: 独立主题入口与设计令牌

Read the approved spec at `docs/superpowers/specs/2026-09-11-corporate-blue-visual-refresh-design.md` only for binding visual constraints. Do not dispatch subagents.

## Files

- Create: `web/corporate-theme.css`
- Modify: `web/index.html`
- Modify: `tests/test_server.py`, method `test_01_private_routes_and_static`
- Report: `.superpowers/sdd/2026-09-11-corporate-blue-visual-refresh/task-1-report.md`

## Requirements

1. Use TDD: add `/corporate-theme.css` to the static-route test and assert `/candidate.css` appears before `/corporate-theme.css` in the served homepage. Run the narrow test and record the expected failure before production edits.
2. Add `<link rel="stylesheet" href="/corporate-theme.css">` after the existing `/candidate.css` link so the theme is the final stylesheet.
3. Create `web/corporate-theme.css` with these exact tokens and base body rule:

```css
:root {
  --brand-950:#071d3d;
  --brand-900:#0b2b59;
  --brand-800:#123f7a;
  --brand-700:#1557b0;
  --brand-600:#1769d2;
  --brand-100:#eaf3ff;
  --brand-50:#f4f8ff;
  --surface:#fff;
  --canvas:#f2f6fb;
  --text-strong:#10233f;
  --text:#30435f;
  --text-muted:#71809a;
  --border:#dfe7f1;
  --shadow-sm:0 2px 10px rgba(9,42,88,.06);
  --shadow-md:0 14px 40px rgba(9,42,88,.12);
  --radius-sm:8px;
  --radius-md:12px;
  --radius-lg:16px;
  --blue:var(--brand-600);
  --line:var(--border);
  --muted:var(--text-muted);
}
body { background:var(--canvas); color:var(--text-strong); }
```

4. Run `python -m unittest tests.test_server.RecruitmentTests.test_01_private_routes_and_static -v` and confirm PASS.
5. Self-review for scope: no JavaScript, service, schema, database, or unrelated CSS changes.
6. Write the report file with status, files changed, red test evidence, green test evidence, self-review, and concerns. Return only status, a one-line test summary, and concerns.
