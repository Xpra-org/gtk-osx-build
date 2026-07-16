---
name: gtk-osx-release-updater
description: Find and apply direct upstream release updates in gtk-osx-build JHBuild modulesets. Use when Codex must compare pinned projects with official release sources, update selected archive paths/versions/SHA-256 hashes, keep duplicate or coordinated module IDs synchronized, verify retained patches against new sources, and create one focused git commit per requested project or package family.
---

# GTK-OSX Release Updater

Update project pins from each project's official release source. Do not use the
`gtk-osx-moduleset-updater` skill for this workflow; that skill compares against
another gtk-osx-build checkout.

## Workflow

1. Inspect `git status --short` and preserve unrelated tracked and untracked work.
2. Locate every tracked definition of each requested module ID:

   ```bash
   rg -n -A8 -B3 'id="MODULE_ID"' modulesets-stable/*.modules xpra-*.modules
   ```

3. Resolve the newest appropriate stable release from the official source:

   - PyPI: use `https://pypi.org/pypi/PROJECT/VERSION/json`.
   - GitHub: use the official releases page or release API.
   - GNOME, GNU, Xiph, SQLite, and similar projects: inspect their official
     source archive index.
   - Exclude prereleases, odd-numbered development series, `.90` snapshots,
     release candidates, and platform-specific binary archives unless requested.
   - Treat major-version changes as potentially incompatible and report them
     before applying unless the user explicitly selected them.

4. Download the exact source archive and calculate SHA-256 locally. For PyPI,
   prefer the sdist URL and digest from the version JSON, then verify the
   downloaded file with `sha256sum`.
5. Prepare one update unit per requested project. Group only definitions that
   must remain synchronized:

   - duplicate module IDs in multiple tracked modulesets;
   - alternate build variants such as `glib` and `glib-no-introspection`;
   - coordinated package families such as PyObjC core and frameworks.

6. Apply explicit pins with `scripts/moduleset_pin.py`, or edit carefully when
   removing obsolete patches or changing build metadata. Preserve dependencies,
   child patches, and local build arguments.
7. Parse every affected XML file and run `git diff --check`.
8. For each retained `<patch>` in an updated module, extract the new archive and
   run `patch --dry-run` with its declared strip level. Refresh the patch in the
   same update commit if necessary. Remove a patch only when the new upstream
   source demonstrably implements the same behavior.
9. Stage only files belonging to that update unit and commit immediately.
10. Finish by parsing all tracked modulesets, checking the full diff, listing
    the created commits, and confirming unrelated work is untouched.

## Manifest Helper

Use a temporary JSON manifest for deterministic branch-tag updates:

```json
{
  "subject": "glib 2.88.2",
  "updates": [
    {
      "id": "glib",
      "old_version": "2.88.0",
      "attrs": {
        "module": "glib/2.88/glib-2.88.2.tar.xz",
        "version": "2.88.2",
        "hash": "sha256:..."
      }
    },
    {
      "id": "glib-no-introspection",
      "old_version": "2.88.0",
      "attrs": {
        "module": "glib/2.88/glib-2.88.2.tar.xz",
        "version": "2.88.2",
        "hash": "sha256:..."
      }
    }
  ]
}
```

Preview matches:

```bash
python3 .codex/skills/gtk-osx-release-updater/scripts/moduleset_pin.py \
  --repo "$PWD" --manifest /tmp/update.json --check
```

Apply and commit:

```bash
python3 .codex/skills/gtk-osx-release-updater/scripts/moduleset_pin.py \
  --repo "$PWD" --manifest /tmp/update.json --commit
```

Each update may include a `files` array to restrict matching to named tracked
modulesets. Without it, update every tracked occurrence of the ID.

## Commit Rules

- Create one commit per project or explicitly coordinated family.
- Use concise subjects such as `gtk 4.22.4` or `pyobjc 12.2.1`.
- Include changed compatibility patches in the same project commit.
- Never stage unrelated tracked changes or untracked files.
- If a late patch check requires a fixup, autosquash it into the original
  project commit before handoff.

## Validation

Run after all updates:

```bash
python3 - <<'PY'
import subprocess
import xml.etree.ElementTree as ET

files = subprocess.check_output(
    ["git", "ls-files", "*.modules", "modulesets-stable/*.modules"],
    text=True,
).splitlines()
for path in files:
    ET.parse(path)
print(f"parsed {len(files)} tracked moduleset files")
PY

git diff --check BASE..HEAD
git log --reverse --format='%h %s' BASE..HEAD
git status --short --branch
```
