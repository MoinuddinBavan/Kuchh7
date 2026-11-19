# Stage 7B.4 — reviewed company price refresh

This remains a demonstration costing workflow. Cabinet construction and hardware
quantities are illustrative; no factory or client approval is implied.

## Employee path

1. Open **Manufacturing → Company Price Setup…** and enter or import rates and
   catalogue selling rules. New projects receive an approved-only snapshot.
2. Select products in the existing library and place them in the 2D design.
   BOM and cabinet cost derive from current dimensions and selected finish.
   Approved catalogue rules resolve draft selling prices automatically.
3. Review **BOM & Quotation → Cost Breakdown → Customer Quotation**. Appliances
   enter the quote only when marked supplied/billable. Props remain excluded.
4. For an existing draft, choose **Manufacturing → Review Company Price Refresh…**
   or the button in **BOM & Quotation → Price Setup**. Review each added,
   changed and missing rate or catalogue rule, including the current and
   proposed values and effective dates. The dialog previews the live draft
   total. **Cancel** leaves the project unchanged; **Apply reviewed prices**
   replaces its price-master snapshot with approved company records.
5. Save the project JSON. Its `pricing_revision` records the approved company
   master fingerprint, latest rate/rule effective date and UTC application time.
   The Price Setup page shows if rates were edited in the project afterward.

The refresh rejects an incompatible currency and refuses a stale preview if
project prices changed between review and apply. A project with no quotation
currency adopts the single company currency on confirmation. Existing manual
cabinet exceptions remain explicitly identified and unchanged. Issued quotation
snapshots and their exports remain frozen. Draft quotations recalculate from
the current project and approved effective rates; missing rates/rules remain
**INCOMPLETE**. Older JSON projects without `pricing_revision` still open.

The current project snapshot is intentionally independent of later company
edits. A company Price Setup change alone cannot silently alter an open project.
This local, per-user setup is not a shared enterprise price database.

## Synthetic verification

The Stage 7B.4 capture script uses **synthetic** rates. For one 900 × 720 ×
600 mm Cashmere cabinet, its board rate changes from 100 to 200 INR/m² only
after review and apply. Illustrative cost changes from **391.48** to **695.68
INR**; an invented 20% markup changes the selling price from **469.78** to
**834.82 INR**. With an invented 10% discount and 5% tax, the draft total
changes from **443.94** to **788.91 INR**. The cabinet BOM and its dimensions
do not change from a rate refresh.

Run the screenshot walkthrough on Windows:

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_stage7b4_pricing
```

It saves only clearly named synthetic outputs under `demo_output/` and uses a
project-local override for company pricing. It does not edit the user's actual
company Price Setup or client workbook.

## Safeguards and remaining client inputs

- Fixed cabinet prices still require the approved exact product variant and
  dimensions. Manual prices remain exceptional and visible.
- Board costs use the illustrative BOM's panel area and approved matching m²
  rates. Sheet purchase rates are not converted without an approved yield rule.
- Surface treatment, edge banding, wastage, labour, finishing and overhead are
  not inferred. Explicit process charges require supplied quantities and rates.
- Automatic hardware counts remain those of the existing demo BOM; matching
  assigned hinges/runners are reconciled, not charged twice.
- Client drawings, part schedules, hardware rules, material/rate revisions,
  costing and selling policy, tax treatment and expected outputs are still
  required for real-cabinet validation.

The 2D sample uses compact cabinet labels within footprints; full dimensions
remain available in the selected properties and tooltip. Explicit plotter
cleanup runs before Qt shutdown. The reported `QOffscreenSurface` warning did
not reproduce on this Windows machine, so other GPU/Qt installations still
require a close/relaunch check.
