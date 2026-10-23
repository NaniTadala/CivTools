# dEZignLink v3.2.1 inspection and CivTools feasibility

## Suite implementation and migration: 20 October 2026

The subsequent user request authorized implementing the remaining tools, then
specifically required moving the complete existing parameter generator and rack
modeler under the suite. The launcher now has four cards; **Dgn Prm** owns the
existing concrete/steel editor, presets, validation and output preview, with an
additional automatic-lengths/joints tab. **Pipe Rack** owns the complete previous
modeler, saved configurations, preview and live generation, plus standalone STD
export. Previous form settings remain readable. Legacy navigation redirects to
these suite windows rather than creating additional standalone utilities.

### Documented workflows implemented

| Tool | Local implementation and output |
| --- | --- |
| Renum | Confirmed floor/category numbering; default first-floor beams1001, columns1501 and braces1751, with larger blocks for crowded floors. Full reviewed mapping, backup, temporary collision-free IDs and incidence verification. Guide pp8–9 describes floor/category patterns but not the exact remote algorithm. |
| Groups | Predefined `_RB` CND/MEM/FLR/PRI_BM/SEC_TER_BM/PLN_BRC/VER_BRC and level sets, plus column/roof sets. Replaces exact generated names while preserving unrelated groups, with backup and readback. Guide pp10–11. |
| Releases | Uses the actual STAAD member selection. START/END and local DOFs are chosen in a compact dialog; only exterior analytical ends of complete supported physical beam chains are assigned. Invalid or incomplete selections have explicit skip reasons; changed selection after review blocks assignment. Guide pp12–13. |
| Dgn Prm | Full prior generator migrated, plus automatic column/beam restraint candidates and DJ1/DJ2 preview/copy/save/Assign. Two evidenced dialects are exposed: IS800:2007 LY/LZ/LX and IS800:1984 LY/LZ/UNL. Assign backs up, saves, closes/reopens the STD, adds a numbered block and restores units. Guide pp14–15. |
| Tables | Available/selected primary/combination load-case lists. Reaction, per-level displacement and pedestal XLSX exports; true populated refreshable PivotTables, signed min/max summaries, controlling cases and horizontal/3D resultants. Pedestal inputs remain editable spreadsheet formulas; torsion is retained. Guide pp15–17. |
| Load Comb | LOAD_COMB XLSX template/import or CSV input; genuine DOCX containing primary-case and combination STAAD scripts and formatted tables. IDs, symbols, load types and signed user factors are preserved. Guide pp18–20. |
| Plate Girders | 142 dimension families from the earlier observed local catalogue, with independently calculated rectangular-plate properties and optional user-defined sections. Exports a STAAD WIDE FLANGE USER TABLE. Guide pp20–21. |
| Pipe Rack | Complete prior rack tool migrated, including live blank-model generation; additional geometry-only STD export preserves its entire grid/tier/foundation/bracing configuration. |
| PEB A–D | Enabled dimensional wizards with original sketches, metric/inch inputs, frame/tie/purlin spacings, height or slope where applicable, and internal-column spacings for C. Standalone STD geometry outputs. Guide pp22–23 and installed UI metadata. |

### Evidence and limits

REA again confirmed the same installed executable SHA-256 documented below; its
native session was closed. Existing static metadata supplied labels and input
contracts for defRelWin, desParamsWin, dataTblWin, pipeRackWin and pebStrWin. No
vendor endpoint was invoked and no vendor account data was used. The algorithms
are independent implementations, not recovered server code. Geometry output,
exact numbering and full design-code equivalence remain unproven.

Installed Bentley help supplied primary design-parameter evidence:

- `C:/Program Files/Bentley/Engineering/STAAD.Pro CONNECT Edition/Help/GUID-C64E85CD-332E-44C1-B783-A5B8D0050102.html`,
  D8.A.4: `CODE IS800 LSD`, LY/LZ/LX for IS800:2007.
- `C:/Program Files/Bentley/Engineering/STAAD.Pro CONNECT Edition/Help/GUID-19E1572B-70F6-4F9D-BF10-398359C19D80.html`,
  D8.B.4: `CODE INDIAN`, LY/LZ/UNL for IS800:1984.

