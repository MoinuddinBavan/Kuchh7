"""Compare a saved KÜCHE7 project with supplied cabinet expectations, read-only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kuchhe7.cabinet_validation import compare_cabinet, load_reference
from kuchhe7.persistence import load_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a cabinet with synthetic or client-approved reference data")
    parser.add_argument("--project", required=True, type=Path, help="Existing project JSON")
    parser.add_argument("--reference", required=True, type=Path, help="Reference expectations JSON")
    parser.add_argument("--report", type=Path, help="Optional Markdown report path")
    parser.add_argument("--json-report", type=Path, help="Optional machine-readable report path")
    args = parser.parse_args(argv)
    project = load_project(args.project)
    report = compare_cabinet(project, load_reference(args.reference))
    print(report.to_markdown())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report.to_markdown(), encoding="utf-8")
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return 1 if report.mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
