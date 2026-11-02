# Küche7 macOS Apple Silicon build guide

This repository uses one shared PySide6/PyVista source tree for Windows and
macOS. The Windows release configuration remains under `release/*.spec`; the
macOS-only packaging files do not run during the Windows build.

## Current compatibility assessment

The application entry point is `python -m kuchhe7`. It uses PySide6 widgets,
QGraphicsView, PyVista/PyVistaQt with stock VTK, openpyxl, and ezdxf. Runtime
source uses `pathlib.Path` and Qt file dialogs; it has no Win32 imports, registry
calls, shell commands, or fixed Windows filesystem paths.

The macOS build targets native `arm64` on macOS 13 or newer. Use Python 3.12 or
3.13 from a native Apple Silicon installation. Do not run the build interpreter
through Rosetta: every bundled Python, Qt, VTK, NumPy, and PyInstaller binary
must have the same architecture.

The prepared configuration is intentionally a native arm64 build, not a
Universal 2 build. Universal 2 requires both arm64 and x86_64 variants of every
binary dependency and is outside this client-demo milestone.

## Prerequisites on the Mac

1. Apple Silicon Mac (M1/M2/M3/M4 or newer) running macOS 13 or newer.
2. Xcode Command Line Tools:

   ```bash
   xcode-select --install
   ```

3. Native arm64 Python 3.12 or 3.13. Verify:

   ```bash
   python3 -c 'import platform; print(platform.machine())'
   # Must print: arm64
   ```

4. Copy or clone the complete repository to the Mac. Do not copy the Windows
   `.venv`; virtual environments are platform-specific.

## Run from source

From the repository root:

```bash
python3 -m venv .venv-macos
source .venv-macos/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt
python -m pip check
python -m pytest -q -p no:cacheprovider --basetemp=.test-tmp-macos
python -m kuchhe7
```

On the physical Mac, manually verify the complete client workflow: empty
startup, 2D placement, 3D orbit/zoom, catalogue placement and deletion,
Undo/Redo, complete kitchen, presentation mode, engineering/exploded view,
drilling preview, nesting, JSON save/reopen, XLSX, and DXF.

## Build `Kuche7.app` and DMG

The script creates/reuses `.venv-macos`, installs only the declared runtime/test
and PyInstaller requirements, runs all tests, generates the `.icns`, builds the
application, validates its signature and architecture, smoke-launches the
frozen executable, and creates the DMG.

```bash
chmod +x release/build_macos.sh
./release/build_macos.sh
```

Expected outputs after a successful build on an actual Apple Silicon Mac:

```text
release/dist-macos/Kuche7.app
release/dist-macos/Kuche7-v1.0.1-macOS-arm64.dmg
```

These paths are expected outputs only. They are not present or claimed as
validated until the script completes successfully on macOS.

## Build remotely with GitHub Actions

The repository includes `.github/workflows/build-macos.yml`. It is manual-only
(`workflow_dispatch`) and uses GitHub's native Apple Silicon `macos-15` runner
with Python 3.12. The workflow calls this same `release/build_macos.sh` script,
creates a resource-preserving ZIP of `Kuche7.app`, and uploads both the ZIP and
DMG as private workflow artifacts.

The hosted runner skips the direct graphical startup smoke test by setting
`KUCHE7_SKIP_GUI_SMOKE=1`. It still runs the complete automated test suite,
builds the bundle, verifies its architecture and ad-hoc signature, and creates
the DMG. VTK/Cocoa rendering and normal user interaction must be checked after
downloading the artifact to a physical Apple Silicon Mac.

To run it, open the private repository on GitHub and select **Actions**,
**Build macOS Apple Silicon**, **Run workflow**. After a successful run, download
the `Kuche7-v1.0.1-macOS-arm64-dmg` artifact from the run summary.

The workflow uses only read permission for repository contents and contains no
publishing step. Do not commit Apple certificates, private keys, passwords or
notarization credentials. Private-repository hosted-runner usage consumes the
GitHub account's included Actions allowance and can become billable if that
allowance is exhausted.

For a local-only build, the script applies an ad-hoc signature. For external
distribution, set a valid Developer ID Application identity before building:

```bash
export KUCHE7_CODESIGN_IDENTITY='Developer ID Application: Company Name (TEAMID)'
./release/build_macos.sh
```

Then store a notarization profile once and submit the finished DMG:

```bash
xcrun notarytool store-credentials 'kuche7-notary' \
  --apple-id 'APPLE_ID' --team-id 'TEAM_ID' --password 'APP_SPECIFIC_PASSWORD'

xcrun notarytool submit \
  release/dist-macos/Kuche7-v1.0.1-macOS-arm64.dmg \
  --keychain-profile 'kuche7-notary' --wait

xcrun stapler staple release/dist-macos/Kuche7-v1.0.1-macOS-arm64.dmg
xcrun stapler validate release/dist-macos/Kuche7-v1.0.1-macOS-arm64.dmg
spctl --assess --type open --context context:primary-signature --verbose=4 \
  release/dist-macos/Kuche7-v1.0.1-macOS-arm64.dmg
```

Do not put Apple credentials in the repository. External distribution requires
Apple Developer Program membership, a Developer ID Application certificate,
hardened-runtime signing, a secure timestamp, notarization, and stapling.

## 3D and packaging checks on the Mac

Run these after dependency installation and after building:

```bash
python -c 'import PySide6, pyvista, pyvistaqt, vtk; print(PySide6.__version__, pyvista.__version__, pyvistaqt.__version__, vtk.vtkVersion.GetVTKVersion())'
file release/dist-macos/Kuche7.app/Contents/MacOS/Kuche7
codesign --verify --deep --strict --verbose=2 release/dist-macos/Kuche7.app
otool -L release/dist-macos/Kuche7.app/Contents/MacOS/Kuche7
```

PyVista/VTK rendering must be inspected on a physical Apple Silicon GPU. A
Windows test cannot verify the macOS Cocoa/OpenGL rendering path, Retina
scaling, native menu behavior, Gatekeeper, signing, or notarization.

## Licensing note

The build uses open-source Python dependencies. PySide6/Qt is offered under
LGPLv3/GPLv3 as well as a commercial option. This project does not require a
commercial Qt licence merely to build the demo, but distribution under LGPL
has compliance obligations. Keep `THIRD_PARTY_NOTICES.md` and the collected
licence files in the bundle, preserve dynamic library replacement rights, and
have the release owner review LGPL compliance. This is operational guidance,
not legal advice.
