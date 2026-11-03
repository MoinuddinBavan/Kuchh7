# Küche7 Intel macOS compatibility candidate

This is a separate packaging track for the existing shared source code. It does
not change the Windows build or the Apple Silicon build.

## Target

- Hardware: Intel `x86_64`
- Client OS candidate: macOS Monterey 12.7.6
- Build runner: GitHub Actions `macos-15-intel`
- Python: 3.12
- Output: `Kuche7-v1.0.1-macOS-Intel.dmg`

This is a compatibility candidate, not a confirmed Monterey release. Final
approval requires launching and exercising it on the client's 2017 Intel
MacBook. PyInstaller documents macOS builds as supported from the build-host OS
forward; therefore the automated binary audit and physical Monterey test are
both mandatory even when dependency wheels advertise older deployment tags.

## Prepared dependency set

| Package | Prepared version | Published macOS Intel basis |
| --- | ---: | --- |
| PySide6-Essentials / Shiboken6 | 6.9.3 | universal2, macOS 12+ |
| PyVista | 0.46.4 | platform-independent wheel |
| PyVistaQt | 0.13.1 | platform-independent wheel |
| VTK | 9.5.2 | x86_64 wheel, macOS 10.10+ tag; compatible with PyVista 0.46.4 |
| NumPy | 2.2.6 | x86_64 wheel, macOS 10.13+ tag |
| Matplotlib | 3.10.7 | x86_64 wheel, macOS 10.13+ tag |
| PyInstaller | 6.22.3 | x86_64/universal2 packaging support |

Wheel filenames are only resolver filters, not final runtime proof. The build
runs `verify_macos_bundle.py`, which enumerates every Mach-O file in the frozen
application, requires a thin `x86_64` architecture, reads the real
`LC_BUILD_VERSION` or `LC_VERSION_MIN_MACOSX` load command, and fails if any
deployment target exceeds macOS 12.0. The generated audit and exact dependency
list are uploaded beside the DMG.

## Manual workflow

From GitHub, select **Actions**, **Build macOS Intel**, **Run workflow**, and the
`main` branch. This workflow is manual-only and will not run merely because a
commit was pushed.

## Client MacBook test checklist

1. Confirm `uname -m` prints `x86_64` and macOS reports 12.7.6.
2. Verify the downloaded SHA-256 checksum.
3. Mount the DMG and copy `Kuche7.app` to Applications.
4. Run `file /Applications/Kuche7.app/Contents/MacOS/Kuche7`; require x86_64.
5. Run `codesign --verify --deep --strict --verbose=2` on the application.
6. Control-click the ad-hoc-signed app and choose Open for the internal demo.
7. Load the complete kitchen and inspect 2D and interactive 3D views.
8. Orbit, zoom and switch CAD/Presentation modes.
9. Place, edit, move, undo, redo and delete furniture.
10. Open manufacturing, drilling and nesting previews.
11. Export and reopen JSON, XLSX and DXF files in writable folders.
12. Close and relaunch the application.

Do not disable Gatekeeper globally. External distribution still requires an
Apple Developer ID signature and notarization.
