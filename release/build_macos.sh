#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV="$ROOT/.venv-macos"
DIST="$ROOT/release/dist-macos"
WORK="$ROOT/release/build-macos"
APP="$DIST/Kuche7.app"
DMG="$DIST/Kuche7-v1.0.1-macOS-arm64.dmg"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script must run on macOS; macOS applications cannot be built on Windows." >&2
  exit 2
fi

"$PYTHON_BIN" - <<'PY'
import platform
import sys

if platform.machine() != "arm64":
    raise SystemExit("Run with a native Apple Silicon arm64 Python, not Rosetta/x86_64.")
if sys.version_info[:2] not in ((3, 12), (3, 13)):
    raise SystemExit("Use Python 3.12 or 3.13 for the validated dependency range.")
major = int(platform.mac_ver()[0].split(".", 1)[0])
if major < 13:
    raise SystemExit("Küche7 requires macOS 13 or newer with the prepared PySide6 build.")
print(f"Building on macOS {platform.mac_ver()[0]}, {platform.machine()}, Python {platform.python_version()}")
PY

"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel
"$VENV/bin/python" -m pip install -r "$ROOT/release/requirements-macos.txt"
"$VENV/bin/python" -m pip check
"$VENV/bin/python" -m pytest -q -p no:cacheprovider --basetemp="$ROOT/.test-tmp-macos"
"$VENV/bin/python" "$ROOT/release/create_macos_icon.py"
"$VENV/bin/pyinstaller" --noconfirm --clean \
  --distpath "$DIST" --workpath "$WORK" "$ROOT/release/kuchhe7-macos.spec"

if [[ -n "${KUCHE7_CODESIGN_IDENTITY:-}" ]]; then
  codesign --force --deep --options runtime --timestamp \
    --sign "$KUCHE7_CODESIGN_IDENTITY" "$APP"
else
  codesign --force --deep --sign - "$APP"
fi
codesign --verify --deep --strict --verbose=2 "$APP"
file "$APP/Contents/MacOS/Kuche7"

if [[ "${KUCHE7_SKIP_GUI_SMOKE:-0}" == "1" ]]; then
  echo "Skipping graphical startup smoke test (KUCHE7_SKIP_GUI_SMOKE=1)."
  echo "The packaged application still requires interactive testing on a real Mac."
else
  KUCHHE7_AUTOCLOSE_MS=5000 "$APP/Contents/MacOS/Kuche7"
fi
hdiutil create -volname "Küche7" -srcfolder "$APP" -ov -format UDZO "$DMG"
shasum -a 256 "$DMG"

echo "Application: $APP"
echo "Disk image:  $DMG"
