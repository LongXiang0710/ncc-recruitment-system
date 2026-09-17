# Task 4: 二维码、响应式和可访问性收尾

This task builds on approved Tasks 1–3. Do not dispatch subagents. Do not change QR markup/data, JavaScript behavior, Python, schemas, or data.

## Files

- Modify: `web/corporate-theme.css`
- Read-only tests: `tests/test_qr_cards_ui.py`, `tests/test_dialog_layout_ui.py`, `tests/table_layout_ui_check.js`
- Report: `.superpowers/sdd/2026-09-11-corporate-blue-visual-refresh/task-4-report.md`

## Binding requirements

- Keep QR content, SVG data, dimensions needed for scanning, download behavior, safety area, and company name intact.
- Preserve the floating dialog close button in the upper-right.
- Preserve desktop toolbar arrangement and allow reasonable wrapping only when width is insufficient.
- Preserve existing breakpoints at `1150px` and `760px`; public mobile forms remain single-column and touch-friendly.
- Add clear keyboard focus and respect reduced-motion preference.
- Formal restrained corporate blue; no filters or overlay on QR images.

## Steps

1. Run baselines:
   - `python -m unittest tests.test_qr_cards_ui tests.test_dialog_layout_ui -v`
   - `node tests/table_layout_ui_check.js`
   Stop and report if baseline fails.
2. Append QR presentation rules using existing `.qr-dialog`, `.qr-grid`, `.qr-card`, `.qr-image-shell`, `.qr-card-label`, `.qr-card-company`, and `.qr-download` selectors. Approved anchors:

```css
.qr-dialog .qr-grid { background:var(--canvas); }
.qr-dialog .qr-card { border-color:#d8e3f0; border-radius:var(--radius-lg); box-shadow:var(--shadow-md); }
.qr-image-shell { background:#fff; }
.qr-card-label { color:var(--text-strong); }
.qr-download { color:var(--brand-700); }
```

Do not apply `filter`, `transform`, negative margins, clipping, pseudo-element overlays, or reduced QR image size to `.qr-image-shell img`.
3. Add global focus-visible and reduced motion:

```css
:focus-visible { outline:3px solid #76aaff; outline-offset:3px; }
@media (prefers-reduced-motion:reduce) {
  *,*::before,*::after { scroll-behavior:auto!important; transition:none!important; }
}
```

4. Append `@media(max-width:1150px)` and `@media(max-width:760px)` after all desktop theme rules. At 760px:
   - Keep navy sidebar and readable navigation.
   - Remove large active-navigation shadow.
   - Keep toolbar controls usable and search full width while buttons wrap as needed.
   - Reduce card/dialog shadow, keep dialog within viewport, keep forms single-column through existing base rules.
   - Keep QR grid single-column and QR image at the current safe mobile dimension.
5. Run final structure tests:
   - `python -m unittest tests.test_qr_cards_ui tests.test_dialog_layout_ui -v`
   - `node tests/table_layout_ui_check.js`
6. Perform read-only visual inspection if browser control is available:
   - Desktop: `/`, `/resume-submit?type=campus`, `/resume-batch`.
   - Mobile approximately 390×844: public submit and batch pages.
   - Do not submit forms, upload files, login, or delete/change data.
   - Check overflow, readability, QR image protection, and console errors.
   If the existing authenticated management page is not safely available, record that Task 5 must perform that check rather than using credentials.
7. Self-review the new CSS for cascade order, correct existing selectors, no hidden fields, and no QR image manipulation.
8. Write report with tests, visual inspection evidence or concrete limitation, selector/rule summary, self-review, and concerns. Return only status, one-line test summary, concerns.
