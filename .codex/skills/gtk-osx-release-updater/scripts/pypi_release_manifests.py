#!/usr/bin/env python3
"""Create a verified moduleset-pin manifest from selected PyPI sdists."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


def parse_update(value: str) -> tuple[str, str]:
    try:
        ident, version = value.split("=", 1)
    except ValueError as error:
        raise argparse.ArgumentTypeError("updates must use ID=VERSION") from error
    if not ident or not version:
        raise argparse.ArgumentTypeError("updates must use non-empty ID=VERSION")
    return ident, version


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "gtk-osx-release-updater"})
    with urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("moduleset", help="XML moduleset containing the selected IDs")
    parser.add_argument("--subject", required=True, help="commit subject for the manifest")
    parser.add_argument("--update", type=parse_update, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True, help="manifest JSON path")
    parser.add_argument(
        "--archives", type=Path, default=Path("/tmp/moduleset-release-archives"),
        help="directory for verified sdists (default: /tmp/moduleset-release-archives)",
    )
    parser.add_argument("--project-index", type=int, default=1)
    args = parser.parse_args()

    root = ET.parse(args.moduleset).getroot()
    branches = {
        node.attrib["id"]: node.find("branch")
        for node in root
        if node.find("branch") is not None and "id" in node.attrib
    }
    args.archives.mkdir(parents=True, exist_ok=True)
    updates = []
    for ident, new_version in args.update:
        branch = branches.get(ident)
        if branch is None or "module" not in branch.attrib or "version" not in branch.attrib:
            raise ValueError(f"{ident}: no versioned branch")
        parts = branch.attrib["module"].split("/")
        try:
            project = parts[args.project_index]
        except IndexError as error:
            raise ValueError(f"{ident}: project segment {args.project_index} is missing") from error
        metadata = json.loads(download(f"https://pypi.org/pypi/{project}/{new_version}/json"))
        sdist = next(item for item in metadata["urls"] if item["packagetype"] == "sdist")
        archive = args.archives / sdist["filename"]
        archive.write_bytes(download(sdist["url"]))
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        expected = sdist["digests"]["sha256"]
        if actual != expected:
            raise RuntimeError(f"{ident}: checksum mismatch: {actual} != {expected}")
        updates.append(
            {
                "id": ident,
                "old_version": branch.attrib["version"],
                "files": [args.moduleset],
                "attrs": {
                    "module": f"{branch.attrib['module'].rsplit('/', 1)[0]}/{sdist['filename']}",
                    "version": new_version,
                    "hash": f"sha256:{actual}",
                },
            }
        )
        print(f"verified {ident}: {archive}")
    args.output.write_text(json.dumps({"subject": args.subject, "updates": updates}, indent=2) + "\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
