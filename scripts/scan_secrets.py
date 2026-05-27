"""Scan the repo for hardcoded secrets.

Exits non-zero if anything looks like a real key. Example files
(*.example, secrets.toml.example) and obvious placeholders are
allowed. Run manually or via pre-commit.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent

# (pattern_name, regex)
PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("OpenAI API key", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("Hugging Face token", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Generic bearer token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}")),
    (
        "Inline password assignment",
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
        ),
    ),
    (
        "Snowflake account literal",
        re.compile(r"(?i)snowflake.*?account\s*[:=]\s*[\"'][a-z0-9][a-z0-9\-]{4,}[\"']"),
    ),
]

ALLOWED_FILES = {
    ".env.example",
    "secrets.toml.example",
    "scan_secrets.py",
}
ALLOWED_DIR_PARTS = {".venv", "venv", "node_modules", ".git", "__pycache__"}

# These literal placeholder substrings make a line obviously safe.
PLACEHOLDER_MARKERS = (
    "placeholder",
    "your_",
    "example",
    "REDACTED",
    "$2b$12$placeholder",
)

ALLOWED_EXTENSIONS = {
    ".py",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".html",
    ".cfg",
    ".ini",
    ".json",
    ".txt",
    ".env",
}


def _walk(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        parts = set(Path(dirpath).parts)
        if parts & ALLOWED_DIR_PARTS:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in ALLOWED_DIR_PARTS]
        for name in filenames:
            p = Path(dirpath) / name
            if name in ALLOWED_FILES:
                continue
            if p.suffix and p.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            yield p


def _is_placeholder(line: str) -> bool:
    lower = line.lower()
    return any(marker.lower() in lower for marker in PLACEHOLDER_MARKERS)


def scan_path(path: Path) -> List[Tuple[Path, int, str, str]]:
    hits: List[Tuple[Path, int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _is_placeholder(line):
            continue
        for name, regex in PATTERNS:
            if regex.search(line):
                hits.append((path, lineno, name, line.strip()))
    return hits


def main(argv: List[str] | None = None) -> int:
    paths = list(_walk(ROOT))
    findings: List[Tuple[Path, int, str, str]] = []
    for p in paths:
        findings.extend(scan_path(p))
    if findings:
        print(f"Found {len(findings)} potential secret(s):", file=sys.stderr)
        for path, lineno, name, line in findings:
            rel = path.relative_to(ROOT)
            print(f"  {rel}:{lineno}  [{name}]  {line[:120]}", file=sys.stderr)
        return 1
    print(f"Secret scan clean. Scanned {len(paths)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
