#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV="$ROOT/.venv-macos-intel"
DIST="$ROOT/release/dist-macos-intel"
WORK="$ROOT/release/build-macos-intel"
APP="$DIST/Kuche7.app"
DMG="$DIST/Kuche7-v1.0.1-macOS-Intel.dmg"
REPORT="$DIST/Kuche7-v1.0.1-macOS-Intel-compatibility.txt"
PREFLIGHT_REPORT="$DIST/Kuche7-v1.0.1-macOS-Intel-dependency-preflight.txt"
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must run on macOS." >&2
  exit 2
fi

"$PYTHON_BIN" - <<'PY'
import platform
import sys

if platform.machine() != "x86_64":
    raise SystemExit("Run with a native Intel x86_64 Python, not Apple Silicon/Rosetta.")
if sys.version_info[:2] != (3, 12):
    raise SystemExit("Use Python 3.12 for the prepared Intel dependency set.")
print(f"Intel build host: macOS {platform.mac_ver()[0]}, {platform.machine()}, Python {platform.python_version()}")
PY

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel
"$VENV/bin/python" -m pip install --only-binary=:all: -r "$ROOT/release/requirements-macos-intel.txt"
"$VENV/bin/python" -m pip check
mkdir -p "$DIST"
"$VENV/bin/python" -m pip freeze > "$DIST/Kuche7-v1.0.1-macOS-Intel-dependencies.txt"
"$VENV/bin/python" - <<'PY'
from importlib.metadata import version

expected = {
    "numpy": "1.26.4",
    "pillow": "10.4.0",
    "vtk": "9.5.2",
}
for package, required in expected.items():
    installed = version(package)
    if installed != required:
        raise SystemExit(f"Expected {package} {required}, found {installed}")
    print(f"Pinned dependency: {package}=={installed}")
PY
"$VENV/bin/python" "$ROOT/release/verify_macos_bundle.py" \
  --root "$VENV/lib/python3.12/site-packages" \
  --arch x86_64 --maximum-macos 12.0 --allow-additional-architectures \
  --report "$PREFLIGHT_REPORT"
"$VENV/bin/python" -m pytest -q -p no:cacheprovider --basetemp="$ROOT/.test-tmp-macos-intel"
"$VENV/bin/python" "$ROOT/release/create_macos_icon.py"
"$VENV/bin/pyinstaller" --noconfirm --clean \
  --distpath "$DIST" --workpath "$WORK" "$ROOT/release/kuchhe7-macos-intel.spec"

if [[ -n "${KUCHE7_CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp \
    --sign "$KUCHE7_CODESIGN_IDENTITY" "$APP"
else
  codesign --force --deep --sign - "$APP"
fi
codesign --verify --deep --strict --verbose=2 "$APP"
"$VENV/bin/python" "$ROOT/release/verify_macos_bundle.py" \
  --app "$APP" --arch x86_64 --maximum-macos 12.0 --report "$REPORT"

if [[ "${KUCHE7_SKIP_GUI_SMOKE:-0}" == "1" ]]; then
  echo "Skipping hosted-runner GUI smoke test; physical Intel Mac validation remains required."
else
  KUCHHE7_AUTOCLOSE_MS=5000 "$APP/Contents/MacOS/Kuche7"
fi
hdiutil create -volname "Küche7 Intel" -srcfolder "$APP" -ov -format UDZO "$DMG"
shasum -a 256 "$DMG"

echo "Application: $APP"
echo "Disk image:  $DMG"
echo "Preflight:   $PREFLIGHT_REPORT"
echo "Audit:       $REPORT"
