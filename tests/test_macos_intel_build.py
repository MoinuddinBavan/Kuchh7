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
    assert "numpy==2.2.6" in requirements
