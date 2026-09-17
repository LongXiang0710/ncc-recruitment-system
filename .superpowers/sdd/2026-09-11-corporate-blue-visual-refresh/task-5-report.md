# Task 5 Report — Full regression, reload, and delivery verification

## Status

DONE_WITH_CONCERNS

## Test and syntax evidence

Command:

```text
python -m unittest discover -s tests -v
```

Result: exit code `0`; `Ran 88 tests in 8.377s`; `OK`. Failures: `0`. Errors: `0`.

Command:

```text
python -m py_compile server.py dify_client.py features/resume_documents/filename_position.py
```

Result: exit code `0`; no compiler output (successful syntax verification).

## Theme route, loading order, and source inspection

- `web/index.html` loads `/candidate.css` at character index `1283` and `/corporate-theme.css` at `1328`; the corporate stylesheet is therefore the final theme stylesheet after candidate CSS.
- `server.py:1612-1613` has the narrow static-route branch for `/corporate-theme.css`, returning `web/corporate-theme.css` as `text/css; charset=utf-8`.
- `web/corporate-theme.css` contains the required `--brand-950` token.
- Source inspection found no `.qr-image-shell img` rule in the theme. No QR-image-specific filter, clipping, transform, pseudo-element overlay, margin, or dimension override was added. (The stylesheet does contain a non-QR `.stat:hover` transform and the approved dialog backdrop filter.)

## Local service reload

Pre-reload listener:

```text
TCP    0.0.0.0:8116   0.0.0.0:0   LISTENING   11368
```

`Get-Process -Id 11368` verified `ProcessName: python` and `Path: D:\Miniconda\python.exe` before it was stopped.

The required hidden-window command was then used with `D:\Miniconda\python.exe`, `server.py --host 0.0.0.0 --port 8116`, and working directory `D:\工作目录\南化建招聘系统`.

Post-reload listener and identity:

```text
TCP    0.0.0.0:8116   0.0.0.0:0   LISTENING   21668
Id          : 21668
ProcessName : python
Path        : D:\Miniconda\python.exe
```

HTTP verification after reload:

| Request | Result |
| --- | --- |
| `http://127.0.0.1:8116/` | HTTP `200`, 1,564 bytes |
| `http://127.0.0.1:8116/corporate-theme.css` | HTTP `200`, 11,428 bytes, `text/css; charset=utf-8`, contains `--brand-950` |

## Read-only browser verification

No fields were filled, no forms submitted, no files uploaded, and no credentials were used.

| Page | Desktop result | 390 × 844 result | Error-level console |
| --- | --- | --- | --- |
| `/resume-submit?type=campus` | Public submission page rendered with visible position input, upload control, consent checkbox, and submit action; no visible desktop overflow. | Single-column card remained readable; input, upload control, consent text, and submit action stayed within viewport with no horizontal overflow. | `[]` |
| `/resume-batch` | Recruitment-type/channel selectors, PDF picker, add-PDF control, disabled import action, and explanatory text rendered clearly; no visible desktop overflow. | Controls stacked appropriately, picker action and status remained readable, and no horizontal overflow was visible. | `[]` |
| `/` management entry | The page presented the unauthenticated login form; its error-level console was `[]`. | Not applicable; management checks require an existing authenticated session. | `[]` |

The browser started from a safe unauthenticated session. Per binding instructions, no login was attempted; recruitment overview, resume collection, talent library, toolbar/table/modal, and live QR dialog could therefore not be inspected.

## Scope review

This project has no Git repository, so an exact baseline diff is unavailable. The four task reports and task briefs identify the intended theme-task production scope as `web/corporate-theme.css`, `web/index.html`, `server.py` (the required static-route allowlist correction), and `tests/test_server.py`; Tasks 2–4 modified only the theme CSS. Current source review confirms the expected link and narrow route implementation.

A filesystem timestamp scan cannot establish causality, but it found the theme files at the expected late-refresh times and many pre-existing production/test files with earlier same-day timestamps. It also found `data/recruitment.db` timestamped at `16:07:24`, immediately after the required server reload. This report does not claim an exact data diff because there was no pre-reload hash and the database is not version-controlled.

## Concerns

1. No safe authenticated browser session existed, so the management screens and live QR dialog—including floating close control, real QR rendering, and toolbar/table/modal checks—remain unverified. No credentials were used to bypass this limitation.
2. Exact scope proof is limited by the absence of Git/baseline hashes. In addition, `data/recruitment.db` received a new modified timestamp during the required service restart; no form or data-edit action was performed, but its logical data equivalence cannot be proven retrospectively without a pre-restart database hash.
