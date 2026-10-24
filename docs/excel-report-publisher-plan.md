# Excel Report Publisher — implementation plan

Status: implemented in the source application, 23 October 2026. See implementation notes below for validation coverage and remaining acceptance work.

## Implementation notes

The toolbar has a visible Remove all action whenever reports are loaded. Removing the last report or clearing the batch restores the initial drop screen, resets preview/navigation/filter state, discards old selection/history/password references and saves an empty session. Pending preview callbacks are invalidated so a removed report cannot reappear; restarting the application also keeps the workspace empty.

Preparation now commits and saves each completed workbook immediately. The report tree remains available for browsing while inclusion, ordering, layout edits and export stay locked for the active batch. In combined mode, completed workbooks are labelled as individual previews until the complete combined PDF can be assembled. Later completions preserve the selected report/sheet, tree expansion and current preview page. Cancellation retains completed artifacts in the manifest.

Layout edits retain a separate, non-exportable sheet cache across session restoration. Preparation compares source bytes, engine version and each sheet's resolved settings, renders only missing/changed sheets, validates those outputs and assembles the workbook from the selected cached/fresh pages. Source changes, explicit recalculation and Retry exceptions bypass sheet reuse; a source fingerprint check also guards the interval before Excel opens the workbook.

Batch performance: intake and preparation each reuse one supervised private Excel process, recycling it after failures, cancellation/timeouts or 32 requests. Every workbook still opens with a fresh manual-calculation guard. Font inspection bulk-reads the original sample range, using individual font reads only for populated cells in mixed-size rows. Page setup changes are committed in groups through Excel's `PrintCommunication` setting. Prepare reuses existing PDFs when source hashes, selected sheet order, resolved settings, engine version and artifact files match; explicit recalculation and Retry exceptions still render again.

Local measurements from `scripts/benchmark_report_publisher.py` on the synthetic two-sheet reports (seconds; single runs):

| Workload | Intake | Preparation including validation/assembly | Combined PDF assembly | First page rasterisation |
| --- | ---: | ---: | ---: | ---: |
| 3 workbooks, before optimisations | 17.477 | 28.500 | 0.038 | 0.036 |
| Same 3 workbooks, after optimisations | 4.161 | 13.210 | 0.081 | 0.054 |
| 30 repeated sample workbooks / 60 pages, after optimisations | 15.488 | 109.304 | 0.487 | 0.047 |

These measurements separate Excel work from direct PDF operations; first-page rasterisation excludes PDF process startup and UI scheduling. The 30-workbook run repeats the three fixtures rather than representing 30 distinct engineering reports. Source hashes remained unchanged, and the three before/after PDFs matched in extracted text, page counts and page geometry. Detailed results are under `artifacts/publisher-performance/`. Complex reports and more worksheets still require additional native Excel export time on their first preparation.

The report list now owns the complete internal drag operation so Qt cannot remove rows a second time after reordering. Workbook checkboxes cascade to every sheet, with partial selection reflected on the parent and cached pages retained when everything is excluded. The main PDF canvas now scrolls continuously through the selected PDF, including every sheet and workbook in combined mode, and renders visible pages on demand.

Combined report mode is available directly on the toolbar and automatically displays the assembled PDF. It refreshes after report/sheet reordering, inclusion changes, cover/contents/numbering changes and preparation. Drag reports into order, drag sheets within their workbook, or use the list's move arrows / Alt+Up and Alt+Down. Reordering prepared sheets rebuilds their PDFs from cached pages without running Excel again. Export reuses the current assembled preview when its source/order/options signature matches.

The presentation was simplified after screenshot review: the normal window has a compact toolbar, report list, large PDF canvas and Prepare / Export actions. Layout, export and advanced options are in a three-tab Settings dialog; ordering, passwords and removal are in the report context menu. The empty workspace hides the report list, progress and Stop appear only during jobs, and the preview fits the available width when the window is resized. Screenshots at 1000 × 700 and 780 × 540 are in `artifacts/publisher-polish/`.

