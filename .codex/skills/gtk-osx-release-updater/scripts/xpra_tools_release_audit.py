#!/usr/bin/env python3
"""Query official release endpoints used by xpra-tools.modules."""

from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen


URLS = {
    "perl": "https://fastapi.metacpan.org/v1/release/perl",
    "lz4": "https://api.github.com/repos/lz4/lz4/releases/latest",
    "brotli": "https://api.github.com/repos/google/brotli/releases/latest",
    "xxhash": "https://api.github.com/repos/Cyan4973/xxHash/releases/latest",
    "curl": "https://api.github.com/repos/curl/curl/releases/latest",
    "sqlite": "https://www.sqlite.org/download.html",
    "gnu-cpio": "https://ftp.gnu.org/gnu/cpio/",
    "grep": "https://ftp.gnu.org/gnu/grep/",
    "gmp": "https://gmplib.org/download/gmp/",
    "mpfr": "https://www.mpfr.org/mpfr-current/",
    "sshpass": "https://sourceforge.net/projects/sshpass/files/",
    "bomutils": "https://api.github.com/repos/hogliux/bomutils/tags?per_page=20",
}
PATTERNS = {
    "sqlite": r"sqlite-autoconf-([0-9]+)\.tar\.gz",
    "gnu-cpio": r"cpio-([0-9]+(?:\.[0-9]+)+)\.tar",
    "grep": r"grep-([0-9]+(?:\.[0-9]+)+)\.tar",
    "gmp": r"gmp-([0-9]+(?:\.[0-9]+)+)\.tar",
    "mpfr": r"mpfr-([0-9]+(?:\.[0-9]+)+)\.tar",
    "sshpass": r"sshpass-([0-9]+(?:\.[0-9]+)+)\.tar",
}


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "gtk-osx-release-updater"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


for name, url in URLS.items():
    try:
        data = fetch(url)
        if name in {"perl", "lz4", "brotli", "xxhash", "curl"}:
            release = json.loads(data)
            print(name, release.get("version") or release.get("tag_name"))
        elif name == "bomutils":
            print(name, [tag["name"] for tag in json.loads(data)])
        else:
            print(name, sorted(set(re.findall(PATTERNS[name], data))))
    except Exception as error:
        print(name, "ERROR", error)
