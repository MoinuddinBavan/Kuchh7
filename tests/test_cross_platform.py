from pathlib import Path

import ezdxf
from openpyxl import load_workbook

from kuchhe7.exports import export_bom_xlsx, export_front_elevation_dxf
from kuchhe7.models import Project
from kuchhe7.persistence import load_project, save_project
from kuchhe7.platform_support import delete_keys, is_macos, platform_name, platform_shortcut, ui_font_family


def test_platform_specific_ui_adaptations_are_deterministic():
    assert platform_name("Windows") == "Windows"
    assert platform_name("Darwin") == "macOS"
    assert not is_macos("Windows")
    assert is_macos("Darwin")
    assert ui_font_family("Windows") == "Segoe UI"
    assert ui_font_family("Darwin") == "SF Pro Text"
    assert platform_shortcut("Ctrl+Shift+M", "Windows") == "Ctrl+Shift+M"
    assert platform_shortcut("Ctrl+Shift+M", "Darwin") == "Meta+Shift+M"
    assert delete_keys("Windows") == ("Delete",)
    assert delete_keys("Darwin") == ("Delete", "Backspace")


def test_unicode_cross_platform_project_and_export_paths(tmp_path):
    project = Project.complete_kitchen_demo("Küche7 – Approval")
    folder = tmp_path / "Küche7 macOS test"
    json_path = save_project(project, folder / "Küche7 project.json")
    xlsx_path = export_bom_xlsx(project, folder / "Küche7 BOM.xlsx")
    dxf_path = export_front_elevation_dxf(project, folder / "Küche7 elevation.dxf")

    assert load_project(json_path).to_dict() == project.to_dict()
    assert load_workbook(xlsx_path, read_only=True, data_only=True)["BOM"].max_row > 4
    assert ezdxf.readfile(dxf_path).header["$INSUNITS"] == 4


def test_macos_build_configuration_uses_shared_entry_point():
    project_root = Path(__file__).resolve().parent.parent
    spec = (project_root / "release" / "kuchhe7-macos.spec").read_text(encoding="utf-8")
    script = (project_root / "release" / "build_macos.sh").read_text(encoding="utf-8")
    requirements = (project_root / "release" / "requirements-macos.txt").read_text(encoding="utf-8")

    assert 'release_root / "desktop_entry.py"' in spec
    assert 'target_arch="arm64"' in spec
    assert 'name="Kuche7.app"' in spec
    assert 'bundle_identifier="com.aizinfotechs.kuche7"' in spec
    assert '"LSMinimumSystemVersion": "13.0"' in spec
    assert "platform.machine() != \"arm64\"" in script
    assert "major < 13" in script
    assert "Kuche7-v1.0.1-macOS-arm64.dmg" in script
    assert "hdiutil create" in script
    assert "KUCHE7_SKIP_GUI_SMOKE" in script
    assert "PySide6-Essentials>=6.11,<6.12" in requirements


def test_github_macos_workflow_is_manual_arm64_and_artifact_only():
    project_root = Path(__file__).resolve().parent.parent
    workflow = (project_root / ".github" / "workflows" / "build-macos.yml").read_text(encoding="utf-8")
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "runs-on: macos-15" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "./release/build_macos.sh" in workflow
    assert 'KUCHE7_SKIP_GUI_SMOKE: "1"' in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "Kuche7-v1.0.1-macOS-arm64.app.zip" in workflow
    assert "Kuche7-v1.0.1-macOS-arm64.dmg" in workflow
    assert "contents: read" in workflow
    assert "demo_output/*" in gitignore
    assert "!demo_output/complete-kitchen.json" in gitignore
