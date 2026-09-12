#!/usr/bin/env python3
"""Report newer stable PyPI releases pinned in a JHBuild moduleset."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from packaging.version import InvalidVersion, Version


def project_name(branch: ET.Element, index: int) -> str:
    parts = branch.attrib["module"].split("/")
    try:
        return parts[index]
    except IndexError as error:
        raise ValueError(f"cannot find project segment {index} in {branch.attrib['module']}") from error


def latest_stable(releases: dict[str, object]) -> Version:
    versions = []
    for value, urls in releases.items():
        try:
            version = Version(value)
        except InvalidVersion:
            continue
        if not version.is_prerelease and not version.is_devrelease and urls:
            versions.append(version)
    if not versions:
        raise ValueError("no stable releases")
    return max(versions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("moduleset", help="XML moduleset to audit")
    parser.add_argument(
        "--project-index", type=int, default=1,
        help="slash-separated module path segment holding the PyPI project (default: 1)",
    )
    args = parser.parse_args()

    root = ET.parse(args.moduleset).getroot()
    for node in root:
        branch = node.find("branch")
        if branch is None or "module" not in branch.attrib or "version" not in branch.attrib:
            continue
        try:
            project = project_name(branch, args.project_index)
            request = Request(
                f"https://pypi.org/pypi/{project}/json",
                headers={"User-Agent": "gtk-osx-release-updater"},
            )
            with urlopen(request, timeout=30) as response:
                latest = latest_stable(json.load(response)["releases"])
            current = Version(branch.attrib["version"])
            if latest > current:
                print(
                    f"UPDATE\t{node.attrib['id']}\t{project}\t{current}\t{latest}"
                    f"\tmajor={latest.major != current.major}"
                )
            elif latest < current:
                print(f"AHEAD\t{node.attrib['id']}\t{project}\t{current}\t{latest}")
        except Exception as error:
            print(f"ERROR\t{node.attrib.get('id', '<unknown>')}\t{error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