The launcher now includes Excel Report Publisher. The implementation provides recursive discovery, per-sheet inclusion and ordering, explicit settings inheritance, reusable presets with sheet-name/layout-signature matching, native Excel rendering in a supervised private process, automatic paper/orientation selection, width-fit, optional section pagination, actual PDF preview with lazy thumbnails, individual/per-sheet/combined publication, nested bookmarks, cover/contents/numbering options, exception review, cancellation, retry, source fingerprints, atomic versioned publication and a recoverable job manifest.

Automatic section detection is deliberately conservative: it recognises bold merged section labels and keeps compact blocks together. Explicit section rows are available for other report structures. Heading detection applies only to clearly bold, unmerged table headings. Row-height repair is opt-in and skipped for sheets containing anchored objects or merges. Same-sheet regions with different orientations remain a later feature as described below.

Data-connection workbooks and legacy macro sheets are held for a separate publishing copy. Binary/legacy workbook preflight cannot inspect saved caches as thoroughly as XML workbooks, so those outputs require review. Saved-value mode uses a manual-calculation guard workbook before opening the report; recalculation is explicit and its outputs require review.

Validation includes real desktop Excel exports of XLSX, XLSM, XLSB and XLS fixtures with a cached formula, embedded raster diagram and manual section breaks; mixed portrait/landscape worksheets; end-of-report text coverage; original source hashes; PDF assembly/navigation; publication byte identity; settings inheritance and session restoration. These are synthetic fixtures. Acceptance against the proposed collection of real engineering reports, special OLE/equation objects, unusual printers/fonts and a 100-file production batch remains necessary before claiming general report fidelity or a measured performance budget. No engineering calculation certification is inferred from a successful export.

## Focused UX changes and remaining ideas

The page control now uses a directly styled text input with explicit foreground/background colours and enough space for its digits. It follows scrolling, preserves unfinished input, and commits jumps on Enter or focus loss. Empty input restores the current page, Escape cancels an edit, and out-of-range numbers go to the nearest valid page.

The first two changes are implemented for 20–30-workbook batches. The remaining entries are optional ideas:

| Priority | Status | Improvement | User benefit and acceptance criterion |
| --- | --- | --- | --- |
| 1 | Implemented | Show and save each completed workbook immediately. | Review starts after the first workbook rather than the entire batch. Completed workbooks open individually during preparation; the final combined preview waits for all included reports. |
| 2 | Implemented | Cache individual sheet outputs across layout edits. | Changing one sheet's orientation or margins regenerates that sheet when source bytes are unchanged. Unaffected sheet PDFs retain their bytes and the workbook is assembled again from cached pages. |
| 3 | Optional | Prioritise visible-page rendering, discard obsolete queued requests, and prefetch one adjacent page when idle. | A selected page does not wait behind old thumbnails. Bound the bitmap cache and retain the page position through zoom and viewport changes. |
| 4 | Optional | Link report/sheet selection to combined-report page ranges and show the current workbook/sheet beside the page field. | A report-tree click jumps to the corresponding combined page. Scrolling identifies the visible sheet; Ctrl+G focuses the page input. |
| 5 | Optional | Extend undo to report/sheet ordering, inclusion and removal, retaining reusable PDFs. | Users can recover from an accidental move or exclusion without running Excel again. Preserve selection, expansion and scroll position. |
| 6 | Optional | Put exception details and remedies beside the affected report/sheet. | Review shows the affected location and offers the relevant action, such as a layout change followed by preparation. Resolve exceptions individually and keep the final included/omitted counts visible before export. |

The implementation also reuses the private Excel process per batch, bulk-reads font samples, batches printer settings, caches unchanged prepared workbooks, and reassembles ordering/inclusion changes without Excel when cached pages are available.

## Product goal

Add one CivTools launcher tool named **Excel Report Publisher**. A user drops a folder of design calculation workbooks, and the tool produces readable PDFs with all report columns fitting the page width. Portrait and landscape can coexist in the same report. Recurring report templates should become a repeatable, low-effort publishing task.

Success means preserving calculation content, choosing sensible layouts, showing the real output, and directing attention to exceptions. Automatic layout cannot certify calculation correctness or guarantee that every unfamiliar workbook is correctly understood.

## Recommended defaults

