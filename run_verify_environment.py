from __future__ import annotations

import argparse
import json
from pathlib import Path

from maintenance.verify import ADEEnvironmentVerifier


def _print_report(report: object) -> None:
    print("\n========================================")
    print(" ADE ENVIRONMENT VERIFICATION")
    print("========================================")
    print(f"Machine      : {report.machine}")
    print(f"Python       : {report.python_version}")
    print(f"Git branch   : {report.git_branch or '-'}")
    print(f"Git commit   : {report.git_commit or '-'}")
    print(f"Git status   : {'modified' if report.git_dirty else 'clean' if report.git_dirty is False else 'unknown'}")
    print(f"DB path      : {report.db_path}")
    print(f"DB size      : {report.db_size / 1024 / 1024:,.1f} MB")
    print(f"DB SHA-256   : {report.db_sha256 or '-'}")
    print(f"Fingerprint  : {report.fingerprint}")
    print("\nCHECKS")
    for item in report.items:
        suffix = f" ({item.detail})" if item.detail else ""
        print(f"[{item.status:4}] {item.name}: {item.value}{suffix}")
    print("\nTABLE COUNTS")
    for name, count in report.table_counts.items():
        print(f"- {name:28} : {'missing' if count is None else f'{count:,}'}")
    failed = [item for item in report.items if item.status == "FAIL"]
    warned = [item for item in report.items if item.status == "WARN"]
    print("\nRESULT")
    print(f"PASS : {len(report.items) - len(failed) - len(warned)}")
    print(f"WARN : {len(warned)}")
    print(f"FAIL : {len(failed)}")
    print(f"Overall: {'PASS' if not failed else 'FAIL'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ADE environment and compare two PCs")
    parser.add_argument("--db", default="datahub/market.db")
    parser.add_argument(
        "--save",
        nargs="?",
        const="output/ade_environment.json",
        help="Save this PC fingerprint JSON. Default: output/ade_environment.json",
    )
    parser.add_argument(
        "--compare",
        help="Compare this PC with a fingerprint JSON exported from another PC.",
    )
    parser.add_argument("--json", action="store_true", help="Print report as JSON")
    args = parser.parse_args()

    verifier = ADEEnvironmentVerifier(".", args.db)
    report = verifier.verify()

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(report)

    if args.save:
        saved = verifier.save(report, args.save)
        print(f"\nSaved report: {saved}")

    if args.compare:
        comparison = verifier.compare(report, args.compare)
        print("\n========================================")
        print(" TWO-PC COMPARISON")
        print("========================================")
        print(f"Current PC : {comparison['current_machine']}")
        print(f"Other PC   : {comparison['other_machine']}")
        for name, matched in comparison["checks"].items():
            print(f"[{'PASS' if matched else 'FAIL'}] {name}")
        print(f"Identical  : {'YES' if comparison['identical'] else 'NO'}")
        if not comparison["identical"]:
            raise SystemExit(2)

    if any(item.status == "FAIL" for item in report.items):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
