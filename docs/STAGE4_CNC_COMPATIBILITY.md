# Stage 4 CNC/CAM compatibility checklist

The **CNC-Targeted Generic Prototype** is an R2010 DXF in millimetres with
closed 2D panel outlines generated from the demonstration cabinet BOM. It is
**not a production cutting file or verified for any CNC/CAM system**. It has no
drilling, pocketing, edge banding, toolpaths, feeds, nesting, machine code or
machine control. Appliances, decorative props and hardware assignments are
excluded. Existing manufacturing formulas remain illustrative.

## Information required from the client

- CNC machine make/model, controller and CAM software/version.
- An accepted sample DXF and written import specification.
- Supported DXF release, entity types, closed-polyline convention and layer names.
- Required origin, coordinate orientation, units and panel orientation.
- Whether text, XDATA, block references or non-cut layers must be omitted.
- Required material/thickness separation and identification convention.
- Confirmed panel construction rules, grain direction, rotation limits and any cut allowance.
- Separate approved instructions for drilling, pockets, edging and toolpaths, if needed later.

## Acceptance procedure

1. Compare the client's accepted sample with this prototype's layers, entities,
   origin and metadata; configure `CncDxfProfile` accordingly.
2. Reopen the DXF in a standard CAD viewer. Check every panel outline is closed,
   has the expected size in millimetres and does not overlap another outline.
3. Import a disposable test file into the client's CAM software with **machine
   output disabled**. Record import warnings, ignored layers and geometry count.
4. Compare imported geometry with the authoritative cabinet BOM and the
   client's approved construction rules. Resolve every mismatch.
5. Obtain written client/CAM specialist acceptance before calling the format
   compatible or using it for production.

Successful `ezdxf` parsing and the included automated tests establish only
internal DXF integrity. They do not establish CAM acceptance or cutting safety.
