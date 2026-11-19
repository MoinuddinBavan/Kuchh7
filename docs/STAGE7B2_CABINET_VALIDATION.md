# Stage 7B.2 — cabinet reference validation

This is a comparison process, not a replacement for approved construction
rules. The only committed reference and project fixtures in this stage are
labelled **synthetic**. A matching synthetic fixture does not establish factory
accuracy, CAM compatibility, approved costs or client acceptance.

## Current calculation chain and freshness

1. Cabinet dimensions, type, counts and material live in the project model.
2. `generate_bom()` applies the existing illustrative component formulas.
   `generate_project_bom()` combines all cabinets. This output is the source for
   the BOM table, engineering component list, panel nesting and panel-outline
   engineering DXF.
3. `cost_cabinet()` prices eligible BOM panel areas and hardware quantities
   against approved, effective Price Master records. Explicit optional charges
   are additional cost lines. Missing rates make the result **INCOMPLETE**.
4. `calculate_quotation()` uses each line's manual, approved fixed, calculated,
   or billable-appliance price. Discount is applied before tax. Fixed and manual
   prices deliberately do not change when dimensions change; calculated prices
   do. Changes to approved rates affect calculated draft prices and billable
   appliance rates.
5. The design UI refreshes 2D, 3D, BOM, engineering preview, cost breakdown and
   draft quotation after a committed cabinet edit. Price Master edits refresh
   cost and draft quotation. Sheet nesting is marked **stale** after relevant
   cabinet changes; click **Recalculate nesting** to
   regenerate the layout. DXFs and document exports use current data when
   requested. Existing saved XLSX, PDF and DXF files never update themselves.
6. The issued quotation snapshot is a frozen record in project JSON. Separate
   **Export issued Excel/PDF** actions read that record only. The original
   quotation export actions remain live **draft** exports.

There is no separate production cutting-list engine. The panel-outline DXF and
nesting preview use BOM panel rectangles. Front-elevation DXF is drawn from
cabinet dimensions and fronts separately. Neither drawing route validates
client CAM import, machining, edge banding or factory clearance rules.

## Reference file and command

Create a project JSON containing the cabinet to check and a separate reference
JSON. The reference must identify `reference_id`, `reference_status`
(`synthetic` or `client_approved`), `source_document`, `cabinet_id`, and an
`expected` object. A client-approved reference additionally requires
`approved_by` and `revision`; these are evidence labels, not an automatic
production approval. Store actual signed source documents separately.

`expected` can contain `cabinet`, `components`, `hardware`, `bom_totals`,
`material_specifications`, `cost`, `selling_price`, `quotation`, `nesting`, and
`drawing`. Provide values only where the client has supplied an expectation.
Every omitted section is reported as **unchecked**. `components` and cost
`lines` are matched by name; extra or missing rows are reported. Drawing
comparison parses actual exported panel-outline DXF rectangles, a front-elevation
outline, and millimetre units. Nesting statistics are project-wide; the other component and drawing
checks use the specified cabinet. Optional numeric tolerances are keyed by
field path, for example `nesting.utilization_percent`; without a supplied
tolerance the comparison is exact.

Run the included synthetic reference:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_cabinet_reference `
  --project tests\fixtures\stage7b2_synthetic_project.json `
  --reference tests\fixtures\stage7b2_synthetic_reference.json `
  --report demo_output\stage7b2-synthetic-match.md `
  --json-report demo_output\stage7b2-synthetic-match.json
```

The fixture represents a 900 × 720 × 600 mm Cashmere two-door cabinet with
synthetic rates and markup. It expects 8 panel instances, 4 hinges, a synthetic
component subtotal of 391.48 INR, synthetic selling price of 469.78 INR, and
synthetic post-discount/tax quotation total of 443.94 INR. These values are test
fixtures only. A 1200 mm width variation produces a mismatch report with
expected, actual and numeric differences; see the generated example in
`demo_output/stage7b2-synthetic-mismatch.md`.

The CLI exits nonzero when mismatches occur. A zero exit code means only that
the **supplied** expectations matched. Review `unchecked_sections` before
making any acceptance claim. It never edits the project or its formulas.

## Information to request from the client

- Approved, revisioned cabinet drawings and dimensions for representative base,
  wall, tall, drawer, corner, sink, wardrobe and vanity units.
- For each part: name, finished and cutting sizes, thickness, substrate/finish,
  grain direction, edge treatment, joinery/clearance rule and quantity.
- Approved hardware schedule, mapping to catalogue IDs, and the rule for
  reconciling automatically generated and assigned hardware.
- Approved, dated material, hardware and appliance rates with units and currency;
  sheet purchasing/yield and wastage rules; explicit labour, machining and
  finishing quantities/rates where applicable.
- Approved fixed selling prices or markup/gross-margin policy, discount and tax
  treatment, rounding and acceptable tolerances.
- Expected BOM, cost, quotation, nesting/cutting schedule and drawing outputs
  for the same cabinet inputs, plus client CAM import acceptance evidence.

## Proposed construction-profile boundary for Stage 7C

Define a versioned `ConstructionProfile` with an ID, revision, applicable
furniture types, approved component and hardware rules, material/edge mapping,
and validation constraints. Route BOM, engineering details and panel exports
through a single profile-generated component manifest. Existing projects should
retain the current **legacy demonstration profile** until a user explicitly
selects an approved replacement. Never infer a profile from a finish name or
silently migrate a saved cabinet. Implement the first profile only after its
client reference and expected outputs have been signed off and compared here.
