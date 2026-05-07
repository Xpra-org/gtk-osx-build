---
name: gtk-osx-moduleset-updater
description: Compare and update gtk-osx-build JHBuild moduleset XML files from an upstream checkout. Use when Codex needs to list library updates available from another gtk-osx-build repository, apply selected module branch version/module/hash changes, skip named packages, limit scope to root modulesets or modulesets-stable, and create one git commit per package update with a required commit message body.
---

# GTK-OSX Moduleset Updater

## Workflow

Use this skill for repeatable update passes between a local gtk-osx-build checkout and an upstream checkout such as `$HOME/projects/gtk-osx-build.upstream`.

1. Confirm the local repo, upstream repo, scope, skips, and commit body from the user request.
2. Run `scripts/moduleset_update.py list` to see upstream-newer branch pins.
3. If asked to apply updates, run `scripts/moduleset_update.py apply` with the same scope and skips.
4. Verify XML parsing and `git status --short` for the affected files.
5. Report commit hashes and any intentionally skipped or untracked modulesets.

## Script

Prefer the bundled script instead of hand-editing XML. It parses moduleset files, compares branch `version` values by module id, copies upstream branch attributes into the local file, preserves local child patches/dependencies, and commits one update at a time.

List updates from stable modulesets and matching root-level modulesets:

```bash
python3 .codex/skills/gtk-osx-moduleset-updater/scripts/moduleset_update.py list \
  --local $HOME/projects/gtk-osx-build \
  --upstream $HOME/projects/gtk-osx-build.upstream \
  --scope root,modulesets-stable
```

Apply updates while skipping packages:

```bash
python3 .codex/skills/gtk-osx-moduleset-updater/scripts/moduleset_update.py apply \
  --local $HOME/projects/gtk-osx-build \
  --upstream $HOME/projects/gtk-osx-build.upstream \
  --scope root,modulesets-stable \
  --skip openssl,python3 \
  --message-body "update merged from https://github.com/jralls/gtk-osx-build"
```

By default the script only modifies tracked files. Use `--include-untracked` only when the user explicitly wants to add a new moduleset file.

## Guardrails

- Stage only the moduleset file being updated for each commit.
- Do not touch unrelated untracked files in `gtk-osx-build`.
- Skip packages exactly by module id, for example `openssl` or `python3`.
- Root scope means root-level `*.modules` files that exist in both repositories.
- Stable scope means `modulesets-stable/*.modules` files that exist in both repositories.
- If a moduleset exists only as an untracked local file, mention it and leave it alone unless explicitly requested.
- If a package appears in more than one moduleset, commit each file update separately unless the user asks for a different grouping.
