# Task 4 Report — QR, responsive, and accessibility finish

## Changed file

- `web/corporate-theme.css` only.

## Selector and rule summary

- Added corporate-blue QR card presentation for `.qr-dialog .qr-grid`, `.qr-dialog .qr-card`, `.qr-image-shell`, `.qr-card-label`, `.qr-card-company`, and `.qr-download`.
- Kept QR source markup, download behavior, and the existing scan-safe image dimensions unchanged: 280px desktop and 250px mobile remain defined in `web/table-tools.css`.
- Added global `:focus-visible` and `prefers-reduced-motion:reduce` handling.
- Appended (rather than changed) the existing `1150px` and `760px` responsive breakpoints. The mobile rules preserve the navy sidebar, remove the large active-navigation shadow, make record-toolbar search full-width and actions wrap, reduce dialog/card shadows, and retain the single-column QR grid.
- The floating close button's existing geometry was not changed; at 1150px and below, the dialog width reserves viewport room for it.

## Tests

- `python -m unittest tests.test_qr_cards_ui tests.test_dialog_layout_ui -v` — passed (2 tests).
- `node tests/table_layout_ui_check.js` — passed.
- CSS self-review script — passed: required anchors and both breakpoints exist; appended task rules do not target `.qr-image-shell img` and contain no QR filters, clipping, or negative margins.

## Read-only visual inspection

- Desktop: inspected `/`, `/apply?type=campus`, and `/resume-batch` on the local service. The management entry presented its login form; the public submission and batch-import pages were readable with no visible overflow.
- Mobile 390×844: inspected campus submission and batch import. Both public forms remained single-column, controls were touch-sized, and no horizontal overflow was visible.
- Browser console: no error entries were recorded during the public-page inspection.

## Self-review

- CSS was appended after the desktop theme rules, so the intended responsive overrides win without changing base markup or JavaScript.
- No field-hiding rules were introduced. No QR image selector was added or modified, and no QR overlay, transform, filter, clipping, or dimension reduction was introduced.

## Concern / follow-up

- The authenticated management page and live QR dialog were not opened because no safe authenticated session was available. Task 5 should verify the QR modal, including its floating upper-right close button, real QR rendering, and toolbar behavior in an authenticated management session.

## Review correction — specified submission route

- The earlier desktop note incorrectly named `/apply?type=campus`; the required route is `/resume-submit?type=campus`.
- Read-only local HTTP verification of `http://localhost:8116/resume-submit?type=campus` returned `200` (1,508-byte document) and confirmed that the route loads `/corporate-theme.css`.
- A desktop visual/overflow and browser-console capture for that route could not be completed in this review round: the CUA browser inventory returned no available browser, and its desktop-browser recovery service was not configured. No form was submitted, no file was uploaded, and no credentials were used. Task 5 must perform the pending visual and console check for this exact route once a browser target is available.
