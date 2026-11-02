# kuchhe7 Client Approval Demo v1.0 — build report

Build date: 17 October 2026  
Platform: Windows 11 x64  
Python used for build: 3.13.0  
PyInstaller: 6.22.3  
Packaging type: one-directory, windowed executable

## Result

- Source regression suite: 73 passed
- Python compilation: passed
- PyInstaller build: passed
- Standalone build-tree launch: passed
- Full packaged workflow with fresh APPDATA/LOCALAPPDATA: passed
- Close and normal relaunch with a second fresh profile: passed
- Delivery ZIP extraction and full smoke rerun: passed
- JSON save/reopen: passed
- XLSX export/readback: passed
- DXF generation/readback with millimetre units: passed
- Nesting reconciliation: passed

Executable: `release/dist/kuchhe7-client-demo-v1.0/kuchhe7-client-demo-v1.0.exe`  
Delivery archive: `release/kuchhe7-client-demo-v1.0-client-approval-win64.zip`  
Checksums: `release/CHECKSUMS.txt`

The default unedited six-unit scene produces 66 eligible/placed panels, zero
unplaced panels, 14 sheets, 21.668 m² eligible and placed area, and 52.0%
allocated-sheet utilization. The packaged smoke flow reduces C1 from 800 mm to
700 mm and then reports 21.350 m² at 51.2% utilization.

## Environment limitation

A separate physical or virtual clean Windows machine was not available. The
delivery ZIP was extracted to a new folder and run without the virtual
environment, using fresh APPDATA, LOCALAPPDATA and PyVista data directories.
This detects project-path and writable-profile dependencies but does not replace
testing on the client's Windows version, graphics driver and endpoint security.

The executable is unsigned and no installer was created. Windows reputation or
endpoint-security prompts can therefore vary. Code signing and installer
selection remain release-owner decisions.

The package is a client-approval feasibility prototype. It does not provide
production nesting, CNC, IMOS, G-code, machining or factory-approved rules.
