# kuchhe7 Client Approval Demo v1.0.1 — bugfix build report

Build date: 19 October 2026  
Platform: Windows 11 x64  
Python used for build: 3.13.0  
PyInstaller: 6.22.3  
Packaging type: one-directory, windowed executable

## Result

- Normal startup is an empty 3600 × 3200 × 2600 mm room.
- The first Catalogue placement creates C1 and updates 2D, 3D, BOM, engineering preview, and nesting data.
- The selected cabinet, including the final cabinet, can be removed from the toolbar or with Delete in the Project tree/2D canvas.
- Cabinet removal is undoable and redoable without changing the cabinet ID.
- Empty-project JSON save/reopen and legacy single-cabinet JSON migration passed.
- Dirty replacement prompts provide Save, Discard, and Cancel.
- Complete still loads the six-unit client kitchen in one action.
- Source regression suite: 86 passed.
- Python compilation: passed.
- PyInstaller build: passed.
- Fresh-profile packaged workflow: passed.
- JSON save/reopen: passed.
- XLSX export/readback: passed (52 worksheet rows in the packaged smoke output).
- DXF generation/readback: passed with millimetre units (`$INSUNITS = 4`).
- Nesting reconciliation: passed (66 eligible, 66 placed, zero unplaced).

Executable: `release/dist/kuchhe7-client-demo-v1.0.1/kuchhe7-client-demo-v1.0.1.exe`  
The validated v1.0 executable and delivery archives were not removed or overwritten.

## Environment limitation

A separate physical or virtual clean Windows machine was not available. The
standalone executable was run outside the virtual environment with fresh
writable APPDATA, LOCALAPPDATA, and PyVista data directories. This detects
hidden development-path and profile-write dependencies but does not replace
testing on the client's Windows build, graphics driver, and endpoint security.

The executable is unsigned and no installer was created. The application
remains a client-approval feasibility prototype. Nesting, drilling, clearances,
DXF output, and construction rules are demonstration-only and not approved for
production, CNC, IMOS, G-code, machining, or factory use.
