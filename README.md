# kuchhe7 Client Approval Demo v1.0.1

`kuchhe7` is a native Windows desktop demonstration for kitchen, wardrobe, and
vanity project configuration. It was prepared by **AIZ INFOTECHS** as a first
client milestone. The BOM and DXF output use illustrative construction rules;
they are not factory-approved and are not CNC/IMOS production integrations.

## Windows setup and run

```powershell
cd "D:\client demo"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m kuchhe7
```

If PowerShell blocks activation, run the interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m kuchhe7
```

## macOS Apple Silicon

The same source code supports a prepared native macOS arm64 build. On an M1,
M2, M3, M4, or newer Mac, use a fresh native Python 3.12/3.13 environment:

```bash
python3 -m venv .venv-macos
source .venv-macos/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q -p no:cacheprovider --basetemp=.test-tmp-macos
python -m kuchhe7
```

For the `.app`, `.dmg`, Apple Silicon, signing, and notarization workflow, see
[`release/MACOS_BUILD.md`](release/MACOS_BUILD.md). macOS binaries must be built
and validated on macOS; the Windows release is preserved separately.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

To regenerate and verify the three-cabinet sample project, workbook, and DXF:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_demo
```

To validate the v0.4.1 premium catalogue sample and regenerate its JSON, XLSX,
and DXF outputs:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_premium_sample
```

To launch the real window and capture the v0.6 room-design views:

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_room_design_demo
```

To validate and capture the v0.7 complete kitchen:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_complete_kitchen
.\.venv\Scripts\python.exe -m scripts.capture_complete_kitchen_demo
```

To launch the polished six-unit presentation and capture the v0.7.1 client
views:

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_visual_polish_demo
```

To launch and capture the v0.8 Cabinet Engineering Preview:

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_engineering_preview
```

To launch and capture the v0.9 Demonstration Sheet Nesting workspace:

```powershell
.\.venv\Scripts\python.exe -m scripts.validate_nesting_demo
.\.venv\Scripts\python.exe -m scripts.capture_nesting_preview
```

For the final v1.0 walkthrough and release checklist, see:

- `release/FIVE_MINUTE_DEMO.md`
- `release/RELEASE_CHECKLIST.md`
- `release/THIRD_PARTY_NOTICES.md`

Build the standalone Windows one-directory package with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r release\requirements-build.txt
.\.venv\Scripts\python.exe release\collect_licenses.py
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean `
  --distpath release\dist --workpath release\build release\kuchhe7-v1.0.1.spec
