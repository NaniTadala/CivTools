# Report Publisher visual review

The reports shown in these screenshots are synthetic layout fixtures.

- `empty.png`: clean starting state, 1000 × 700.
- `prepared.png`: real Excel PDF preview, 1000 × 700.
- `compact.png`: real PDF preview, 780 × 540, with no horizontal scrolling in Fit width.
- `settings.png`: compact Layout / Export / Advanced settings dialog.
- `combined-prepared.png` and `combined-compact.png`: automatically assembled six-page report with page thumbnails and toolbar combined-mode toggle.

Regenerate using `python scripts/preview_report_publisher.py` with installed Excel and local child processes permitted. `--reuse` recaptures prepared artifacts from the previous visual-review session.

Review covered empty and populated layouts, filename space, preview resizing, status indicators, dialog cancellation and export-only changes retaining prepared PDFs.
