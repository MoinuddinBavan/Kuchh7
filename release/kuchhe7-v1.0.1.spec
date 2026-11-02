from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).parent
datas = [
    (str(project_root / "README.md"), "."),
    (str(project_root / "release" / "THIRD_PARTY_NOTICES.md"), "."),
    (str(project_root / "release" / "FIVE_MINUTE_DEMO.md"), "."),
    (str(project_root / "release" / "RELEASE_CHECKLIST.md"), "."),
    (str(project_root / "release" / "BUILD_REPORT.md"), "."),
    (str(project_root / "demo_output" / "complete-kitchen.json"), "samples"),
]
licenses = project_root / "release" / "licenses"
if licenses.exists():
    datas.append((str(licenses), "licenses"))

binaries = []
hiddenimports = ["PySide6.QtOpenGLWidgets", "vtkmodules.qt.QVTKRenderWindowInteractor"]
for package in ("pyvista", "pyvistaqt", "vtkmodules"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(project_root / "release" / "windows_entry.py")],
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
    name="kuchhe7-client-demo-v1.0.1",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="kuchhe7-client-demo-v1.0.1",
)
