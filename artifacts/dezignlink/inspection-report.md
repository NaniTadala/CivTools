# dEZignLink v3.2.1 inspection and CivTools feasibility

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
