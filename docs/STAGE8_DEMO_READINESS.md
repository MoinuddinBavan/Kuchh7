# KÜCHE7 Stage 8 — automatic workflow validation

This is a **synthetic feasibility demonstration**, not client-approved pricing or manufacturing engineering. The repeatable check is `python -m scripts.validate_stage8_workflow demo_output/stage8-synthetic` from the project virtual environment. It creates only disposable files under `demo_output/stage8-synthetic` and does not alter the company Price Setup or client workbook.

## Checkpoint and data sources

- Stage 7B.4 baseline: 203 tests passed; committed locally as `857e30f`. The untracked `docs/Kuche7 points.xlsx` was excluded. No remote push was made.
- Company setup is copied into a new `Project.empty()` by `pricing_setup.apply_company_setup_to_new_project`; this synthetic fixture has approved INR board, hinge, runner and oven rates plus catalogue rules. Cabinet `quotation.unit_prices` remains empty.
- `catalogue.create_catalogue_cabinet` supplies the product dimensions. `models.Project` validates placement and persists the cabinets and price revision. `bom.generate_project_bom` uses the existing illustrative panel rules. `costing.cost_cabinet` prices BOM panel area in square metres and hardware per item. `quotation.calculate_quotation` resolves the approved catalogue rule and calculates 20% markup on complete illustrative cost. Discount is applied to subtotal; tax applies after discount.
- `nesting.nest_project` expands the same BOM panel quantities, groups by material and thickness, then runs deterministic first-fit shelf placement. `engineering_dxf.export_engineering_dxf` creates millimetre cabinet elevations and panel outlines from current project/BOM data. Neither is a validated CNC instruction set.

## Synthetic example before design edits

| Cabinet | Product and initial dimensions (W × H × D, mm) | Finish | BOM rows | Illustrative component cost (INR) | Draft selling price (INR) |
|---|---|---|---:|---:|---:|
| C1 | Base 2-door, 900 × 720 × 600 | Cashmere | 8 | 391.48 | 469.78 |
| C2 | Wall 2-door, 800 × 720 × 350 | Warm White | 8 | 381.63 | 457.96 |
| C3 | Base 3-drawer, 600 × 720 × 600 | Warm White | 10 | 551.09 | 661.31 |

The three selling prices total INR 1,589.05 before a 10% synthetic discount (INR 158.91) and 5% synthetic tax on the discounted amount (INR 71.51), yielding a draft total of **INR 1,501.65**. Purchase/component cost and customer selling price are different fields. Missing approved rates result in `INCOMPLETE`, rather than a fabricated approved cost.

The initial BOM expands to 39 eligible nesting rectangles. All 39 were placed on 8 example 2440 × 1220 mm sheets, at 43.63% allocated-sheet utilization. Hardware is excluded from nesting. These figures describe the example heuristic, not a factory cut plan.

## Changes, quotation lifecycle, and exports

Widening C1 to 1000 mm, increasing its height to 770 mm, depth to 650 mm, then changing Cashmere to Warm White changed the live draft totals in sequence to INR 1,725.15, 1,741.97, 1,767.10, and 2,004.63 (after a billable synthetic oven was included). The approved Warm White board rate was then changed from INR 150/m² to INR 200/m² in a separate company master. The existing project remained at INR 2,004.63 until the reviewed refresh was applied; afterward its draft became INR 2,426.88. The previously issued synthetic quotation remained INR 1,690.65 throughout those edits. A decorative plant left BOM, quotation and nesting quantities unchanged.

Generated artifacts in `demo_output/stage8-synthetic` include JSON, initial and updated BOM XLSX, BOM PDF, draft quotation XLSX/PDF, issued quotation XLSX/PDF, front-elevation DXF and initial and updated panel-outline DXF. The validator reopens JSON, checks draft Excel pricing, reads both DXF types and checks `$INSUNITS = 4` (mm), compares every panel-outline rectangle against the corresponding BOM/nesting instance dimensions, and checks issued snapshot preservation. Existing Stage 7B.3/7B.4 tests cover exact fixed variants, manual exceptions, missing-rate handling, hardware reconciliation, gross-margin rules, and export values.

Nesting does **not** silently regenerate after a cabinet change. The desktop `SheetNestingWidget` displays “Project changed — recalculate”; the user must press **Recalculate nesting**. A Stage 8 regression verifies the old result stays marked stale until explicit regeneration, then the panel area changes and the status returns to “Layout current”. Previously exported files are not silently changed.

## Desktop review and limits

`python -m scripts.capture_stage8_workflow` launches the real PySide6/PyVista Windows application with a disposable synthetic project, visits Design Studio, all four library categories, Presentation View, Engineering Preview and drilling, Sheet Nesting, Price Setup, Cost Breakdown, BOM and Quotation, then closes the window. Screenshots are in `demo_output/stage8-synthetic`. At the available 1920 × 1080 display, the main workspace, 2D cabinet labels, BOM and quote totals were readable. A narrow drilling-preview adjustment places four controls in two rows and enlarges drawing annotations; the final screenshot was visually reviewed. Native app closure and a separate `python -m kuchhe7.app` startup/shutdown check completed without a QOffscreenSurface error in this environment; the originally affected setup has not been independently retested. The final full suite passed **205 tests**.

This is a scripted desktop walkthrough plus service-level data validation. It is not a physical employee acceptance test of every mouse gesture or an external API/CAM test. The sample has no client-approved cabinet construction profiles, cut lists, component consumption, yield/wastage rules, approved price list, tax policy, quotation template, or CAM-machine acceptance. Live OpenAI rendering was not invoked. Client review is required before production use.
