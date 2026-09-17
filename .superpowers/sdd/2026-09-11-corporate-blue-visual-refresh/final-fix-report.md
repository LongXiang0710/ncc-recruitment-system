# Final fix report: destructive styling and accessibility

## Scope

- Production change: `web/corporate-theme.css` only.
- No DOM, class, event-handler, confirmation-flow, or deletion-behavior changes were made.
- No focused test was added. The existing server integration test already verifies that the theme is served and loaded after `candidate.css`; a new test that asserted CSS selectors or literal colors would duplicate the CSS implementation rather than validate a separate observable integration.

## Root cause and fix

`web/corporate-theme.css` is loaded after `web/candidate.css`. Its generic `.secondary` and `.primary` rules therefore overrode the earlier `.delete-selected` color/border treatment, while `.primary.delete-confirm` inherited the shared blue primary appearance. The class-specific focus-visible rule also won over the global focus rule and used a translucent outline.

The theme now supplies these specific destructive selectors after the shared action rules:

- `.secondary.delete-selected`: foreground `#a74245`, border `#e4b2b5`, background `#fff6f6`.
- `.secondary.delete-selected:hover`: foreground `#873033`, border `#ce7378`, background `#ffe9ea`.
- `.secondary.delete-selected:disabled`: foreground `#9a6a6c`, border `#ead7d8`, background `#fbf5f5`, no shadow, and opaque disabled presentation.
- `.primary.delete-confirm`: background `#b6494b`, shadow `rgba(182,73,75,.2)`.
- `.primary.delete-confirm:hover`: background `#973d40`, shadow `rgba(151,61,64,.25)`.
- `.primary.delete-confirm:disabled`: background `#d89ea0`, no shadow, and opaque disabled presentation.

Both destructive controls have explicit `:focus-visible` coverage with `outline: 3px solid #0b5fcc` and `outline-offset: 2px`.

## Readability and focus colors

- `--text-muted` changed from `#71809a` (about 4.00:1 on white) to `#566782` (about 5.74:1 on white).
- `input::placeholder, textarea::placeholder` changed from `#9aa8ba` (about 2.42:1) to `#5a6b82` (about 5.44:1).
- The winning `.primary`, `.secondary`, and `.light` `:focus-visible` rule now uses opaque `#0b5fcc`; the global `:focus-visible` rule uses that exact same color. Its contrast on white is about 5.96:1.
- Component focus offset remains `2px`, retaining visible separation around primary buttons; the global rule retains its `3px` offset.

## Verification

Focused structural command:

```text
python -m unittest tests.test_dialog_layout_ui tests.test_selection_export_ui tests.test_qr_cards_ui -v
Ran 3 tests in 0.191s
OK
```

Table-layout command:

```text
node tests/table_layout_ui_check.js
table layout UI checks passed
```

Full suite:

```text
python -m unittest discover -s tests -v
Ran 88 tests in 7.816s
OK
```

Additional read-only cascade/accessibility assertion verified the required selectors, colors, focus offsets, and `candidate.css` before `corporate-theme.css` load order:

```text
theme cascade and accessibility assertions passed
```

## Browser acceptance

Browser control was available, but its inventory contained no applications and only an empty Codex in-app browser with zero tabs. No existing authenticated session was available. No login was attempted; no data was submitted, changed, or deleted. Consequently, the authenticated management toolbar, safe-opened deletion confirmation, QR dialog, and live keyboard-focus states were not visually inspected.

## Self-review and concerns

- The cascade-specific selectors are more specific than the shared theme controls and appear later in the same stylesheet, so they restore destructive differentiation without changing behavior.
- The destructive palette is restrained and aligns with the existing `.row-actions button.danger` red (`#b6494b`).
- The outstanding release-verification gap is visual acceptance of authenticated management and QR states, including actual keyboard focus rendering, once a safe existing authenticated browser session is available.