| Setting | Default |
| --- | --- |
| Input | Files or folder; include subfolders, visibly indicated |
| Formats | `.xlsx`, `.xlsm`, `.xlsb`, `.xls`, validated separately |
| Paper | A4; A3 allowed only when enabled in the preset |
| Orientation | Automatic, evaluated per worksheet |
| Scaling | All report columns on one page wide; unrestricted vertical pages |
| Readability target | Proposed 9 pt effective body text, adjustable and calibrated against real reports |
| Content | Visible, nonempty worksheets and printable chart sheets; show all exclusions |
| Print area | Respect plausible existing areas; flag conflicts rather than silently expanding or cutting |
| Formatting | Preserve calculation layout; selectively repair well-understood defects |
| Calculation values | Publish saved results where possible; no automatic external refresh or macro execution |
| Output | One PDF per workbook, retaining relative folder structure |
| Batch behaviour | Process good files; collect exceptions without repeated dialogs |
| Originals | Read-only originals; changes occur in temporary copies |

Users can also choose a combined report or both individual and combined PDFs. A combined report retains sheet and workbook order unless explicitly reordered.

## User experience

### 1. Add reports

The initial screen contains a large drop area, Add folder, Add files, a preset selector, output folder, and **Prepare reports**. Show the default settings in a compact sentence: `A4 · Auto orientation · Fit all columns · Saved values`.

Discovery immediately shows file counts and starts populating an expandable workbook/sheet list. Ignore Excel lock files (`~$`), exclude the tool's own output/staging directories, deduplicate paths, and avoid recursive directory-link loops. Make recursive scanning a visible toggle. Display unsupported files in a summary rather than pretending they were processed.

Remember the last preset and output folder. Provide **Prepare and export** for repeat batches using established presets, with exceptions held for review.

### 2. Review the prepared report

Use a resizable three-pane workspace:

- Left: workbook and sheet tree, inclusion checkboxes, order, search, and filters for All / Needs review / Failed.
- Centre: actual PDF preview, page thumbnails, zoom, fit width, page navigation, and current versus proposed layout when requested.
- Right: settings for the selected sheet or selection, plus a short explanation of automatic decisions.

The footer keeps Export ready reports, progress, and the exception count visible. Support keyboard navigation, multi-select changes, undo/reset, and accessible text labels in addition to colours. Collapse the settings pane on small screens.

Useful messages describe the decision and the remedy:

- `Landscape chosen: portrait would reduce body text below your target.`
- `Existing print area excludes a populated block. Keep area / Include block / Edit area.`
- `Text remains too small on A4. Allow A3 / Edit report area / Keep current layout.`
- `Workbook needs a password. Enter once for this run / Skip.`

Do not require a click for each ordinary automatic adjustment. A visible reason and reversible override are sufficient. Flagged workbooks remain separate from completed outputs until resolved or deliberately exported with an exception recorded.

Settings follow this precedence: **sheet override > workbook override > batch preset > application default**. Every control indicates whether it is inherited or overridden. Applying a preset must not silently erase explicit sheet overrides.

### 3. Export and reuse

Export the exact prepared PDF after validating that its source fingerprint and settings have not changed. Do not re-render an approved preview invisibly. If either changes, invalidate the prepared result and show why it needs regeneration.

Show workbook-level progress, current stage, completed files, exceptions, and elapsed time. Support stop after current file and a separate stop-now action using the isolated worker. Completed files survive cancellation. Offer Open report, Open output folder, Retry exceptions, and Save preset.

Default collision handling creates a new versioned name. Keep the relative input folders so identically named workbooks do not collide. Do not silently replace existing issued reports.

## Layout intelligence

### A. Inspect before changing

Build a sheet inventory containing values/formulas, displayed text, number formats, fonts, row/column dimensions, hidden/filter states, merged ranges, printable shapes/charts/images, existing print areas, title rows, headers/footers, manual breaks, and worksheet protection. Identify chart sheets separately from cell worksheets.

Calculate candidate report bounds from real content and printable objects. Excel's used range is only a hint: distant formatting can produce spurious pages. Blank bordered areas, intentional spacing, signature areas, and diagrams may still belong to the report. Formula cells displaying an empty string require special handling, not blanket removal.

