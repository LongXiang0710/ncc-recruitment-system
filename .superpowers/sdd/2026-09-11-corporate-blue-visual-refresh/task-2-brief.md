# Task 2: 管理后台外壳与核心组件

This task builds on the approved Task 1 theme foundation. Do not dispatch subagents. Do not modify JavaScript, Python, schemas, data, or HTML.

## Files

- Modify: `web/corporate-theme.css`
- Read-only tests: `tests/test_dialog_layout_ui.py`, `tests/table_layout_ui_check.js`, `tests/test_selection_export_ui.py`
- Report: `.superpowers/sdd/2026-09-11-corporate-blue-visual-refresh/task-2-report.md`

## Binding requirements

- Use the existing theme tokens in `web/corporate-theme.css`.
- Preserve the fixed sidebar dimensions and layout behavior.
- Style existing selectors only: `aside`, identity/nav elements, `header`, `.page-title`, `.panel`, `.stat`, `.primary`, `.secondary`, inputs, `.badge`, `.toolbar`, table elements, `.row-actions`, `.pagination`, `dialog` and dialog regions.
- Formal corporate blue: deep navy sidebar, bright blue active navigation, white cards, pale blue-gray canvas, restrained shadows.
- Do not change DOM structure, data attributes, event handlers, API requests, or business behavior.

## Steps

1. Run the baseline commands before CSS edits:
   - `python -m unittest tests.test_dialog_layout_ui tests.test_selection_export_ui -v`
   - `node tests/table_layout_ui_check.js`
   Stop and report if baseline fails.
2. Append maintainable grouped rules to `web/corporate-theme.css` for:
   - Sidebar/identity/navigation, with readable inactive, hover, and active states.
   - Header/page title/account controls.
   - Panels, cards, inputs, selects, textareas, primary/secondary/light buttons, disabled states, and focus states.
   - Toolbar, table header/body/hover, selection checkbox, action buttons, status badges, and pagination.
   - Dialog backdrop, shell, header, footer, and floating close button compatibility.
3. Base the implementation on these approved values, improving selector completeness where needed without adding features:

```css
aside { background:linear-gradient(180deg,var(--brand-950),var(--brand-900)); border-right:0; box-shadow:8px 0 30px rgba(7,29,61,.08); }
aside nav button.active { color:#fff; background:linear-gradient(135deg,var(--brand-600),#247be5); box-shadow:0 10px 24px rgba(0,80,190,.28); }
.panel,.stat { border-color:var(--border); border-radius:var(--radius-md); box-shadow:var(--shadow-sm); }
.primary { background:linear-gradient(135deg,var(--brand-700),var(--brand-600)); box-shadow:0 7px 16px rgba(21,87,176,.18); }
input:focus,select:focus,textarea:focus { border-color:var(--brand-600); box-shadow:0 0 0 3px rgba(23,105,210,.12); }
.badge { border-radius:999px; font-weight:650; }
th { background:#f4f7fb; color:#52647e; font-weight:650; }
tbody tr:hover { background:#f6faff; }
dialog { border-radius:var(--radius-lg); box-shadow:0 30px 90px rgba(7,29,61,.3); }
dialog::backdrop { background:rgba(7,29,61,.58); backdrop-filter:blur(4px); }
```

4. Re-run:
   - `python -m unittest tests.test_dialog_layout_ui tests.test_selection_export_ui -v`
   - `node tests/table_layout_ui_check.js`
5. Self-review for color contrast, selector scope, duplicate rules, accidental component behavior changes, and preservation of `.close` positioning from existing table-layout styles.
6. Write the report file with status, file changed, baseline evidence, final test evidence, self-review, and concerns. Return only status, one-line test summary, and concerns.
