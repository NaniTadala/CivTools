# STAAD floating suite visual audit

Completed 23 October 2026. All 13 tools, including PEB A-D, were captured in 41
states across eight configurations: **328 screenshots**. Screenshots and contact
sheets were reviewed, with detailed inspection of the parameter editor, table
headers, numeric fields, menus, dialogs, review controls and narrow layouts.

## Updated editor

[Compact parameter editor](light-1/parameters.png) | [Steel editing](light-1.25/parameters-editing.png) | [Narrow steel editor](dark-1.5/minimum-width-steel.png) | [Expanded editor](light-1/parameters-expanded.png)

## Corrections made

- Compact parameter tables fit Use, Parameter and Value without a horizontal
  scrollbar. The selected scope appears below; description remains available
  as a tooltip. Expand restores Scope and Description columns.
- Short, complete tab labels fit inside the panel. Long parameter names wrap.
- Table padding and row heights leave room for the full font height.
- Explicit palette and form backgrounds prevent native dark strips and dark
  scrollbar tracks. All 123 corresponding light/dark state pairs are
  pixel-identical; see [comparison output](palette-comparison.json).
- Pipe-rack numeric fields display their values. Step arrows are visible.
- Parameter editing preserves small values such as 0.002, instead of using
  Qt's default two-decimal spin editor.
- Member tables adapt their visible columns to the panel width. Headers fit.
- Result-type selection and a fixed Export Excel action keep export controls
  in view. Other export actions use the same footer position.
- Populated case lists use deliberate ellipses with full-text tooltips.

## Capture matrix

Offscreen scale factors are 1, 1.25 and 1.5. Native captures use the Windows Qt
platform with scale multipliers 1 and 1.5 in addition to the host's DPI setting.
Native captures are widget snapshots, without OS title bars.

| Configuration | Captures | Width-check issues | Contact sheets |
|---|---:|---:|---|
| dark-1 | 41 | 0 | [1](dark-1/contact-1.png) [2](dark-1/contact-2.png) [3](dark-1/contact-3.png) [4](dark-1/contact-4.png) [5](dark-1/contact-5.png) [6](dark-1/contact-6.png) |
| dark-1.25 | 41 | 0 | [1](dark-1.25/contact-1.png) [2](dark-1.25/contact-2.png) [3](dark-1.25/contact-3.png) [4](dark-1.25/contact-4.png) [5](dark-1.25/contact-5.png) [6](dark-1.25/contact-6.png) |
| dark-1.5 | 41 | 0 | [1](dark-1.5/contact-1.png) [2](dark-1.5/contact-2.png) [3](dark-1.5/contact-3.png) [4](dark-1.5/contact-4.png) [5](dark-1.5/contact-5.png) [6](dark-1.5/contact-6.png) |
| light-1 | 41 | 0 | [1](light-1/contact-1.png) [2](light-1/contact-2.png) [3](light-1/contact-3.png) [4](light-1/contact-4.png) [5](light-1/contact-5.png) [6](light-1/contact-6.png) |
| light-1.25 | 41 | 0 | [1](light-1.25/contact-1.png) [2](light-1.25/contact-2.png) [3](light-1.25/contact-3.png) [4](light-1.25/contact-4.png) [5](light-1.25/contact-5.png) [6](light-1.25/contact-6.png) |
| light-1.5 | 41 | 0 | [1](light-1.5/contact-1.png) [2](light-1.5/contact-2.png) [3](light-1.5/contact-3.png) [4](light-1.5/contact-4.png) [5](light-1.5/contact-5.png) [6](light-1.5/contact-6.png) |
| native-dark-1 | 41 | 0 | [1](native-dark-1/contact-1.png) [2](native-dark-1/contact-2.png) [3](native-dark-1/contact-3.png) [4](native-dark-1/contact-4.png) [5](native-dark-1/contact-5.png) [6](native-dark-1/contact-6.png) |
| native-dark-1.5 | 41 | 0 | [1](native-dark-1.5/contact-1.png) [2](native-dark-1.5/contact-2.png) [3](native-dark-1.5/contact-3.png) [4](native-dark-1.5/contact-4.png) [5](native-dark-1.5/contact-5.png) [6](native-dark-1.5/contact-6.png) |

## Validation

- 20 productivity UI tests passed.
- 10 workflow migration tests passed.
- Four workspace checks passed: construction/state retention, member selection,
  reviewed changes/cache invalidation and design-parameter generation settings.
- Eight additional checks passed across 125% and 150% scaling: parameter layout,
  visible numeric editors, table headings and small-value preservation.
- Screenshot metrics found no undersized button captions, numeric editor widths
  or visible table headings. Each capture directory contains metrics.json.
- Source whitespace checks passed.

Tables and long forms retain normal scrolling; a partially visible row at a
scroll boundary is expected. Model geometry and review data in these captures
are illustrative. No live STAAD model was changed, and this audit does not
validate COM behavior or the packaged executable.

## Reproduce

From the repository root:

```powershell
python artifacts/audit_productivity_ui.py --theme dark
$env:QT_SCALE_FACTOR = '1.5'
python artifacts/audit_productivity_ui.py --theme light
python artifacts/audit_productivity_ui.py --theme dark --native
```

The script uses an isolated settings directory, performs no COM calls and exits
with a failure status when its text-width checks find an issue.