.\.venv\Scripts\python.exe release\finalize_package.py --version v1.0.1
```

The validated executable is under
`release\dist\kuchhe7-client-demo-v1.0.1\kuchhe7-client-demo-v1.0.1.exe`; the
portable final delivery archive is
`release\kuchhe7-client-demo-v1.0.1-client-approval-win64.zip`. The prior v1.0
executable and archives remain available unchanged.

## Demo workflow

The application starts with an empty 3600 × 3200 × 2600 mm room. Use the
**Catalogue** to place the first cabinet (C1), or choose **Complete** to load the
six-unit client kitchen in one action. **File > New Project** also creates an
empty room. Select a cabinet in the Project tree or 2D plan, use **Remove** or
the scoped **Delete** shortcut to remove it, and use **Undo/Redo** to restore or
repeat placement changes. Delete is intentionally inactive while editing text,
numeric, or combo-box controls.

Change cabinet and room properties in the right panel, inspect the synchronized
plan/3D model/BOM, then use the Export toolbar buttons. Save projects as JSON
and reopen them through **File > Open Project**. Dirty project replacement uses
an explicit Save / Discard / Cancel choice.

Use **Load Sample Kitchen** for the premium presentation arrangement containing
a 900 mm Cashmere C1 base cabinet, elevated 600 mm Warm White C2 wall cabinet,
and 800 mm Walnut C3 tall pantry. Select furniture in the Project tab or directly in the 2D plan. Browse
the 15 illustrated types under the **Catalogue** tab by Base Cabinets, Wall
Cabinets, Tall Units, and Vanity. Each item shows a model-derived preview,
category, and default dimensions; then use **Place selected furniture**. Move
the translucent preview in the 2D plan and click to commit it, or press **Esc**
to cancel. Drag any placed footprint to reposition it. **Snap**, **Grid 100 mm**,
alignment guides, and Undo/Redo provide controlled placement while the existing
Position X/Y fields remain available. Add and Remove manage up to ten units.
Out-of-room placements and genuine three-dimensional intersections are rejected;
an elevated wall unit may overlap a base footprint when their Z ranges do not
intersect.

The cabinet-view ribbon provides **Front**, **Isometric**, and **Reset View**
camera commands. **Fit All Cabinets** reframes the full arrangement while
preserving the current viewing direction. Enable **Show Interior** to hide the door and handle geometry
and inspect every carcass and shelf. Door, drawer, open-shelf, sink, corner,
lift-up, appliance, wall-mounted, and tall-unit geometry is generated from the
selected catalogue type. Mouse rotation, pan, and zoom remain
available directly in the 3D viewport. BOM and exports include every cabinet;
the combined DXF is still a demonstration front elevation only.

Use **Presentation View** to place the same accurately positioned cabinets in
a 3600 × 3200 mm room environment with a neutral floor, back and side walls,
baseboard junctions, a subtle backsplash, countertop, plinth, and coordinated
lighting. **Hide Room Walls** keeps the floor and cabinetry visible, while
**Presentation Camera** restores the predefined client-facing composition.
These visual actors never enter project JSON, BOM, XLSX, or DXF output.

The 3D canvas header includes **Maximize 3D** (`Ctrl+Shift+3`). It temporarily
hides the plan and dock panels for a full presentation viewport; **Restore
Workspace** returns the previous splitter sizes and dock visibility. Furniture
selection shows the cabinet controls immediately, while selecting D1/W1 shows
the relevant opening editor.

### Cabinet Engineering Preview

Open **Manufacturing > Manufacturing Preview** or select the workspace tab. The
preview follows the currently selected cabinet and reads its component rows
directly from the existing demonstration BOM generator. It provides a labeled
exploded assembly, component dimensions/material/quantity, and a dimensioned 2D
drawing for the selected component.

The separate **Drilling Preview** tab illustrates configurable hole diameter,
reference-edge offset, pitch and count for a door or side panel. These parameters
are temporary presentation settings: they are not saved to the project and are
never included in the existing DXF or any CNC output. The workspace displays the
required warning: **Engineering feasibility demo — drilling and construction
rules not approved for production.**

### Demonstration Sheet Nesting

Open **Manufacturing > Sheet Nesting** or select the separate workspace tab.
The layout expands positive-dimension panel quantities from the authoritative
project BOM, keeps material and thickness groups on separate sheets, and uses a
documented deterministic decreasing-area first-fit shelf heuristic. Select a
material group and sheet, then click any rectangle to inspect its cabinet ID,
component, original dimensions, thickness, instance number, and orientation.

The example 2440 × 1220 mm sheet size, saw kerf, edge margin, rotation option,
and user-controlled grain rotation restriction are editable. A project edit
marks the existing result as stale; **Recalculate nesting** explicitly regenerates
it from the updated BOM. Oversized panels remain unplaced with a visible reason.
The displayed utilization is placed rectangular panel area divided by the full
area of all allocated sheets. The heuristic is deterministic but does not claim
to find an optimal cutting solution.

The workspace warning is mandatory: **Demonstration nesting layout only. Not
approved for CNC cutting or factory use.** It produces no toolpaths, G-code,
machine drilling, IMOS data, or production cutting DXF.

The nesting statistics distinguish total eligible panel area, successfully
placed panel area, unplaced panel area, and utilization of all allocated sheet
area. **Layout current** refers only to freshness; the separate **Layout
complete/incomplete** status reports whether every eligible panel was placed.

Use **Load Complete Kitchen Demo** for the separate v0.7 client scene. It loads
six editable units: an 800 mm Cashmere two-door base, 600 mm Warm White drawer
base, 800 mm Cashmere sink base, Warm White wall cabinet, Walnut open wall
shelf, and 600 mm Walnut tall pantry. C1–C3 form one continuous back-wall run;
C4–C5 stack above it without a false collision, and C6 finishes the layout with
a deliberate gap. The presentation countertop, recessed plinth, sink rim and
recessed basin are generated
as a single visual run and split automatically whenever a real cabinet gap is
introduced. They remain presentation-only and are excluded from JSON, BOM,
XLSX, and DXF manufacturing data.

Loading the sample asks for confirmation whenever the current project has
unsaved changes. The active cabinet is highlighted in the tree, 2D plan, and
3D assembly, and its ID is shown above the selected-cabinet properties.

### Room openings

Rectangular rooms have persistent NORTH, EAST, SOUTH, and WEST wall IDs. Use
**Design > Room Openings > Select Wall**, or click a wall in the 2D plan, then
choose **Add Door** or **Add Window** from the right-side Room Openings panel.
Move along the chosen wall and click to place; press **Esc** to cancel. Doors
and windows can be selected in the plan or Project tree, dragged along their
wall, edited numerically, removed, and restored with Undo/Redo.

Opening offset, width, height, floor elevation, wall, and door swing are stored
in project JSON. Door swing clearance and window opening-volume conflicts are
checked geometrically against furniture in X/Y/Z. These are transparent demo
rules rather than approved building-code or factory-clearance calculations.

### Demonstration construction rules

- Side panels are full cabinet height and depth.
- Top and bottom fit between the two side panels.
- Shelves fit between sides and stop 20 mm short of the front.
- The back panel fits inside the carcass opening and uses a fixed 6 mm thickness.
- Door leaves share the front width, with a 3 mm presentation reveal.
- Each demonstration door receives two hinges.
- Drawer boxes, runners, sink rails, corner returns, and appliance rails are
  illustrative component rules for this demo only.

## Scope and limitations

The v0.9 milestone intentionally remains limited to rectangular rooms and ten
placed furniture units. Furniture placement is top-view click/drag with wall,
furniture-edge, and optional 100 mm grid snapping. Openings move only along their
assigned wall; wall thickness and swing rules are simplified demonstration
geometry, not a full architectural constraint solver. Presentation countertops
and plinths are dynamically grouped visual geometry only; worktop fabrication,
sink cut-outs, fillers, end panels, and production installation rules remain out
of scope.
The demo does not include fillers, production worktop calculations, CNC
machining, factory optimisation, or production AutoCAD/IMOS interoperability.
Catalogue geometry, BOM formulas, and exports are presentation-grade
demonstrations and require manufacturing approval before any production use.
The existing DXF export contains demonstration cabinet front elevations only;
it is not a nesting layout, machining drawing, toolpath or cutting instruction.
The engineering and nesting workspaces do not include validated hardware
libraries, joinery, machining, tool selection, optimized nesting, edge-banding
schedules, cutting sequences or CNC code.

### Premium finish palette

- Warm White `#E8E5DE`
- Cashmere `#BDB2A5`
- Natural Oak `#B99568`
- Walnut `#694B39`
- Graphite `#43474A`

Projects saved with the v0.4 names White Matte, Cashmere / Greige Matte, and
Graphite Grey continue to open and retain their selected finish appearance.