Other automatic code dialects are not exposed without evidence. The retained
vendor response previously labelled IS800 actually contains CODE INDIAN. Length
outputs remain geometry-based restraint candidates, not code-compliance checks;
nonorthogonal beta orientations require manual review. Parameter assignment
preserves earlier CHECK CODE blocks and does not invent a new design invocation.
Release inference deliberately skips cantilevers, tertiary and ambiguous chains.
Excel pivot XML, caches, relationships and workbook reopening are tested; actual
Excel application refresh and live model-changing operations were not exercised.

Dialog surfaces, checkbox labels and list colors are now explicit, so native dark
Windows palettes do not produce dark text on dark dialog backgrounds. A dark-
palette release-dialog check verifies background, text and button contrast.

Validation includes the new core planners, exports, workbook/pivot structures,
all 13 suite windows, preserved generator settings/presets/live-runner delegation,
confirmation/selection checks and dashboard routing. The full existing suite was
also run. The project virtual environment lacked OpenSTAAD; the already-installed
pure Python 26.0.1.14 distribution was repackaged locally and installed there without
changing its code or downloading a different implementation. A pre-existing
missing-property-type channel/angle fallback in the migrated generator was also
corrected using the existing regression test.

Final regression command: `.venv/Scripts/python.exe -m unittest discover -s tests`
with Qt offscreen and reduced motion. **All 148 tests passed**, including the
isolated PDF renderer, existing CAD-service tests, complete tool migration,
generated DOCX/XLSX/STD files and dark-palette dialog contrast. Tests of the new
model-changing operations use mocked COM rather than modifying the user's model.

---

## Selection follow-up: 20 October 2026

The current task compared the Select workflow with the user-supplied
`Dezign link User Guides & Resources.pdf`, the already-open client, and the
running STAAD model. This supplements the original historical inspection below.

### Evidence and boundaries

- REA `open_binary` confirmed the installed client still has SHA-256
  `d700fa2cc24fabfd2b0afecddba608d190050d593bc356085837d680d6913aaa`.
  The REA native session was closed after inspection.
- REA's Frida provider could not load its Node binding. The existing Python
  Frida helper was used instead, with approved process access. This is ordinary
  runtime introspection, not REA-produced runtime Evidence. It inspected only
  the engineering functions and selection-call bytecode, made no app actions or
  vendor network requests, and detached. The bounded observation is retained in
  `selection-runtime-inspection.json`; the probe is `probe-selection-inspection.py`.
- Runtime code references cached `memGroupsDict` and `selMemDict` before
  `SelectMultipleBeams`/`SelectMultipleNodes` (module offsets 8314–8788) and
  clear/reselect operations for deselection (8950–9154). The separate `smProc`
  function references saved-model processing and `serverCall`. This establishes
  the client code path, not the remote classification algorithm or a timing
  measurement of a user's Dezign Link click.
- A later attempt to compare cached vendor category IDs could not run because
  the previously observed client PID was no longer present. No cached vendor
  classification output was acquired, so the counts below are CivTools results.
- Guide pp. 5–7 documents processing once, enabling categories present in the
  model, toggling multiple categories, and processing again after geometry edits.
  It describes column-to-column primary beams, roof rafters and inclined-plane
  roof braces. The requirement to restrict primary beams to columns rooted at
  supports comes from the user's explicit correction.

### Corrections and comparison

| Selection behavior | Result |
| --- | --- |
| Process once, toggle cached groups | Full geometry/load-case scans and classification now run during processing. Toggles check the active model path, entity counts and saved-file signature, then update selection. They do not rebuild other feature tables. |
| Main columns / primary beams | Vertical connectivity from support nodes identifies main column stacks. Straight split horizontal chains must connect main stacks at both ends. Floating columns cannot promote beams to primary. |
| Vertical bracing | Frame-attached XY/YZ inclined members, including split braces, now receive this category. Previously the classifier never emitted it. |
| Rafters / rafter bracing | Roof chains between supported column tops and diagonals in identified roof planes now receive the corresponding categories. Eave connections do not merge a brace with a rafter chain. |
| Multiple categories and absent groups | Checked groups combine with overlap preserved. Categories absent from the processed model are disabled. |
| Minimal controls | Select has model name, Process Members, category buttons and status. Process Members uses the accent style; other buttons use neutral checked borders. The console remains hidden on errors and completion. |

