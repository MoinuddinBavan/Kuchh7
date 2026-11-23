# Stage 10 nesting audit — synthetic demonstration only

This is a rectangle layout and price-allocation feasibility workflow. It is
**not** a factory-approved cutting program, purchase plan, CNC toolpath or CAM
post-processor. No client sheet, kerf, trim, grain or purchase-rate data has
been supplied.

## Existing engine and Stage 10 changes

| Capability | Before Stage 10 | Stage 10 status |
| --- | --- | --- |
| Source parts | BOM rows with cut-size fallback; no cut-list part or wall IDs | Uses the authoritative Stage 8 cut list, retaining part, cabinet, wall and construction-profile IDs. Validated on 65 synthetic panels. |
| Material groups | Display material and thickness | Separates material, thickness, finish and optional stable material ID. Unknown material is unplaced. |
| Sheet master | One editable 2440×1220 mm example setting | Existing approved Price Master sheet records now carry optional material ID, finish, grain axis, rotation policy, supplier and revision. Demonstration UI settings still work for projects without client rates. |
| Placement | Decreasing-area first-fit shelves | Deterministic best-fit guillotine rectangle candidate plus preserved shelf fallback. The automatic choice prioritizes fewer unplaced parts, then fewer sheets. Global optimality is not claimed. |
| Clearance | One kerf and symmetric margin | Separate kerf, minimum part clearance, four trims and symmetric margin. The larger of kerf and clearance defines the single part separation; they are not added twice. |
| Grain | No rotation of directional parts | Rotation requires compatible panel and sheet grain axes. An unknown sheet grain does not authorize a directional 90-degree turn. Costing refuses directional sheet allocation without an approved sheet grain axis. |
| Utilization | Placed area / purchased sheet area | Reports purchased and usable sheet areas, panel area, residual usable area, trim/margin exclusion, purchased-area and usable-area utilization, theoretical area lower bound and actual allocated sheets. |
| Offcuts | None | Conservative disjoint residual rectangles above configurable minimum dimensions are *candidates for review*, never inventory records. Other unused area is not labelled irreversible waste. |
| Freshness | Cabinet attribute tuple and settings change flag | Signature follows actual cut-list parts and profile revision. Settings mark the UI layout stale; quotation sheet costing makes a fresh layout and validates it on each draft calculation. Layouts are regenerated after project reopen. |
| Export | No nesting-specific file | Additional, separately named 1:1 demonstration sheet-layout DXF with sheets, usable boundaries, panel rectangles, part labels and grain notes. Existing ten export commands are unchanged. |
| Cost | Per-cabinet sheet estimates | Optional project-wide calculated-cost policy requires current complete validated placement and approved per-sheet rates. It allocates each group sheet expense by cabinet cut-panel area with exact-cent reconciliation. Fixed prices, manual overrides and issued snapshots retain existing behavior. |

## Synthetic six-cabinet validation

The Stage 8 synthetic profiles yielded **47 BOM rows, 65 manufactured panel
instances and 19 hardware units**. With explicitly synthetic 2440×1220 mm
sheets, 3 mm kerf, 5 mm minimum clearance, 10 mm margin and 8/6/4/7 mm
left/right/top/bottom trims, every panel was placed in its material group.
The total area lower bound was 12 sheets; the validated layout allocated 14.
The previous shelf method also used 14 on this fixture. Purchased-area
utilization was 50.74%; usable-area utilization was 52.80%. Thirty-two
conservative residual rectangles passed the synthetic 150×100 mm offcut
threshold. Their suitability for reuse is unverified.

An independent second fixture of nine rectangles used **four sheets with the
prior shelf method and three with the automatic best-fit candidate**. Both
layouts passed independent bounds, separation, grain and quantity checks.
This one fixture does not imply universal superiority; the automatic choice
keeps the prior method when it uses fewer sheets.

The synthetic per-sheet rate of INR 100 produced a total of INR 1,400 for the
14-sheet fixture. Cabinet allocations sum to exactly INR 1,400 with currency
rounding to cents. These are **test values, not client-approved costs**.

The output files in `demo_output/stage10_nesting/validation/` contain a
sheet-by-sheet manifest, group reports, candidate offcuts, cost allocations,
the source synthetic project and Price Master, and a 1:1 DXF. The DXF was
read back with 65 panel outlines and millimetre units.

## Limits and client inputs

The rectangle partition is a layout, not an executable guillotine/panel-saw
sequence. Irregular residual regions and actual kerf-loss area are not
classified. The remaining usable area includes kerf/clearance strips and
non-reusable slivers; it is not all purchase waste. No stock inventory is
created. Shared sheet costs use an explicit cut-area allocation rule that
requires client approval before commercial use.

Client reference data is needed for purchased sheet SKUs and sizes, material
and surface compatibility, panel grain requirements, machine process, kerf,
clearance and trim rules, offcut-reuse policy, purchase rates, cost-allocation
policy and CAM/CNC import validation. Directional grain and real machine
cutting remain unverified until those specifications are supplied and tested.
The current Stage 8 cut-list records do not carry a stable material SKU, so
material-ID matching is prepared in the nesting data model but cannot be
validated against real client stock identifiers yet.
