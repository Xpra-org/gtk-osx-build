#!/usr/bin/env python3
"""Compare and apply gtk-osx-build moduleset branch updates."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BRANCH_ATTRS = ("module", "version", "hash", "repo", "checkoutdir")


def version_key(version: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part.lower() for part in re.split(r"([0-9]+)", version))


def run(repo: Path, *args: str) -> None:
    subprocess.run(args, cwd=repo, check=True)


def git_lines(repo: Path, *args: str) -> list[str]:
    return subprocess.check_output(args, cwd=repo, text=True).splitlines()


def selected_files(local: Path, upstream: Path, scopes: set[str], include_untracked: bool) -> list[Path]:
    tracked = set(git_lines(local, "git", "ls-files"))
    candidates: list[Path] = []
    if "root" in scopes:
        candidates.extend(sorted(p.relative_to(upstream) for p in upstream.glob("*.modules")))
    if "modulesets-stable" in scopes:
        stable = upstream / "modulesets-stable"
        candidates.extend(sorted(p.relative_to(upstream) for p in stable.glob("*.modules")))
    out: list[Path] = []
    for rel in candidates:
        if not (local / rel).exists():
            continue
        if include_untracked or str(rel) in tracked:
            out.append(rel)
    return out


def branch_map(path: Path) -> dict[str, tuple[str, dict[str, str]]]:
    root = ET.parse(path).getroot()
    parents = {}
    for elem in root.iter():
        for child in list(elem):
            parents[child] = elem
    out: dict[str, tuple[str, dict[str, str]]] = {}
    for branch in root.iter("branch"):
        version = branch.get("version")
        module = branch.get("module")
        if not version or not module:
            continue
        parent = parents.get(branch)
        while parent is not None and parent.tag in {"branch", "dependencies", "after", "if"}:
            parent = parents.get(parent)
        ident = parent.get("id") if parent is not None else module
        if ident:
            out[ident] = (version, dict(branch.attrib))
    return out


def find_updates(
    local: Path,
    upstream: Path,
    scopes: set[str],
    skips: set[str],
    include_untracked: bool,
) -> list[tuple[Path, str, str, str, dict[str, str]]]:
    updates = []
    for rel in selected_files(local, upstream, scopes, include_untracked):
        local_branches = branch_map(local / rel)
        upstream_branches = branch_map(upstream / rel)
        for ident, (up_version, up_attrs) in upstream_branches.items():
            if ident in skips or ident not in local_branches:
                continue
            local_version, _local_attrs = local_branches[ident]
            if up_version != local_version and version_key(up_version) > version_key(local_version):
                updates.append((rel, ident, local_version, up_version, up_attrs))
    return updates


def module_block_pattern(ident: str) -> re.Pattern[str]:
    quoted = re.escape(ident)
    return re.compile(
        r'(?P<start><(?P<tag>[A-Za-z0-9_+.-]+)\b(?=[^>]*\bid="' + quoted + r'")[^>]*>)'
        r"(?P<body>.*?)"
        r"(?P<end></(?P=tag)>)",
        re.S,
    )


def set_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(r'(\b' + re.escape(name) + r'=)"[^"]*"')
    if pattern.search(tag):
        return pattern.sub(r'\1"' + value + '"', tag, count=1)
    close = "/>" if tag.rstrip().endswith("/>") else ">"
    index = tag.rfind(close)
    if index < 0:
        raise ValueError("cannot find XML tag close")
    return tag[:index] + f' {name}="{value}"' + tag[index:]


def remove_attr(tag: str, name: str) -> str:
    return re.sub(r"\s+\b" + re.escape(name) + r'="[^"]*"', "", tag, count=1)


def update_branch_tag(branch_tag: str, upstream_attrs: dict[str, str]) -> str:
    for attr in sorted(set(BRANCH_ATTRS) - set(upstream_attrs)):
        branch_tag = remove_attr(branch_tag, attr)
    for attr in BRANCH_ATTRS:
        if attr in upstream_attrs:
            branch_tag = set_attr(branch_tag, attr, upstream_attrs[attr])
    return branch_tag


def apply_one(local: Path, rel: Path, ident: str, upstream_attrs: dict[str, str], message_body: str) -> str:
    path = local / rel
    text = path.read_text()
    matches = list(module_block_pattern(ident).finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"{rel}:{ident}: expected 1 module block, found {len(matches)}")
    match = matches[0]
    block = match.group(0)
    branch_matches = list(re.finditer(r"<branch\b[^>]*>", block, re.S))
    if len(branch_matches) != 1:
        raise RuntimeError(f"{rel}:{ident}: expected 1 branch tag, found {len(branch_matches)}")
    branch_match = branch_matches[0]
    old_branch = branch_match.group(0)
    new_branch = update_branch_tag(old_branch, upstream_attrs)
    if old_branch == new_branch:
        raise RuntimeError(f"{rel}:{ident}: no branch attribute changes")
    new_block = block[: branch_match.start()] + new_branch + block[branch_match.end() :]
    path.write_text(text[: match.start()] + new_block + text[match.end() :])
    ET.parse(path)
    run(local, "git", "diff", "--check", "--", str(rel))
    run(local, "git", "add", str(rel))
    subject = f"{ident} {upstream_attrs['version']}"
    run(local, "git", "commit", "-m", subject, "-m", message_body)
    return subprocess.check_output(["git", "-C", str(local), "rev-parse", "--short", "HEAD"], text=True).strip()


def parse_csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "apply"))
    parser.add_argument("--local", required=True, type=Path)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--scope", default="root,modulesets-stable")
    parser.add_argument("--skip", default="")
    parser.add_argument("--include-untracked", action="store_true")
    parser.add_argument("--message-body", default="update merged from https://github.com/jralls/gtk-osx-build")
    args = parser.parse_args()

    scopes = parse_csv(args.scope)
    skips = parse_csv(args.skip)
    updates = find_updates(args.local, args.upstream, scopes, skips, args.include_untracked)
    if args.command == "list":
        for rel, ident, old, new, _attrs in updates:
            print(f"{rel}\t{ident}\t{old}\t{new}")
        return 0
    for rel, ident, old, new, attrs in updates:
        commit = apply_one(args.local, rel, ident, attrs, args.message_body)
        print(f"{commit}\t{rel}\t{ident}\t{old}\t{new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