Geometry inference remains conservative for skew vertical frames and unusual
roof topology. The guide does not specify a complete classification algorithm;
exact vendor algorithm equivalence and equivalence of the other suite features
are not established by this follow-up. Reprocess after unsaved geometry edits;
changes preserving entity counts cannot be detected by the inexpensive toggle
checks alone. Model-changing and export workflows retain their full validation.

### Live validation

The running model `410-PR-01 Stretch- F.STD` contained 1,397 nodes and 2,417 members.
The corrected classifier identified 402 column members, 519 primary beam members
(282 X / 237 Z), and 144 vertical braces. These are geometry-based categories,
not independently checked structural design roles.

Profiling isolated an additional STAAD delay: its normal clear-selection call
took about 1.7–2.1 seconds for 402–519 selected members. Redraw batching helped,
and a verified select-all/invert operation removed that per-member clear delay.
The implementation uses the documented inverse-selection operation (OpenSTAAD
guide p. 346), avoids the Python wrapper's automatic zoom, and falls back to
normal clearing if the batch result is not empty. It reenables redraw in a
`finally` block and verifies the final IDs.

The final measured six select/deselect operations took **24–96 ms**. Processing
read the model in about 565 ms and classification took about 9 ms in that run.
The full trace and restoration checks are in `selection-benchmark.json`, with
the reproducible probe in `benchmark-selection.py`. Original selection was
restored and the saved model's SHA-256 was unchanged. Thirty-six focused tests
passed, including classification, cached toggles, inverse fallback, redraw
restoration, hidden console, and productivity workspace workflows.

---

Inspection date: 15 October 2026. Scope: the supplied installed application at
`C:\Root Bridge Technologies\dEZignLink for STAAD.Pro` and the current CivTools source.

## Finding

A functionally similar tool can be implemented inside CivTools. Exact behavioral
equivalence cannot be established from this installation: important processing is
delegated to a remote service whose implementation is absent from the client.
The installed program is an automation/helper suite around STAAD.Pro, rather than
an independently observed structural analysis solver.

This is an investigation and implementation proposal. No feature has been added
to CivTools, no target program was launched, no vendor endpoint was called, and no
STAAD model was modified. Stored account/session values were not read.

## Evidence and method

| Reference | Source and observation | Coverage |
| --- | --- | --- |
| REA PE | `inspect_pe_resources`, Evidence `ev_bef12c4cf5425be3e88fe02c255fe8ff30828de8eb70d140d735ba64483c8668` | Complete static PE resource tree: x64 PE32+, 8,845,906 bytes. Executable SHA-256 `d700fa2cc24fabfd2b0afecddba608d190050d593bc356085837d680d6913aaa`. |
| REA DB | `inspect_sqlite_database`, Evidence `ev_a0e67cd53da462f5792f6bef484f3d5ee3cad5ccfbef171a2489746c94eb4cf8` | Complete schema inventory, no data rows requested. Original structured Evidence retained in `rea-database-schema.json`. |
| Python package | Local PyInstaller `CArchiveReader` and the execution-free Python 3.9 marshal reader in `scripts/inspect_dezignlink.py` | Main entry `dEZignLink_v3.2_uc`, 96,441 uncompressed bytes, consumed completely; 99 nested code scopes. Scope names, referenced names, selected strings and limited remote-call instruction windows retained in `static-metadata.json`. These are shell-derived observations, not REA Evidence. |
| Illustrations | Visual inspection of installed `imgPebA.png` through `imgPebD.png` | Packaged explanatory drawings only; generated topology and numbering not verified. |
| CivTools | Read-only inspection of source registry, pages, jobs and core services | Integration feasibility; no live STAAD interoperability test. |

