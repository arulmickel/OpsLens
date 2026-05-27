"""Produce a clean delivery copy of the repo with secrets stripped.

Use this before zipping the project for a recruiter, an interviewer, or any
share link. The output is a sibling folder named `opslens_delivery/` (or a
custom path via --out) that excludes `.env`, real credentials, local logs,
caches, the venv, and anything in `local_data/`. After copying, the script
runs the secret scanner against the delivery copy and fails loud if anything
suspect remains.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Anything matching one of these patterns is excluded from the delivery copy.
EXCLUDE_NAMES = {
    ".env",
    ".env.local",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".coverage",
    "htmlcov",
    ".idea",
    ".vscode",
    "node_modules",
    "local_data",
    "logs",
    ".DS_Store",
    ".git",
    "opslens_delivery",
}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".log", ".sqlite", ".db")


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {
        n
        for n in names
        if n in EXCLUDE_NAMES or any(n.endswith(suffix) for suffix in EXCLUDE_SUFFIXES)
    }


def copy_repo(src: Path, dest: Path) -> int:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=_ignore)
    return sum(1 for _ in dest.rglob("*") if _.is_file())


def run_scan(repo_root: Path) -> int:
    scanner = repo_root / "scripts" / "scan_secrets.py"
    if not scanner.exists():
        print("Scanner script not found in delivery copy; aborting.", file=sys.stderr)
        return 2
    result = subprocess.run(
        [sys.executable, str(scanner)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=None,
        help="Destination folder. Defaults to ../opslens_delivery next to the project.",
    )
    args = parser.parse_args()

    src = Path(__file__).resolve().parents[1]
    dest = Path(args.out).resolve() if args.out else src.parent / "opslens_delivery"

    if dest == src:
        print("Refusing to overwrite the source repo.", file=sys.stderr)
        return 2

    print(f"Copying {src} -> {dest}")
    files = copy_repo(src, dest)
    print(f"Copied {files} files into {dest}")

    print("Running secret scan against the delivery copy")
    rc = run_scan(dest)
    if rc != 0:
        print("\nSecret scan FAILED on the delivery copy. Do not share this folder.")
        return rc

    if (dest / ".env").exists():
        print("Delivery copy still contains a .env file. Aborting.", file=sys.stderr)
        return 2

    print(f"\nDelivery copy ready at: {dest}")
    print("Zip it with PowerShell:")
    print(f'  Compress-Archive -Path "{dest}" -DestinationPath "{dest}.zip"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
