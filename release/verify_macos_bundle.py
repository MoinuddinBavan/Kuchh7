"""Fail-closed architecture and deployment-target audit for a macOS app bundle."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def parse_version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.strip().split("."))


def parse_architectures(output: str) -> tuple[str, ...]:
    return tuple(part for part in output.strip().split() if part)


def parse_deployment_targets(output: str) -> tuple[str, ...]:
    """Extract minos/version values from LC_BUILD_VERSION and legacy commands."""

    targets: list[str] = []
    command: str | None = None
    for raw_line in output.splitlines():
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
    return tuple(targets)


def run_tool(*arguments: str) -> str:
    completed = subprocess.run(arguments, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def inspect_bundle(app: Path, expected_arch: str, maximum_macos: str) -> tuple[list[str], list[str]]:
    records: list[str] = []
    failures: list[str] = []
    maximum = parse_version(maximum_macos)
    macho_count = 0

    for path in sorted(app.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        description = run_tool("file", "-b", str(path))
        if "Mach-O" not in description:
            continue
        macho_count += 1
        relative = path.relative_to(app).as_posix()
        architectures = parse_architectures(run_tool("lipo", "-archs", str(path)))
        targets = parse_deployment_targets(run_tool("otool", "-l", str(path)))
        records.append(
            f"{relative} | arch={','.join(architectures) or 'UNKNOWN'} "
            f"| min_macos={','.join(targets) or 'UNKNOWN'}"
        )
        if architectures != (expected_arch,):
            failures.append(f"{relative}: expected only {expected_arch}, found {architectures or 'none'}")
        if not targets:
            failures.append(f"{relative}: no macOS deployment target load command found")
        for target in targets:
            if parse_version(target) > maximum:
                failures.append(f"{relative}: deployment target {target} exceeds macOS {maximum_macos}")

    if macho_count == 0:
        failures.append("No Mach-O files were found in the application bundle")
    return records, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--maximum-macos", required=True)
    parser.add_argument("--report", required=True, type=Path)
    arguments = parser.parse_args()

    if not arguments.app.is_dir():
        raise SystemExit(f"Application bundle not found: {arguments.app}")

    plist_target = run_tool(
        "plutil", "-extract", "LSMinimumSystemVersion", "raw", "-o", "-",
        str(arguments.app / "Contents" / "Info.plist"),
    )
    records, failures = inspect_bundle(arguments.app, arguments.arch, arguments.maximum_macos)
    if parse_version(plist_target) > parse_version(arguments.maximum_macos):
        failures.append(
            f"Info.plist requires macOS {plist_target}, exceeding {arguments.maximum_macos}"
        )

    lines = [
        "Kuche7 macOS bundle compatibility audit",
        f"Bundle: {arguments.app}",
        f"Required architecture: {arguments.arch}",
        f"Maximum deployment target: macOS {arguments.maximum_macos}",
        f"Info.plist minimum: macOS {plist_target}",
        f"Mach-O files inspected: {len(records)}",
        "",
        *records,
        "",
        "RESULT: " + ("FAIL" if failures else "PASS"),
    ]
    if failures:
        lines.extend(["", "Failures:", *(f"- {failure}" for failure in failures)])
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-(len(failures) + 3) :] if failures else lines[:7] + ["RESULT: PASS"]))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
