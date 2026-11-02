"""Collect installed runtime-package notices for the Windows demo bundle."""

from __future__ import annotations

import json
import re
import shutil
from importlib import metadata
from pathlib import Path


DISTRIBUTIONS = [
    "PySide6_Essentials", "shiboken6", "pyvista", "pyvistaqt", "vtk", "QtPy",
    "numpy", "matplotlib", "pillow", "pooch", "scooby", "cyclopts",
    "typing_extensions", "openpyxl", "et_xmlfile", "ezdxf", "fonttools",
    "contourpy", "cycler", "kiwisolver", "packaging", "pyparsing",
    "python-dateutil", "six", "requests", "charset_normalizer", "idna",
    "urllib3", "certifi", "platformdirs", "rich", "markdown-it-py", "mdurl",
    "colorama",
]


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    output = project_root / "release" / "licenses"
    output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []

    for requested_name in DISTRIBUTIONS:
        try:
            distribution = metadata.distribution(requested_name)
        except metadata.PackageNotFoundError:
            continue
        name = distribution.metadata.get("Name", requested_name)
        version = distribution.version
        license_name = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See bundled notice"
        manifest.append({"name": name, "version": version, "license": license_name})
        copied = 0
        for file in distribution.files or []:
            basename = Path(str(file)).name.casefold()
            if not basename.startswith(("license", "copying", "notice")):
                continue
            source = Path(distribution.locate_file(file))
            if not source.is_file():
                continue
            destination = output / f"{safe_name(name)}-{safe_name(version)}-{copied}-{source.name}"
            shutil.copy2(source, destination)
            copied += 1

    (output / "runtime-license-manifest.json").write_text(
        json.dumps(sorted(manifest, key=lambda item: item["name"].casefold()), indent=2),
        encoding="utf-8",
    )
    print(f"Collected notices for {len(manifest)} installed runtime distributions in {output}")


if __name__ == "__main__":
    main()
