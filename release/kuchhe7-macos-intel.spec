import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).parent
release_root = project_root / "release"
icon_path = release_root / "assets" / "Kuche7.icns"
datas = [
    (str(project_root / "README.md"), "."),
    (str(release_root / "THIRD_PARTY_NOTICES.md"), "."),
    (str(release_root / "MACOS_BUILD.md"), "."),
    (str(release_root / "MACOS_INTEL_COMPATIBILITY.md"), "."),
    (str(release_root / "FIVE_MINUTE_DEMO.md"), "."),
    (str(project_root / "demo_output" / "complete-kitchen.json"), "samples"),
    (str(release_root / "assets" / "kuche7-icon.svg"), "assets"),
]
licenses = release_root / "licenses"
if licenses.exists():
    datas.append((str(licenses), "licenses"))

binaries = []
hiddenimports = [
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg",
    "vtkmodules.qt.QVTKRenderWindowInteractor",
]
for package in ("pyvista", "pyvistaqt", "vtkmodules"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

codesign_identity = os.environ.get("KUCHE7_CODESIGN_IDENTITY") or None

a = Analysis(
    [str(release_root / "desktop_entry.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["PyQt5", "PyQt6", "tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kuche7",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch="x86_64",
    codesign_identity=codesign_identity,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Kuche7",
)
app = BUNDLE(
    coll,
    name="Kuche7.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier="com.aizinfotechs.kuche7",
    version="1.0.1",
    info_plist={
        "CFBundleDisplayName": "Küche7",
        "CFBundleName": "Küche7",
        "CFBundleShortVersionString": "1.0.1",
        "CFBundleVersion": "1.0.1",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    },
)
