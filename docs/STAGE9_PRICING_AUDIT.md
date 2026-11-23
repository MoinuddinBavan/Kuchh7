# Stage 9 pricing audit — demonstration data only

KÜCHE7 reuses its existing `PriceMaster`, BOM, construction profiles, catalogue
rules, quotation service and issued snapshots. No rate in the synthetic Stage 9
test fixture is a client-approved commercial rate.

## Existing and extended workflow

| Step | Source and policy |
| --- | --- |
| Cabinet definition | Revisioned Cabinet Library item, dimensions, finish and optional construction-profile snapshot. Existing items remain valid. |
| Parts | `generate_bom` and the Stage 8 construction profile supply panel sizes, cut sizes, edge assignments and hardware quantities. Costing does not recalculate construction geometry. |
| Rates | The project's approved Price Master snapshot. An existing draft adopts newer company prices only after explicit review and refresh. |
| Cost | `cost_cabinet` creates line-level Decimal amounts with rate ID, BOM part ID, specification, supplier reference and rate revision. Missing approved rates result in `INCOMPLETE`; an approved zero is a genuine zero. |
| Selling price | Exact-dimension fixed catalogue rule takes precedence; otherwise the latest applicable calculated markup or gross-margin rule applies. An explicit quotation manual override takes precedence under the existing quotation workflow. |
| Draft and issued documents | Drafts recalculate from current design and project price snapshot. Issued quotations use their saved historical snapshot for both Excel and PDF. |

The default material basis remains **finished panel area** for old projects.
An employee can explicitly choose cut area, a per-sheet estimate with a stated
yield, or cabinet-isolated sheets from the demonstration nesting algorithm.
The latter two are estimates, not verified factory purchases or a shared-sheet
allocation. Missing or stale sheet inputs never silently fall back to area.
Material and edge wastage, overhead and optional labour/operation quantities
are charged only when configured. The policy rejects material wastage added to
sheet estimates and duplicate percentage/explicit overhead charging.

Currency amounts are rounded per cost line to 0.01 with `ROUND_HALF_UP`; the
sale rule then rounds to 0.01. Panel mm² converts to m² by 1,000,000, and edge
mm converts to metres by 1,000. Markup is cost × (1 + rate), while gross margin
is cost ÷ (1 − rate). Discount and tax retain the existing quotation rules; no
tax rate is supplied by Stage 9.

## Synthetic validation example

The independent oracle reads the fixed Stage 8 cut-list fixture and applies
explicit synthetic m², edge, hardware, assembly, overhead and markup rates.
These figures are **test examples only**:

| Cabinet | Cost | Selling price |
| --- | ---: | ---: |
| C1 two-door base | 460.03 | 552.04 |
| C2 three-drawer base | 521.13 | 625.36 |
| C3 sink base | 374.23 | 449.08 |
| C4 wall cabinet | 375.72 | 450.86 |
| C5 open-shelf cabinet | 263.10 | 315.72 |
| C6 tall pantry | 979.69 | 1,175.63 |
| **Draft subtotal** | | **3,568.69** |

The six-cabinet Stage 8 fixture stays at 47 BOM rows, 65 panels and 19 hardware
units. The legacy fixture stays at 48 rows and 66 panels. Decorative props are
excluded from costs, quotation, BOM and manufacturing exports.

## Export and compatibility boundaries

The existing BOM XLSX/PDF, draft quotation XLSX/PDF, issued quotation XLSX/PDF,
elevation DXF, engineering drawing export, complete kitchen DXF and cut-list
XLSX remain separate commands. Cost lines are internal; customer quotation
documents retain selling-price lines. Old projects use their saved pricing
and construction data. Fixed prices do not silently become cost-based prices.

## Client information still required

Client-approved material IDs/specifications, thicknesses, purchase units and
rates; edge band specifications and prices; hardware IDs and prices; labour and
operation quantities/rates; material yield or sheet-allocation policy; wastage
and overhead rules; selling-price/markup/margin policy; currency, discount and
tax rules; and reference BOM/cut lists for real cabinets. Actual production
cost accuracy and factory sheet consumption remain unverified until those
references are compared and approved.