Existing print areas and page setup provide evidence of author intent. Retain a plausible configured layout when it meets readability requirements. An outlying data block may be working data deliberately excluded from the report; surface the ambiguity. Never delete blank rows or columns to make a report shorter.

Recognise three initial layout families: designed calculation form, continuous table, and mixed/uncertain. Use transparent rules based on merges, borders, text/number distribution, objects, and existing print settings. Sheet names alone do not justify exclusion or template matching.

### B. Choose portrait or landscape

Measure visible report width in points, not column count. For each allowed paper/orientation pair, estimate the width scale using printable width after margins, and derive estimated effective body font size. Weight ordinary body text more heavily than isolated small footnotes. These measurements shortlist candidates; they do not establish final pagination.

Choose a candidate in this order:

1. Honour explicit user locks.
2. Preserve a plausible existing orientation if it passes readability and layout checks.
3. Prefer portrait when it meets the target and keeps the calculation layout intact.
4. Use landscape when portrait shrinks content excessively or creates a clearly poorer layout.
5. Try A3 only if the preset allows it.
6. If no candidate passes, retain all content and mark the workbook for review.

Use content coverage and readability as primary criteria; treat page count, awkward breaks, excessive whitespace, and deviation from the original as secondary criteria. Avoid selecting landscape for every worksheet merely because its text could be larger.

For ordinary sheets apply Excel's width-fit settings: `Zoom=False`, `FitToPagesWide=1`, `FitToPagesTall=False`. This satisfies the user's preferred all-columns workflow without compressing an entire long calculation onto one page.

Different worksheets can use different orientations in one PDF. A worksheet containing both a narrow calculation section and a very wide table initially uses one orientation and may be flagged. Exporting independently oriented sections within one worksheet is a later feature requiring reliable section boundaries and ordered range exports.

### C. Repair formatting selectively

Preserve fonts, superscripts/subscripts, equation objects, units, borders, fills, numerical precision, and conditional formatting. Keep diagrams anchored to their associated calculations. Preserve hidden rows/columns and filters, and show their presence in inspection details.

The default repair pass may adjust page margins, orientation, scaling, and justified print bounds. Text wrapping, row-height changes, and constrained column-width adjustments apply only to confidently identified table regions or a saved template that enables them. They require a preview validation pass. Avoid global AutoFit, which can disrupt calculation forms and object placement.

Merged narrative cells, embedded/OLE objects, linked images, and protected sheets receive specific handling or an exception. Do not claim successful repair simply because Excel returned an export without error. Unsupported protected formatting can use the original layout or require the user to unlock a copy.

Repeat existing title rows. Infer new repeated headings only for clear continuous tables, recording the choice. Freeze panes are a hint, not proof of a printable heading. Preserve existing report headers/footers; add project metadata and page numbering only through an explicit publishing preset.

### D. Keep calculation blocks together

Identify candidate section boundaries using headings, borders, merged labels, whitespace, diagrams, and saved template rules. Aim to keep a heading with its first calculation rows and keep a compact equation/diagram block on one page. Blocks larger than a page remain explicit exceptions or follow a reviewed split rule.

Excel's Fit To mode can ignore manual page breaks. Therefore advanced section pagination must use a tested alternative: compute an explicit percentage zoom that still fits all report columns, apply manual horizontal breaks, render, and verify that there is no horizontal spill. Recompute the scale after any dimension change. Do not combine Fit To and manual breaks and assume both work.

If the controlled pagination path fails validation, fall back to native width-fit and flag the affected section. Treat this as a separate implementation milestone after baseline Excel rendering works.

### E. Render, inspect, and refine

Generate a temporary PDF through Excel. Check page count and dimensions, emitted text sizes where available, unexpected empty pages, edge-adjacent content, and discrepancies against the sheet inventory. Raster content, charts, and equation objects need dedicated visual fixture tests; text extraction cannot prove their completeness.

Use a bounded correction loop: chosen candidate, one alternative orientation/layout where justified, and one targeted repair. Cache outputs by source content fingerprint, effective settings, engine version, and relevant Excel/font/printer environment. Never loop indefinitely trying to perfect an ambiguous sheet.

An empty-looking signature page or a sparse calculation page is not automatically disposable. Any blank-page removal needs evidence and a recorded reason. Confidence is an explainable rule outcome, not an invented probability of correctness.

