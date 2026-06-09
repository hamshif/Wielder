#!/usr/bin/env python
"""Pre-commit security/versioning gate for reusable Wielder repositories."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    ("aws_access_key_id", r"\bAKIA[0-9A-Z]{16}\b"),
    ("aws_secret_access_key_literal", r"(?i)aws_secret_access_key\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
    ("private_key_block", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    label: str
    text: str


def _run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def _git_root(repo: Path) -> Path:
    try:
        return Path(_run_git(repo, ["rev-parse", "--show-toplevel"]).strip())
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{repo} is not a git repository") from exc


def _candidate_files(repo: Path) -> list[Path]:
    output = _run_git(repo, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    return [repo / item for item in output.split("\0") if item]


def _compile_patterns(args: argparse.Namespace) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for token in args.forbidden_token:
        patterns.append((f"forbidden token {token!r}", re.compile(re.escape(token), re.IGNORECASE)))
    for pattern in args.forbidden_regex:
        patterns.append((f"forbidden regex {pattern!r}", re.compile(pattern, re.IGNORECASE)))
    if not args.skip_secret_patterns:
        for label, pattern in DEFAULT_SECRET_PATTERNS:
            patterns.append((label, re.compile(pattern)))
    return patterns


def _is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:32768]
    except OSError:
        return True
    return b"\0" in chunk


def _is_excluded(path: Path, repo: Path, excludes: list[str]) -> bool:
    rel = path.relative_to(repo).as_posix()
    for exclude in excludes:
        clean = exclude.rstrip("/")
        if rel == clean or rel.startswith(clean + "/"):
            return True
    return False


def _scan_file(path: Path, repo: Path, patterns: list[tuple[str, re.Pattern[str]]]) -> list[Finding]:
    rel = path.relative_to(repo).as_posix()
    findings: list[Finding] = []
    if _is_binary(path):
        return findings
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return findings
    for line_number, line in enumerate(lines, start=1):
        for label, pattern in patterns:
            if pattern.search(line):
                findings.append(Finding(path=rel, line=line_number, label=label, text=line.strip()))
    return findings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a reusable security versioning audit.")
    parser.add_argument("--repo", default=".", help="Repository root or a path inside it.")
    parser.add_argument("--expected-branch", default=None, help="Fail if the checked-out branch differs.")
    parser.add_argument(
        "--forbidden-token",
        action="append",
        default=[],
        help="Case-insensitive literal token that must not appear in tracked/unignored files.",
    )
    parser.add_argument(
        "--forbidden-regex",
        action="append",
        default=[],
        help="Case-insensitive regular expression that must not appear in tracked/unignored files.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Repo-relative file or directory to exclude from the scan.",
    )
    parser.add_argument("--require-clean", action="store_true", help="Fail if the working tree is dirty.")
    parser.add_argument("--skip-secret-patterns", action="store_true", help="Do not run built-in secret scans.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo = _git_root(Path(args.repo).resolve())
    branch = _run_git(repo, ["branch", "--show-current"]).strip()
    status = _run_git(repo, ["status", "--short", "--branch"])
    dirty_lines = [line for line in status.splitlines() if line and not line.startswith("##")]

    if args.expected_branch and branch != args.expected_branch:
        print(f"FAIL expected branch [{args.expected_branch}], found [{branch}]", file=sys.stderr)
        return 2
    if args.require_clean and dirty_lines:
        print("FAIL working tree is dirty:", file=sys.stderr)
        print(status, file=sys.stderr)
        return 2

    candidates = _candidate_files(repo)
    patterns = _compile_patterns(args)
    findings: list[Finding] = []
    for path in candidates:
        if _is_excluded(path, repo, args.exclude):
            continue
        if not path.is_file():
            continue
        findings.extend(_scan_file(path, repo, patterns))

    print(f"security_versioning_check repo={repo}")
    print(f"branch={branch or '<detached-or-unborn>'}")
    print(f"files_scanned={len(candidates)}")
    print(f"dirty={bool(dirty_lines)}")
    if dirty_lines:
        print("dirty_status:")
        for line in dirty_lines:
            print(f"  {line}")

    if findings:
        print("FAIL security findings:")
        for finding in findings[:200]:
            print(f"{finding.path}:{finding.line}: {finding.label}: {finding.text}")
        if len(findings) > 200:
            print(f"... {len(findings) - 200} additional finding(s) omitted")
        return 1

    print("PASS security_versioning_check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
