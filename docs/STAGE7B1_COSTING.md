# Stage 7B.1 — draft costing foundation

This workspace is a **feasibility demonstration**. Its cabinet component sizes and
quantities still come from the illustrative BOM. A user marking a rate or pricing
rule “approved” records a local workflow decision; it does not establish client or
factory approval. No prices, allowances, margins or labour times ship with the app.

## Where to use it

Open **BOM & Quotation → Price Master** to add a record or import a JSON, CSV or
XLSX list. The required columns are `record_id`, `category`, `match_key`,
`description`, `unit`, `rate`, `currency`, `effective_date`, and `status`.
Optional columns are `thickness_mm`, `sheet_length_mm`, `sheet_width_mm`, and
`specification`. An approved Board record additionally needs thickness and a
material specification. Use `match_key` equal to the BOM material name, and a
separate board record for each thickness. Hardware BOM rates use the component
name as match key, such as `Concealed hinge` or `Drawer runner pair`.
Additional assigned hardware uses the catalogue type ID, such as `handle_bar`.
Appliance rates use the catalogue type ID and affect quotations only when the
product is marked supplied/billable.

Rates are saved in the project JSON (schema version 8). **Save master JSON** also
creates a portable local price-list file. Import replaces the project's current
master only after confirmation. Older project JSON files open with an empty
master and retain their manual quotation prices.

Open **Cost Breakdown** after selecting a cabinet. It shows the BOM component,
rate record ID, quantity conversion, rate, amount and any missing-rate warnings.
The calculation uses the quotation date to select the latest approved rate whose
effective date has arrived. All rates used for one calculation must share the
quotation currency.

## Explicit calculation rules

- Panel area in square metres = `length_mm × width_mm × BOM quantity / 1,000,000`.
- Panel amount = area × approved `m2` rate, rounded half up to 0.01 per BOM row.
- Hardware amount = BOM quantity × approved `each` rate. An assignment matching
  an automatic hinge/runner BOM line must have the same quantity; it is not
  costed twice. An unmatched quantity makes the cost **INCOMPLETE**. Assigned
  accessory hardware is a separate, labelled cost line.
- Optional Labour, Machining and Finishing records are used only when a user
  specifies an explicit quantity (`rate_ID=quantity`) in a cabinet pricing rule.
  No default hours or charges are inferred.
- `sheet` rates can be stored with sheet dimensions but are **not** converted
  into cost from panel area. That would imply an unapproved purchase/wastage rule.
- A calculated selling price is either `cost × (1 + markup% / 100)` or
  `cost / (1 − gross_margin% / 100)`, rounded half up to 0.01. These are distinct
  commercial rules and cannot be used together. A fixed price requires an
  explicitly approved rule. Existing manual prices are preserved in their own
  field and are never overwritten by either mode.
- Quotation discount and tax retain the existing order: discount on subtotal,
  then tax on the discounted amount.

Missing required records, non-matching currency, unapproved rules or missing
markup/margin leave the draft **INCOMPLETE**. The cost result means coverage of
the currently modelled BOM components only. It excludes unmodelled edge banding,
surface treatment, wastage, factory process costs and other client-specific
construction requirements. Those categories can be recorded in the master but
are not costed until quantities and rules are approved.

The quotation tab displays the pricing mode per line. **Record issued snapshot**
requires a complete draft, customer, quotation number and currency. It stores a
copy of amounts in project JSON; later design edits affect the live draft but
do not mutate the stored snapshot. Excel and PDF exports remain live draft
documents, not an issued-snapshot export.

## Validation and client dependency

The automated fixtures use IDs prefixed `SYN-` and deliberately synthetic rates.
They are not client-approved prices. Capture the native demo screens with:

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_stage7b1_pricing
```

Before commercial use, obtain the client's exact material and board
specifications, dated rates and currency, hardware mapping, appliance supply
prices, labour and process units, wastage/purchase rules, markup or gross-margin
policy, tax treatment, and approved expected outputs for representative cabinets.
Stage 7B.2 should validate those fixtures, reconcile the engineering geometry and
hardware schedule, then add approved edge/finish and sheet-purchase calculations.
Do not call the current BOM, nesting, DXF or costs production-ready.
