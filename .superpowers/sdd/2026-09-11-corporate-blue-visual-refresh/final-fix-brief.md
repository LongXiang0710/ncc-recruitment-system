# Final fix wave: destructive styling and accessibility

Read the final reviewer findings in `.superpowers/sdd/2026-09-11-corporate-blue-visual-refresh/final-review-package.md` context and the exact requirements below. Do not dispatch subagents.

## Files

- Modify: `web/corporate-theme.css`
- Add or modify a focused test only if it validates observable theme integration without duplicating CSS implementation.
- Report: `.superpowers/sdd/2026-09-11-corporate-blue-visual-refresh/final-fix-report.md`

## Required fixes

1. Restore clear destructive styling for existing `.secondary.delete-selected` bulk-delete controls and `.primary.delete-confirm` confirmation controls, including normal, hover, focus, and disabled presentation. Do not alter DOM, classes, event handlers, confirmation logic, or delete behavior. Use restrained red tones consistent with the existing `.danger` action.
2. Change `--text-muted` from the plan draft to a darker readable value; use a placeholder color with at least approximately 4.5:1 contrast on white.
3. Make the winning focus-visible rule for `.primary`, `.secondary`, and `.light` use an opaque high-contrast blue. Align the global `:focus-visible` rule to the same color. Preserve outline offset so primary buttons retain a visible white separation from the outline.
4. Keep the theme isolated in `web/corporate-theme.css`; do not change other production files.
5. Run focused structural checks:
   - `python -m unittest tests.test_dialog_layout_ui tests.test_selection_export_ui tests.test_qr_cards_ui -v`
   - `node tests/table_layout_ui_check.js`
6. Run full suite: `python -m unittest discover -s tests -v`.
7. If browser control is available, inspect computed/visible states without clicking deletion or submitting data. Use an existing safe authenticated session only; do not log in. Check management toolbar, delete confirmation only if it can be opened without a destructive final action, and QR dialog. Otherwise record this acceptance gap unchanged.
8. Report exact color values, selectors, test counts/output, browser checks or limitation, self-review, and concerns.

## Reviewer findings to address verbatim

- `corporate-theme.css:82` overrides `.delete-selected` from `candidate.css`; `.primary.delete-confirm` receives the same blue as Save. Add explicit theme rules for bulk deletion and deletion confirmation, including hover and disabled states.
- The class-specific focus rule wins over the global focus rule and uses a 25%-opacity outline; muted and placeholder colors have weak contrast. Use a clearly contrasting opaque focus color and darker text/placeholder colors, then verify keyboard focus when browser access permits.
- Authenticated management and QR visual acceptance remains incomplete. Complete it only if a permitted existing authenticated session is available; otherwise keep the release-verification limitation explicit.
