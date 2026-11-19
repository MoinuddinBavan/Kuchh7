# Stage 7B.3 — catalogue-first pricing (demonstration)

## Employee workflow

Open **Manufacturing → Company Price Setup…** before making a new design. Configure
rate records under **Material & product rates** and cabinet selling rules under
**Catalogue selling rules**, or import CSV/XLSX rate records. Click **Save** to
store the company setup in the operating system's user application-data folder.
The default setup contains **no prices**. `KUCHE7_PRICE_SETUP_PATH` can override
the location for testing and managed deployments.

**New Project** copies the current company setup into its project JSON. This
keeps saved projects portable and prevents a later company rate edit from
silently changing an existing or issued quotation. To update an existing
project, use **BOM & Quotation → Price Setup** and explicitly import or edit its
master. CSV/XLSX imports replace rate records and retain existing catalogue
rules; JSON imports replace both. Import validation completes before any record
is replaced. Approved records require rates, date, currency and applicable
board specifications. Mixed approved currencies in one imported setup are
rejected. Imported appliance and accessory IDs must exist in the relevant
catalogue; hardware may use a catalogue ID or the existing automatic BOM names.
Imported rate units must suit their category. Purchase and selling units are metadata; the **rate unit** alone
controls the current cost calculation. No unit conversion is inferred.

For a cabinet, the quote first checks an explicit cabinet exception. Otherwise
it resolves an approved catalogue selling rule by product ID, supported finish,
currency and effective date. Fixed prices require the exact width, height and
depth. Calculated rules use the current BOM-derived cost plus an approved markup
**or** gross-margin percentage. If the size is unsupported, the rate is missing,
or the cost/rule is incomplete, the live draft says **INCOMPLETE**. The quote UI
labels manual prices as exceptions; **Clear cabinet exception** restores the
catalogue path. Billable appliances, sinks and taps use approved `each` rates
from the same Price Master. Decorative props are never billable or costed.

The BOM, costing and quotation are recalculated from current project data when
viewed or exported. The desktop workspace refreshes them after a committed
cabinet or hardware edit. Issued quotation snapshots remain frozen and have
separate export actions. Draft exports visibly identify incomplete pricing;
issuing a snapshot is blocked until all billable prices are complete.

## Synthetic worked example

`tests/fixtures/stage7b3_synthetic_prices.csv` is an **invented test fixture**,
not a client-approved price list. A 900 × 720 × 600 mm Cashmere two-door cabinet
under the synthetic 18 mm board rate of 100 INR/m², 6 mm back rate of
80 INR/m², and four hinges at 10 INR each has the following demonstration cost:

| Component | Cost (INR) |
| --- | ---: |
| Two sides | 86.40 |
| Top and bottom | 103.68 |
| Back | 47.28 |
| Shelf | 50.11 |
| Doors | 64.01 |
| Four hinges | 40.00 |
| **Total illustrative cost** | **391.48** |

An approved **synthetic** 20% markup rule yields a draft cabinet selling price
of **469.78 INR**. A 10% discount followed by 5% tax yields **443.94 INR**.
Changing width to 1200 mm recalculates the cost and draft selling price; it
does not rewrite an issued snapshot. This example adds no labour, overhead,
wastage, edge banding, sheet yield or other process charge. Add each optional
charge only after a documented client rule and quantity are supplied. Sheet
purchase rates are **not** converted to panel-area costs.

## Current boundaries and client dependencies

- Cabinet component dimensions and hardware counts are still illustrative.
  Actual construction rules await client drawings and Stage 7B.2 comparison.
- Surface finishes, laminate and edge-banding rates can be recorded, but their
  consumption is not inferred from the demo BOM. They remain outside calculated
  cost until approved quantities and rules are supplied.
- Fixed selling rules are exact-dimension variants. Quantity is currently one
  per placed cabinet; multiple identical cabinets are separate project objects.
- Approval status is user-declared locally; an external approval workflow is
  outside this milestone. Company setup is local to a user profile, not a
  shared enterprise service.
- The client must supply revisioned rates, product/variant mappings, permitted
  currencies and units, material/yield rules, approved process quantities,
  markup or margin policy, and expected cabinet results before acceptance.

No CNC machine compatibility, factory-approved pricing or construction accuracy
is implied by these synthetic checks.
