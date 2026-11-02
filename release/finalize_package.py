"""Add release documents and create the non-installer Windows delivery ZIP."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
import argparse
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1.0")
    args = parser.parse_args()
    version = args.version
    project_root = Path(__file__).resolve().parent.parent
    release_root = project_root / "release"
    package = release_root / "dist" / f"kuchhe7-client-demo-{version}"
    executable = package / f"kuchhe7-client-demo-{version}.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"Packaged executable not found: {executable}")

    for name in ("README.md",):
        shutil.copy2(project_root / name, package / name)
    for name in ("THIRD_PARTY_NOTICES.md", "FIVE_MINUTE_DEMO.md"):
        shutil.copy2(release_root / name, package / name)
    checklist = release_root / (
        "RELEASE_CHECKLIST.md" if version == "v1.0" else f"RELEASE_CHECKLIST-{version}.md"
    )
    if checklist.exists():
        shutil.copy2(checklist, package / "RELEASE_CHECKLIST.md")
    build_report = release_root / ("BUILD_REPORT.md" if version == "v1.0" else f"BUILD_REPORT-{version}.md")
    if build_report.exists():
        shutil.copy2(build_report, package / "BUILD_REPORT.md")
    samples = package / "samples"
    samples.mkdir(exist_ok=True)
    shutil.copy2(project_root / "demo_output" / "complete-kitchen.json", samples / "complete-kitchen.json")

    manifest = {
        "application": "kuchhe7",
        "release": f"Client Approval Demo {version}",
        "platform": "Windows x64",
        "entry_point": executable.name,
        "executable_sha256": sha256(executable),
        "production_status": "Feasibility prototype; not approved for CNC or factory use",
    }
    (package / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    archive = release_root / f"kuchhe7-client-demo-{version}-client-approval-win64.zip"
    if archive.exists():
        raise FileExistsError(f"Refusing to overwrite existing archive: {archive}")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for source in sorted(package.rglob("*")):
            if source.is_file():
                bundle.write(source, Path(package.name) / source.relative_to(package))
    checksums = release_root / ("CHECKSUMS.txt" if version == "v1.0" else f"CHECKSUMS-{version}.txt")
    checksums.write_text(
        f"{sha256(executable)}  {executable.name}\n{sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )
    print(executable)
    print(archive)


if __name__ == "__main__":
    main()
