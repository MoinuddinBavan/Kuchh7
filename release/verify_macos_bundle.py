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


def inspect_tree(
    root: Path,
    expected_arch: str,
    maximum_macos: str,
    *,
    require_exact_architecture: bool,
) -> tuple[list[str], list[str]]:
    records: list[str] = []
    failures: list[str] = []
    maximum = parse_version(maximum_macos)
    macho_count = 0

    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        description = run_tool("file", "-b", str(path))
        if "Mach-O" not in description:
            continue
        macho_count += 1
        relative = path.relative_to(root).as_posix()
        architectures = parse_architectures(run_tool("lipo", "-archs", str(path)))
        targets = parse_deployment_targets(run_tool("otool", "-l", str(path)))
        records.append(
            f"{relative} | arch={','.join(architectures) or 'UNKNOWN'} "
            f"| min_macos={','.join(targets) or 'UNKNOWN'}"
        )
        if require_exact_architecture and architectures != (expected_arch,):
            failures.append(f"{relative}: expected only {expected_arch}, found {architectures or 'none'}")
        elif not require_exact_architecture and expected_arch not in architectures:
            failures.append(f"{relative}: required {expected_arch}, found {architectures or 'none'}")
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--app", type=Path)
    source.add_argument("--root", type=Path)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--maximum-macos", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--allow-additional-architectures", action="store_true")
    arguments = parser.parse_args()

    root = arguments.app or arguments.root
    assert root is not None
    if not root.is_dir():
        raise SystemExit(f"Audit root not found: {root}")

    records, failures = inspect_tree(
        root,
        arguments.arch,
        arguments.maximum_macos,
        require_exact_architecture=not arguments.allow_additional_architectures,
    )
    plist_target: str | None = None
    if arguments.app is not None:
        plist_target = run_tool(
            "plutil", "-extract", "LSMinimumSystemVersion", "raw", "-o", "-",
            str(arguments.app / "Contents" / "Info.plist"),
        )
        if parse_version(plist_target) > parse_version(arguments.maximum_macos):
            failures.append(
                f"Info.plist requires macOS {plist_target}, exceeding {arguments.maximum_macos}"
            )

    lines = [
        "Kuche7 macOS native compatibility audit",
        f"Audit root: {root}",
        f"Required architecture: {arguments.arch}",
        "Architecture policy: "
        + (
            "required architecture may be part of a universal binary"
            if arguments.allow_additional_architectures
            else "thin binary required"
        ),
        f"Maximum deployment target: macOS {arguments.maximum_macos}",
        f"Mach-O files inspected: {len(records)}",
    ]
    if plist_target is not None:
        lines.append(f"Info.plist minimum: macOS {plist_target}")
    lines.extend(["", *records, "", "RESULT: " + ("FAIL" if failures else "PASS")])
    if failures:
        lines.extend(["", "Failures:", *(f"- {failure}" for failure in failures)])
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-(len(failures) + 3) :] if failures else lines[:8] + ["RESULT: PASS"]))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
