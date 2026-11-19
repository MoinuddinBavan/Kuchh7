# Stage 9 — cabinet library with integrated demo pricing

Stage 8 was protected by local commit `ad210e3` after its 205-test baseline passed. The client meeting workbook was not staged or changed. Stage 9 is a local milestone; nothing was pushed.

## Employee workflow

In **Libraries → Furniture**, select **Add Cabinet…**. The **Details** tab takes a unique product ID, name, existing construction template, dimensions, supported dimension range, finish, door/drawer/shelf counts, and optional bar-handle quantity. The template fixes the category and front style so the existing illustrative BOM/geometry rules are reused. The **Pricing** tab offers exact-variant fixed selling price or calculated selling price from the existing BOM cost and markup/gross margin. The live preview lists the matching approved Price Master record IDs, quantities, rates, cost, missing rates, and selling price. Saving writes a revisioned local cabinet definition and a rule into the existing Company Price Setup; there is no second rate database.

**Edit Cabinet…** creates a new immutable internal revision. The visible product ID remains the same; older projects continue to reference their saved revision and Price Master snapshot. Selecting a built-in model for Edit creates a new user-managed copy after the employee supplies a product ID. Built-in definitions remain unchanged. New projects copy the current approved company rates and rules. An existing draft project must use the reviewed Company Price Refresh before placing a newly priced custom model that is absent from its snapshot.

The local custom definitions live in the platform application-data directory as `custom-cabinet-library.json`; `KUCHE7_CABINET_LIBRARY_PATH` may override that location for disposable testing. Projects also save the custom definitions needed by their placed cabinets, so a saved project can reopen with its own historical revision. Existing project schema version 8 and legacy migrations remain supported.

## Synthetic verification

The disposable Windows walkthrough in `scripts/capture_stage9_library.py` used synthetic INR rates and a synthetic base cabinet. The automatically matched board, back, hinge, and optional handle references produced an illustrative component cost of **INR 405.48** and a calculated draft selling price of **INR 486.58** at 20% markup, with no manual cabinet unit price. Increasing width from 900 to 1000 mm changed cost to **INR 435.91** and draft selling price to **INR 523.09**. These are not client-approved rates or formulas.

Focused tests cover library persistence, immutable edits, dimension restrictions, fixed-price exact matching, missing/unapproved rates, automatic hardware assignment without duplicate counts, draft repricing, frozen issued snapshots, project reopen, and BOM/quotation/DXF exports. The full suite passed **213 tests**. The desktop walkthrough captured Add, Pricing, Edit, 2D/3D placement, automatic BOM, automatic quotation, resized draft with frozen issued total, and library-after-restart screens under `demo_output/stage9-synthetic-final3`. That folder also contains synthetic BOM/quotation XLSX and PDF, a panel-outline DXF, and a saved project JSON that reopened successfully.

## Boundaries

- The application continues to use its existing illustrative cabinet construction rules. Custom models choose a supported template; arbitrary new construction profiles are unavailable until the client approves them.
- Board/hardware rates are matched automatically by finish, thickness, component name/type and effective date. The dialog shows the matched record IDs; it does not override the Price Master matching algorithm with an arbitrary rate choice.
- An “approved” checkbox is a local demo marker. There is no employee authorization system in this milestone.
- Fixed selling prices apply only to the saved dimensions. Resizing beyond that exact variant leaves the draft price incomplete unless a calculated rule or another approved fixed variant exists.
- A fixed selling price may be known while the illustrative manufacturing cost is incomplete; the cost preview shows that distinction. Client costing and approval policy remain pending.
- Optional bar handles are stored as existing cabinet hardware assignments and included in costing without double-counting automatic hinges. The legacy cabinet BOM remains unchanged and does not add an optional handle line.
- No approved material prices, CNC instructions, or production construction formulas are bundled.