## Calculation and data fidelity

The default should publish saved calculation results. Open originals read-only, stage copies, set manual calculation before opening, suppress link updates, and avoid refreshing connections or invoking workbook macros. Preserve relative paths when staging related workbooks. VBA security controls do not block every legacy macro mechanism or every refresh-on-open connection, so preflight and handle unsupported automation cases explicitly.

Compare available pre-open cached results with the loaded/exported snapshot. Mark missing or changed caches, formula errors, external links, unavailable add-ins/UDFs, and refresh dependencies. Excel may still alter values in some opening scenarios; the product must not promise an absolute saved-value guarantee for every workbook format.

An optional **Recalculate before export** mode must explain that it can change results, wait for calculation completion, report changed/error values, and avoid implicit external refresh. Macro-dependent workbooks should normally be calculated and saved by their owner before publishing. Layout intelligence never changes formula expressions or engineering inputs.

## Output and report assembly

Initial deliverables are one PDF per workbook, optionally per sheet, plus an export summary mapping source files and selected sheets to their output. Record source fingerprints, settings, exclusions, exceptions, page ranges, and timestamps for repeatability.

Combined-report support adds workbook and sheet bookmarks, editable report order, optional cover and contents pages, and optional continuous page numbering. Preserve mixed page sizes/orientations. Reserve space for new footer content before rendering rather than stamping over calculations. Contents page offsets require an assembly pass that accounts for the final front matter. Flag incomplete combined reports clearly; never present omitted failed files as a complete package.

## Architecture within CivTools

Use the existing PySide6 styling, independent tool window, saved-state conventions, and launcher integration. The report window needs a large preview workspace rather than the STAAD compact palette layout.

Suggested new modules:

| Module | Responsibility |
| --- | --- |
| `qt_report_publisher.py` | Queue, tree, preview, settings, progress and exceptions |
| `core/report_models.py` | Immutable inventories, resolved settings, layout plans and results |
| `core/report_discovery.py` | Folder scan, filters, source identities and collision planning |
| `core/report_inspection.py` | Report bounds, object inventory and template evidence |
| `core/report_layout.py` | Pure candidate scoring and layout/repair plans |
| `core/report_excel_worker.py` | Dedicated process owning Excel COM and staged workbooks |
| `core/report_validation.py` | Source invariants, rendered-output checks and issue records |
| `core/report_assembly.py` | PDF merge, bookmarks, contents and publication |
| `core/report_presets.py` | Versioned presets, overrides and reusable sheet-template rules |

Use desktop Excel as the rendering engine through the project's existing `pywin32` dependency. Require installed desktop Excel for the first release; show an actionable prerequisite message before a batch begins. Do not silently substitute a different renderer with different output fidelity.

Run Excel in a dedicated child process with a privately owned application instance, serial workbook operations, watchdog timeouts, and bounded retries. Do not use the existing CAD queue or attach to a user's open Excel session. Track the Excel process identity so cleanup can terminate only the instance created by CivTools. Recycle that instance after failures or resource thresholds.

Extend the existing single-process PyMuPDF service for preview, validation and assembly. Keep large page rasterisation off the UI thread, render visible thumbnails lazily, and prioritise the selected report. Discovery may run concurrently; Excel calls remain serial. Reuse rendered output whenever possible instead of exporting again at publication time.

Publish staged PDFs atomically after validation; retain prior outputs on failure. Persist a job manifest to support retry/resume after interruption. Defer blanket multiprocessing of Excel instances until profiling demonstrates a need and integration tests establish stability.

## Build sequence and completion gates

