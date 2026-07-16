#!/usr/bin/env python3
"""Apply explicit release pins to tracked JHBuild modulesets."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def git_lines(repo: Path, *args: str) -> list[str]:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).splitlines()


def module_pattern(ident: str) -> re.Pattern[str]:
    quoted = re.escape(ident)
    return re.compile(
        r'(?P<start><(?P<tag>[A-Za-z0-9_+.-]+)\b(?=[^>]*\bid="' + quoted + r'")[^>]*>)'
        r"(?P<body>.*?)"
        r"(?P<end></(?P=tag)>)",
        re.S,
    )


def set_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(r"(\b" + re.escape(name) + r'=)([\"\'])(.*?)(\2)')
    if pattern.search(tag):
        return pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}{value}{match.group(2)}", tag, count=1)
    close = "/>" if tag.rstrip().endswith("/>") else ">"
    index = tag.rfind(close)
    if index < 0:
        raise ValueError(f"cannot add {name}: malformed branch tag")
    return tag[:index] + f' {name}="{value}"' + tag[index:]


def update_block(block: str, old_version: str, attrs: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    branches = list(re.finditer(r"<branch\b[^>]*>", block, re.S))
    if len(branches) != 1:
        raise RuntimeError(f"expected one branch tag, found {len(branches)}")
    match = branches[0]
    old_tag = match.group(0)
    version_match = re.search(r'\bversion=(["\'])(.*?)\1', old_tag)
    current = version_match.group(2) if version_match else ""
    if current != old_version:
        raise RuntimeError(f"expected version {old_version}, found {current or '(missing)'}")
    new_tag = old_tag
    for name, value in attrs.items():
        new_tag = set_attr(new_tag, name, value)
    patch_info = []
    for patch_tag in re.findall(r"<patch\b[^>]*?/?>", block, re.S):
        file_match = re.search(r'\bfile=(["\'])(.*?)\1', patch_tag)
        strip_match = re.search(r'\bstrip=(["\'])(.*?)\1', patch_tag)
        if file_match:
            patch_info.append((file_match.group(2), strip_match.group(2) if strip_match else "1"))
    return block[: match.start()] + new_tag + block[match.end() :], patch_info


def candidate_files(repo: Path, requested: list[str] | None) -> list[Path]:
    tracked = [
        Path(path)
        for path in git_lines(repo, "ls-files", "*.modules", "modulesets-stable/*.modules")
    ]
    if not requested:
        return tracked
    wanted = {Path(path) for path in requested}
    missing = wanted - set(tracked)
    if missing:
        raise RuntimeError(f"untracked or missing modulesets: {', '.join(map(str, sorted(missing)))}")
    return [path for path in tracked if path in wanted]


def ensure_clean(repo: Path, paths: set[Path]) -> None:
    dirty = git_lines(repo, "status", "--porcelain", "--", *map(str, sorted(paths)))
    if dirty:
        raise RuntimeError("refusing to overwrite tracked changes:\n" + "\n".join(dirty))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    manifest = json.loads(args.manifest.read_text())
    subject = manifest.get("subject", "").strip()
    updates = manifest.get("updates")
    if not subject or not isinstance(updates, list) or not updates:
        raise RuntimeError("manifest requires a subject and non-empty updates list")

    planned: dict[Path, str] = {}
    matched_ids: dict[str, int] = {}
    patch_notes: list[tuple[str, Path, str, str]] = []

    for update in updates:
        ident = update["id"]
        old_version = update["old_version"]
        attrs = update["attrs"]
        if not {"module", "version", "hash"} <= set(attrs):
            raise RuntimeError(f"{ident}: attrs must include module, version, and hash")
        files = candidate_files(repo, update.get("files"))
        matches = 0
        for relative in files:
            text = planned.get(relative, (repo / relative).read_text())
            found = list(module_pattern(ident).finditer(text))
            if not found:
                continue
            if len(found) != 1:
                raise RuntimeError(f"{relative}:{ident}: expected one module block, found {len(found)}")
            match = found[0]
            new_block, patches = update_block(match.group(0), old_version, attrs)
            planned[relative] = text[: match.start()] + new_block + text[match.end() :]
            matches += 1
            for patch, strip in patches:
                patch_notes.append((ident, relative, patch, strip))
        if matches == 0:
            raise RuntimeError(f"{ident}: no matching tracked module definition")
        matched_ids[ident] = matches

    ensure_clean(repo, set(planned))
    for ident, count in matched_ids.items():
        print(f"{ident}: {count} definition(s)")
    for ident, relative, patch, strip in patch_notes:
        print(f"PATCH\t{ident}\t{relative}\t{patch}\t-p{strip}")
    if args.check:
        for relative in sorted(planned):
            print(f"WOULD_UPDATE\t{relative}")
        return 0

    for relative, text in planned.items():
        path = repo / relative
        path.write_text(text)
        ET.parse(path)
    subprocess.run(["git", "diff", "--check", "--", *map(str, sorted(planned))], cwd=repo, check=True)
    subprocess.run(["git", "add", "--", *map(str, sorted(planned))], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", subject], cwd=repo, check=True)
    print(subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True).strip())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