REA `open_binary` identified the executable and its digest. Native overview was
unavailable: Ghidra and IDA were not configured, and Hopper does not support this
Windows host. The native session was closed. No native decompilation is claimed.
The package contains `python39.dll`, a PYZ with Python 3.9 magic `610d0d0a`,
PySimpleGUI/Tkinter, COM libraries, SQLAlchemy and spreadsheet/document libraries.

The custom reader builds neutral metadata dictionaries, never executable code
objects. It is a narrow inspection helper for this identified artifact, not a
general-purpose decompiler. Literal names alone do not prove executed behavior.
Call-site instruction sequences corroborate the main remote processing boundary.

## How it works

1. A PySimpleGUI/Tkinter toolbar dispatches separate feature windows. Helpers use
   COM initialization and `GetActiveObject('StaadPro.OpenSTAAD')` to access the
   active STAAD model's geometry, properties, supports and output interfaces.
2. Model-related processing reads the saved `.std` using `open(..., 'r')` and
   `readlines()`. Calls such as `smProc` pass that entire line list to `serverCall`.
   `serverCall` builds a payload from positional arguments and invokes a requests
   session's `post(url, json=payload)`. This is static code evidence of intended
   transmission; no network transmission was observed during this investigation.
3. The remote response supplies member classifications, processing plans,
   design-parameter data, or generated file contents. Login/subscription handling
   is present. Credentials, cookies and account implementation are outside scope.
4. Local code applies returned selections, groups, releases and renumbering using
   OpenSTAAD, or writes generated STAAD command files and reports. Parameter
   assignment includes closing/reopening and rewriting the saved STAAD file, with
   text-export fallback. This path has not been exercised.
5. SQLAlchemy/SQLite stores per-file cached geometry and feature data. The
   `results` table has `std_file`, `mem_inc`, `node_coords`, `units`, `beta`,
   `access_date`, `sel_mem`, `def_rel`, and `dat_tbl` columns. The `settings` table
   contains output-path and account-session fields; only its schema was inspected.
   Cache invalidation/model-change helpers exist, but completeness is unverified.

## Feature inventory

The following are observed client workflows and labels, not claims of successful
execution or complete algorithm recovery. Source-line numbers are embedded
compiled-code metadata, not accessible original source files.

| Feature | Static anchors | Local behavior and remote dependency |
| --- | --- | --- |
| Member selection | `selMemWin` line 683, `smProc` line 1887 | Categories for columns, primary/secondary beams, X/Z directions, vertical/plan bracing, rafters, rafter bracing, support nodes and level selections. `sel_members` receives saved model lines plus `processMembers`; classification is returned remotely. Local selection uses OpenSTAAD. |
| Renumbering | `rnProc` line 1958 | `renum_members` returns the plan; local `RenumberBeam` and `SaveModel` apply it. UI includes backup handling and restrictions for plates, solids and physical members. Exact numbering rules are unknown. |
| Groups | `gmProc` line 2054 | `grp_members` returns grouping data; local `CreateGroupEx`, `DeleteGroup` and `SaveModel` apply it. Member/node/floor grouping labels and `_RB` naming fragments are present. |
| Releases | `defRelWin` line 863, `drProc` line 2178, `defineReleases` line 2249 | `def_releases` processes saved model lines. Local start/end release assignment offers FX/FY/FZ/MX/MY/MZ controls; geometry-based processing rules remain remote. |
| Design parameters | `desParamsWin` line 945, `dpProc` line 2303 | `des_params` receives model lines and selected design code. Client exposes column/beam LY/LZ and code-dependent LX, UNL or LT labels, plus beam DJ1/DJ2. Supported code list itself is requested remotely; no exhaustive list established. |
| Analysis tables | `dataTblWin` line 1108, `getLoadCases` line 2378, `genDataTbl` line 2466 | Remote `data_table` assists model/load-case/node selection. Actual support reactions and node displacements use local OpenSTAAD output calls. Selected load cases feed Excel exports and pivot summaries. |
| Pedestal forces | `genDataTblFile` line 2562 | Workbook includes pedestal dimensions, height, self-weight and force/moment transformations. Workbook text states torsion is excluded. No unit/sign or engineering validation performed. |
| Load combinations | `ldCmbTemp` line 2796, `ldCmbProc` line 2909 | Excel `LOAD_COMB` input/template with case numbers, combination numbers, load symbols/types and factors; `gen_loadComb` supplies processing/output. Local code builds a Word document. Exact factors and supported types are unknown. |
| Plate girders | `pltGrdrsProc` line 3052 | `gen_pltgrdrs` returns a filename and STAAD-compatible command text for manual insertion. Section catalogue and generation rules are not present in this call site. |
| Pipe racks | `pipeRackWin` line 1319, `prProc` line 3082 | Local validation covers width, frame count/spacing, tier and longitudinal beam spacing lists, and matching total heights. `gen_pipeRack` receives six geometry/unit arguments and returns output-file data. |
| PEB structures | `pebStrWin` line 1398, `pebProc` line 3171 | Four illustrated variants: A gable frame, B gable with centre/ridge columns, C gable with two internal column lines, D single-slope roof. Width, column/ridge height or slope, frames, frame spacing, tie-beam/purlin spacing, units and variant are sent to `gen_pebStr`. Final member layout, numbering and endpoint placement rules remain unknown. |

