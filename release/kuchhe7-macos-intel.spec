import os
import subprocess
from collections import defaultdict
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
    hiddenimports += [
        name
        for name in package_hidden
        if not name.startswith(("pyvista.utilities.xvfb", "pyvista.plotting.utilities.xvfb"))
        and not name.startswith(("vtkmodules.gtk.", "vtkmodules.tk.", "vtkmodules.wx."))
    ]

codesign_identity = os.environ.get("KUCHE7_CODESIGN_IDENTITY") or None

a = Analysis(
    [str(release_root / "desktop_entry.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "PyQt5",
        "PyQt6",
        "tkinter",
        "_tkinter",
        "pytest",
        "vtkmodules.gtk",
        "vtkmodules.tk",
        "vtkmodules.wx",
    ],
    noarchive=False,
)


def linked_library_names(source_path):
    completed = subprocess.run(
        ["otool", "-L", str(source_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        Path(line.strip().split(" (compatibility", 1)[0]).name
        for line in completed.stdout.splitlines()[1:]
        if line.strip()
    }


def deployment_targets(source_path):
    completed = subprocess.run(
        ["otool", "-l", str(source_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    targets = []
    command = None
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if line == "cmd LC_BUILD_VERSION":
            command = "build"
        elif line == "cmd LC_VERSION_MIN_MACOSX":
            command = "legacy"
        elif command == "build" and line.startswith("minos "):
            targets.append(line.split(maxsplit=1)[1])
            command = None
        elif command == "legacy" and line.startswith("version "):
            targets.append(line.split(maxsplit=1)[1])
            command = None
    return targets


# PyVista contains a Linux-only, runtime-guarded ctypes.CDLL('libX11.so') call.
# PyInstaller's static ctypes scan sees the string on macOS and pulls Homebrew's
# X11 library plus its Xau/Xdmcp dependencies from the hosted runner.  Remove
# only that externally sourced chain after proving no retained binary links it.
runner_x11_names = {"libX11.so", "libXau.6.dylib", "libXdmcp.6.dylib"}
runner_x11_entries = [entry for entry in a.binaries if Path(entry[0]).name in runner_x11_names]
provenance_report = os.environ.get("KUCHE7_BINARY_PROVENANCE_REPORT")

if runner_x11_entries:
    found_names = {Path(entry[0]).name for entry in runner_x11_entries}
    if found_names != runner_x11_names:
        raise SystemExit(
            f"Refusing partial X11 removal; expected {sorted(runner_x11_names)}, "
            f"found {sorted(found_names)}"
        )

    aliases = {}
    for destination, source, _typecode in runner_x11_entries:
        source_path = Path(source).resolve()
        if "site-packages" in source_path.parts:
            raise SystemExit(f"Refusing to remove package-owned library: {source_path}")
        canonical = Path(destination).name
        aliases[canonical] = canonical
        aliases[source_path.name] = canonical

    reverse_dependencies = defaultdict(set)
    for destination, source, _typecode in a.binaries:
        source_path = Path(source)
        if not source_path.is_file():
            continue
        try:
            linked_names = linked_library_names(source_path)
        except (OSError, subprocess.CalledProcessError):
            continue
        for linked_name in linked_names:
            canonical = aliases.get(linked_name)
            if canonical:
                reverse_dependencies[canonical].add(destination)

    removable_destinations = {entry[0] for entry in runner_x11_entries}
    for library_name in runner_x11_names:
        retained_dependents = {
            dependent
            for dependent in reverse_dependencies[library_name]
            if dependent not in removable_destinations
        }
        if retained_dependents:
            raise SystemExit(
                f"Refusing to remove {library_name}; retained dependents: "
                + ", ".join(sorted(retained_dependents))
            )

    plotter_source = project_root / ".venv-macos-intel" / "lib" / "python3.12" / "site-packages" / "pyvista" / "plotting" / "plotter.py"
    plotter_text = plotter_source.read_text(encoding="utf-8")
    if "platform.system() == 'Linux'" not in plotter_text or "ctypes.CDLL('libX11.so')" not in plotter_text:
        raise SystemExit("Refusing X11 removal because PyVista's Linux-only guard changed")

    report_lines = [
        "Kuche7 Intel PyInstaller binary provenance",
        "RESULT: SAFE_TO_EXCLUDE_RUNNER_X11_CHAIN",
    ]
    for destination, source, _typecode in sorted(runner_x11_entries):
        name = Path(destination).name
        introduced_by = (
            "pyvista.plotting.plotter Linux-only ctypes.CDLL"
            if name == "libX11.so"
            else ",".join(sorted(reverse_dependencies[name])) or "libX11.so transitive dependency"
        )
        report_lines.append(
            f"library={name} | source={Path(source).resolve()} | "
            f"introduced_by={introduced_by} | "
            f"min_macos={','.join(deployment_targets(source)) or 'UNKNOWN'} | decision=excluded"
        )
    report_lines.append("remaining_required_references=none")
    if provenance_report:
        report_path = Path(provenance_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n".join(report_lines))
    a.binaries = [entry for entry in a.binaries if entry[0] not in removable_destinations]
elif provenance_report:
    report_path = Path(provenance_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "Kuche7 Intel PyInstaller binary provenance\n"
        "RESULT: NO_RUNNER_X11_CHAIN_PRESENT\n",
        encoding="utf-8",
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
