# Publisher text and icon audit

`scripts/audit_report_publisher_text.py` measures visible button, checkbox, combo-box and label content against available space and captures workspace/settings screenshots.

Verified at 760 × 500 and 1000 × 700, application text sizes 100%, 115%, 130%, and display scale factors 1.0, 1.25, 1.5. No control text overflow was detected. The captured preview stress fixture is a blank page used for typography checks; real Excel report screenshots are in `../publisher-polish/`.

Dynamic filenames, selected-sheet captions and operation messages use deliberate ellipses and complete-text tooltips. The Settings button is text-only; page navigation and overflow controls use matching vector strokes instead of platform-dependent icons or font glyphs.

Publisher regression tests: eight passed, including native Excel exports. Rebuilt executable smoke test: passed.
