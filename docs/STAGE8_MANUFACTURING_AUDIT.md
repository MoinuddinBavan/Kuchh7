# Stage 8 manufacturing calculation audit

**Status: validated for synthetic profiles only. No client-approved cabinet specification was supplied.** The original kitchen projects and their construction results are unchanged unless an employee explicitly applies a versioned profile to an individual cabinet.

## Existing engine before Stage 8

| Capability | Finding |
| --- | --- |
| Cabinet families | Existing catalogue contains base, drawer, sink, wall, open shelf, tall and other demonstration types. The six-cabinet kitchen exercises the six requested families. |
| Panel formulas | Implemented with generic illustrative constants in `bom.py`; never factory approved. |
| Hardware | Two concealed hinges per door and one runner pair per drawer in the legacy BOM. Separately assigned fittings are reconciled by the costing service. No approved hinge, runner, handle or bracket schedule exists. |
| Material | Cabinet finish is used for carcass and fronts; drawer board is a separate demonstration material. |
| Edge banding and grain | Previously absent. Stage 8 records explicit profile assignments; unspecified edges and grain remain unspecified. |
| Cutting and nesting | Existing panel rectangles from the BOM; nesting is a sheet-packing illustration without approved yield or toolpaths. |
| DXF | Existing millimetre-scale elevations, panel outlines and one-file Complete Kitchen drawing. Machine import remains unverified. |
| Costing and quotation | Existing panel-area and hardware-rate workflow; rates must be configured. Issued quotation snapshots are not changed by this stage. |

## Selected construction profile

A cabinet's optional `construction_profile` JSON stores the entire profile snapshot, including `profile_id`, `revision`, cabinet type, `DEMO / NOT FACTORY APPROVED` status, dimensional clearances, thicknesses, back/shelf inclusion, edge rules, grain rules, panel material assignments and explicit hardware quantities. Missing required profile fields raise an error. Unsupported fitting arrangements raise an error rather than falling back to a guessed factory rule.

The currently implemented fitting arrangement is **top and bottom between full-height sides**. The back may be omitted or inset by an explicit offset. Carcass board thickness remains the cabinet's editable board thickness. Adjustable shelf and fixed shelf distinctions, plinth construction, side offsets, overlay backs, hardware drilling and joint machining remain undefined until the client supplies specifications.

For an explicitly selected profile, generated parts continue through the single authoritative `generate_bom` / `generate_project_bom` path. Existing projects with no profile use the unmodified legacy formulas. The synthetic profile generator in `construction.py` is test data only. It omits the sink cabinet back and shelf to demonstrate a type-specific rule; it is **not** a claim that the client's sink cabinets omit them.

### Dimensional conventions

- Length and width in the BOM are **finished panel rectangles**. Panel area is finished length × finished width × quantity / 1,000,000 m².
- `cut_length_mm` and `cut_width_mm` are the cut rectangle. They equal finished dimensions unless the explicit `compensate_cut_for_banding` flag is set and edge rules define the compensation.
- `front` and `back` edge lengths follow the panel's length axis; `left` and `right` follow its width axis. Banding totals multiply each assigned edge length by panel quantity.
- Compensation subtracts the specified band thickness from the corresponding cut axis. This convention is a configurable demonstration example, **not an approved banding or trimming process**.
- Nesting receives cut rectangle sizes, material, thickness and grain direction from each BOM component. Directional grain prevents 90° part rotation; physical sheet grain direction and grain matching are not yet modelled or verified.
- Cabinet placement rotation changes only kitchen placement. It does not alter panel grain metadata.

## Traceability and reconciliation

The cut list keeps a stable cabinet-specific `C#-P##` ID, BOM row number, project, wall assignment and note, profile ID/revision, material, finish, finished and cut sizes, quantity, grain and edge assignments. It keeps rows separate by cabinet and part, so equal rectangles with incompatible specifications are never collapsed. Wall association uses the existing Stage 7.1 drawing grouping heuristic and reports ambiguous or unassigned cases.

The synthetic six-cabinet fixture produced **47 BOM rows, 42 cut-list panel rows, 65 individual panels and 19 hardware units**. All 65 panels reconcile with nesting input, engineering panel outlines and Complete Kitchen DXF contours. Finished panel area is **21.145060 m²**; cut rectangle area is **21.143628 m²**. These are not purchased sheet area. Two C1 synthetic doors specify one 716 mm front edge each, giving **1,432 mm** of synthetic ABS banding. The previous unprofiled fixture remains **48 BOM rows, 66 panels, 19 hardware units and 21.668 m²**.

Artifacts can be regenerated with:

```powershell
.venv\Scripts\python.exe -m scripts.validate_stage8_manufacturing demo_output\stage8_manufacturing\validation
```

They include a six-cabinet project JSON, BOM XLSX/PDF, cut-list XLSX/CSV, engineering and Complete Kitchen DXFs, a profile JSON example and a machine-readable expected-versus-actual report. These generated files are local demo artifacts. The original sample project is not altered.

## Desktop access and export safety

In **Manufacturing**, employees can apply a synthetic profile, import a profile JSON for the selected cabinet or restore legacy rules. Each action validates and requests confirmation before changing the active draft project. A separate **Export Demonstration Cut List (XLSX)** action produces the panel schedule. The Manufacturing Preview component tooltip shows the profile, cut size, grain and edge rules. Existing selected-cabinet drawing and drilling illustration remain available.

All nine pre-existing export actions remain: BOM XLSX/PDF, Quotation XLSX/PDF, Issued Quotation XLSX/PDF, Elevation DXF, Engineering Drawing Export and one-file Complete Kitchen DXF. They were not renamed or merged. The panel-outline portions of engineering and Complete Kitchen DXF use cut sizes when explicitly configured and carry profile/grain/edge metadata; legacy contour sizes remain unchanged. The Complete Kitchen DXF still includes the plan, named wall elevations and BOM schedules in one file. These are generic demonstration CAD geometries, not machine toolpaths.

## Required client specifications before production use

1. Approved base, drawer, sink, wall, open shelf and tall cabinet construction drawings and dimensional examples.
2. Board and shutter specifications by component, thickness, material grade, finish and permitted substitutions.
3. Joint and fit arrangement, back overlay/inset/groove details, side and panel allowances, shelf fixing and plinth/toe-kick details.
4. Door/drawer reveals, front overlays, drawer-box system, runner clearances and finished-versus-cut conventions.
5. Edge-banding map per part and side, band material/thickness/width, trimming and cut-size compensation convention.
6. Grain direction by material and part, sheet grain direction, matching/sequence requirements and allowed rotations.
7. Approved hardware schedules by door size and type, shelf supports, brackets, connectors, handles, runner specifications and treatment of separately assigned fittings.
8. Verified drilling and machining coordinates, tolerances, tool compensation and client CAM/CNC import examples.
9. Approved material and hardware rates plus any cost basis for banding, wastage, purchased sheets, finishing and machining. Stage 8 does not assign those costs.

**Classification: synthetic profile calculations verified; production construction and machine readiness pending client data and physical/CAM acceptance.**