Spreadsheet export references both XlsxWriter/OpenPyXL and Excel COM; pivot-table
creation uses Excel COM. The client checks for Excel and Word installations in
relevant flows. Installed dependencies alone do not establish all supported uses.

## Proposed CivTools integration

Add one tool card named **STAAD productivity suite**, opening a native Qt page
with tabs for Model tools, Design parameters, Results, Load combinations and
Structure generators. This is a proposed design, not recovered vendor UI.

Reuse these existing components:

- `src/civtools/core/staad_parameters.py`: `StaadService` model reading and
  existing concrete/steel parameter and DJ generation. Algorithmic equivalence
  to dEZignLink has not been established.
- `src/civtools/core/piperack.py` and `core/geometry.py`: current pipe-rack
  generation/geometry planning. Vendor rack inputs use spacing lists; CivTools
  uses grids and absolute tier elevations, so an explicit input conversion is needed.
- `src/civtools/jobs.py`: `Job(cad=True)` serial COM queue and worker reporting.
- `src/civtools/qt_pages.py`: `ToolPage` progress, logs, settings and window state.
- `src/civtools/qt_app.py`: `TOOLS`, navigation factory and utility sizing maps.
  New keys also need page title/state maps and icon/artwork registration.

Suggested implementation order:

1. Local model snapshot, documented member classification, selection/group tools,
   and reuse of existing parameter previews. Establish a small model fixture set
   covering units, sloping/rotated members, releases, offsets and discontinuities.
2. Local reactions/displacements exports, envelopes and pedestal workbook with
   explicit units, axes, signs and formulas validated against STAAD output.
3. PEB A-D geometry plans and previews, reusing the pipe-rack planning approach.
4. Explicit release/renumber plans with backup and review; load-combination and
   plate-girder generation from independently specified rules/catalogues.

Implement the engineering processing locally from documented requirements.
Wrapping the vendor executable or reusing its private endpoints would retain its
installation/server/account dependencies and would not supply the missing algorithms.
Original Qt artwork and application code can provide the same workflow categories.

## Checklist and unresolved questions

| Question | Status |
| --- | --- |
| Identify executable/framework and package layout | Answered by REA identity/resources and local package inspection. |
| Explain STAAD connection and main data flow | Answered statically; runtime not observed. |
| Inventory user-facing workflows | Answered at client UI/call-site level; runtime coverage and remote code lists incomplete. |
| Identify local cache and outputs | Answered at schema/code-reference level; generated files not exercised. |
| Determine CivTools integration feasibility | Answered architecturally; existing code is reusable. |
| Recover exact classification, numbering, parameter and generator algorithms | Unresolved: important server implementation is absent. |
| Prove output/engineering equivalence | Unresolved: requires expected outputs from controlled sample models, unit/sign verification and feature-specific comparisons. |

The installation alone does not justify promising an exact clone. A standalone
CivTools equivalent is technically feasible, with the above gaps treated as
requirements and validation work rather than assumed behavior.