| Phase | Build | Completion gate |
| --- | --- | --- |
| 1. Rendering proof | Representative workbook corpus, isolated Excel worker, mixed-orientation native export, cache/value inspection, PDF preview | Actual Excel integration preserves the agreed fixture content and source hashes; no user's Excel session is affected |
| 2. Core product | Folder discovery, workbook/sheet selection, inheritance, A4 auto orientation, width-fit, real preview, individual PDFs, progress/cancellation/retry | Folder-to-PDF workflow works end to end in the packaged app; failures do not stop other files |
| 3. Intelligent layout | Bounds detection, readable candidate selection, selective repairs, title detection, bounded render checks, explicit-zoom section pagination | Agreed difficult fixtures pass rendered checks or surface useful exceptions; no silent content removal |
| 4. Report publishing | Combined reports, ordering, bookmarks, optional covers/contents, numbering, saved template rules | Published page map matches preview and contents; mixed page geometry and incomplete batches are handled correctly |
| 5. Release hardening | Large batches, crashes/timeouts, resume, protected files, long/non-ASCII paths, fonts/printers, all advertised formats | Packaged Windows build passes the acceptance matrix and measured resource/performance budgets |

Release the full intended feature after these gates. The native rendering proof is the first engineering task, before investing in extensive UI polish. Validate the critical output fidelity assumptions early.

## Validation and acceptance

Assemble about 15–25 representative, sanitised workbooks covering portrait calculations; landscape tables; mixed orientations; merged narrative text; superscripts/Greek symbols; embedded equations; charts and diagrams; wide result tables; intentional blank/signature areas; damaged used ranges; configured print areas; manual breaks; hidden/filter states; external links/UDFs; protected files; and all supported Excel formats. Include multiple workbooks sharing a base filename.

Meaningful tests comprise pure layout/precedence tests, real Excel export integration, visual and semantic comparison against reviewed PDF fixtures, and UI tests for batch controls and exception recovery. Mocks alone cannot validate Excel rendering. Maintain tolerances for font/printer/version differences, and record the tested environment.

Required acceptance checks:

- Original workbook hashes and engineering formula/input data remain unchanged.
- All selected sheets are accounted for, in the chosen order; no silent omission.
- Accepted width-fit reports have no horizontal continuation pages.
- Portrait/landscape selection respects locks and permitted paper sizes.
- Calculation text, values, units, diagrams and equations match reviewed fixtures.
- Readability failures and ambiguous content areas appear as exceptions rather than quiet successes.
- The previewed artifact is the published artifact for the same source/settings snapshot.
- Passwords, corrupt files and stalled automation produce bounded failures and allow the batch to continue.
- Cancellation and crashes retain completed files and preserve previous output versions.
- Memory stays bounded with lazy previews and sequential workbook processing on a batch of at least 100 representative files.

Measure preparation time, export time, memory, page count, exception rate and correction frequency on that corpus. Establish performance targets from actual measurements rather than promising a fixed seconds-per-file rate. Tune automatic formatting against that corpus before widening its scope.

## Reference assessment

The linked [fulvian/exc-to-pdf repository](https://github.com/fulvian/exc-to-pdf) describes a NotebookLM-oriented pipeline using openpyxl, pandas and ReportLab, with table detection and PDF bookmarks. Its README is useful inspiration for navigation and structured extraction. Source-file retrieval was unavailable during this review, so no code-level validation or quality assessment is claimed.

For this product, the recommendation is an independent Excel-native rendering implementation. Reconstructing tables does not establish fidelity for designed calculation forms, embedded equations, charts, and authored print layouts. If any third-party code is later reused, inspect and test that code and retain its required licence attribution.

Supporting platform references:

- [Excel PageSetup](https://learn.microsoft.com/en-us/office/vba/api/excel.pagesetup) and [FitToPagesTall](https://learn.microsoft.com/en-us/office/vba/api/excel.pagesetup.fittopagestall): page layout and width-fit behaviour.
- [Workbook.ExportAsFixedFormat](https://learn.microsoft.com/en-us/office/vba/api/excel.workbook.exportasfixedformat): native PDF publication.
- [Microsoft's worksheet scaling guidance](https://support.microsoft.com/en-gb/excel/scale-a-worksheet?nochrome=true): Fit To ignores manual page breaks.
- [Workbooks.Open](https://learn.microsoft.com/en-us/office/vba/api/excel.workbooks.open): read-only opening and external-link update controls.
- [AutomationSecurity](https://learn.microsoft.com/en-us/office/vba/api/excel.application.automationsecurity): programmatic macro settings and legacy macro limitations.
- [Range.AutoFit](https://learn.microsoft.com/en-us/office/vba/api/excel.range.autofit): row/column sizing behaviour.
