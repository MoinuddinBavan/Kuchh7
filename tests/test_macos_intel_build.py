from pathlib import Path
import runpy


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_macho_audit_parsers_cover_modern_and_legacy_targets():
    module = runpy.run_path(str(PROJECT_ROOT / "release" / "verify_macos_bundle.py"))
    parse_architectures = module["parse_architectures"]
    parse_targets = module["parse_deployment_targets"]

    assert parse_architectures("x86_64\n") == ("x86_64",)
    assert parse_architectures("x86_64 arm64\n") == ("x86_64", "arm64")
    output = """
Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform 1
    minos 12.0
      sdk 15.5
Load command 10
      cmd LC_VERSION_MIN_MACOSX
  cmdsize 16
  version 10.13
      sdk 10.15
"""
    assert parse_targets(output) == ("12.0", "10.13")


def test_intel_build_is_separate_manual_and_fail_closed():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "build-macos-intel.yml").read_text("utf-8")
    script = (PROJECT_ROOT / "release" / "build_macos_intel.sh").read_text("utf-8")
    spec = (PROJECT_ROOT / "release" / "kuchhe7-macos-intel.spec").read_text("utf-8")
    requirements = (PROJECT_ROOT / "release" / "requirements-macos-intel.txt").read_text("utf-8")

    assert "workflow_dispatch:" in workflow
    assert "runs-on: macos-15-intel" in workflow
    assert "./release/build_macos_intel.sh" in workflow
    assert "Kuche7-v1.0.1-macOS-Intel.dmg" in workflow
    assert 'target_arch="x86_64"' in spec
    assert '"LSMinimumSystemVersion": "12.0"' in spec
    assert "verify_macos_bundle.py" in script
    assert "--maximum-macos 12.0" in script
    assert "--only-binary=:all:" in script
    assert "PySide6-Essentials==6.9.3" in requirements
    assert "pyvista==0.46.4" in requirements
    assert "vtk==9.5.2" in requirements
    assert "numpy==1.26.4" in requirements
    assert "pillow==10.4.0" in requirements
    assert "--root \"$VENV/lib/python3.12/site-packages\"" in script
    assert "--allow-additional-architectures" in script
    assert '"vtkmodules.gtk"' in spec
    assert '"vtkmodules.tk"' in spec
    assert '"vtkmodules.wx"' in spec


def test_dependency_preflight_allows_universal_but_final_requires_thin(tmp_path):
    module = runpy.run_path(str(PROJECT_ROOT / "release" / "verify_macos_bundle.py"))
    inspect_tree = module["inspect_tree"]
    native = tmp_path / "library.dylib"
    native.write_bytes(b"test")

    def compatible_tool(command, *_arguments):
        if command == "file":
            return "Mach-O universal binary"
        if command == "lipo":
            return "x86_64 arm64"
        if command == "otool":
            return "cmd LC_BUILD_VERSION\nminos 12.0"
        raise AssertionError(command)

    inspect_tree.__globals__["run_tool"] = compatible_tool
    _, preflight_failures = inspect_tree(
        tmp_path, "x86_64", "12.0", require_exact_architecture=False
    )
    _, final_failures = inspect_tree(
        tmp_path, "x86_64", "12.0", require_exact_architecture=True
    )

    assert preflight_failures == []
    assert final_failures == [
        "library.dylib: expected only x86_64, found ('x86_64', 'arm64')"
    ]
