#!/usr/bin/env python3
"""Validate an ArchaeoGPR Obsidian vault: wikilinks, orphan notes, disallowed files.

Usage:
    python scripts/validate_obsidian_vault.py obsidian/ArchaeoGPR_Vault
    python scripts/validate_obsidian_vault.py obsidian/ArchaeoGPR_Vault --strict-orphans

Checks performed:
  1. Every [[wikilink]] target resolves to exactly one Markdown file in the vault.
  2. Every note has at least one incoming wikilink (orphan check) — reported
     always; only affects the exit code if --strict-orphans is passed, since
     orphan-ness is explicitly an optional/advisory check per the project spec.
  3. No disallowed binary/oversized files exist under the vault (Markdown-only
     knowledge base; QC binaries belong under the repo's outputs/ directory
     and should only ever be linked from vault notes, not copied in).

Exit code is non-zero if any broken wikilink or disallowed file is found
(and, with --strict-orphans, if any orphan note is found).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ALLOWED_TEXT_SUFFIXES = {".md"}
ALLOWED_CONFIG_DIR_NAMES = {".obsidian"}
MAX_ALLOWED_FILE_BYTES = 512 * 1024  # 512 KiB — generous for Markdown/small config, not for binaries

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)")
CODE_FENCE_PATTERN = re.compile(r"```.*?```", re.DOTALL)


def strip_code_fences(text: str) -> str:
    """Remove fenced code blocks so their contents can't be misread as wikilinks."""
    return CODE_FENCE_PATTERN.sub("", text)


def find_markdown_files(vault_root: Path) -> list[Path]:
    return sorted(p for p in vault_root.rglob("*.md") if p.is_file())


def extract_wikilinks(markdown_text: str) -> list[str]:
    body = strip_code_fences(markdown_text)
    return [match.group(1).strip() for match in WIKILINK_PATTERN.finditer(body)]


def build_note_index(md_files: list[Path], vault_root: Path) -> dict[str, list[Path]]:
    """Map every plausible link key (basename, and vault-relative path) to its file(s)."""
    index: dict[str, list[Path]] = {}
    for path in md_files:
        rel_no_ext = path.relative_to(vault_root).with_suffix("").as_posix()
        basename = path.stem
        for key in {rel_no_ext, basename}:
            index.setdefault(key, []).append(path)
    return index


def resolve_link(link_target: str, note_index: dict[str, list[Path]]) -> list[Path]:
    normalized = link_target.strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return note_index.get(normalized, [])


def check_wikilinks(
    md_files: list[Path], vault_root: Path
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str, list[Path]]], dict[Path, set[Path]]]:
    """Returns (broken_links, ambiguous_links, incoming_edges)."""
    note_index = build_note_index(md_files, vault_root)
    broken: list[tuple[Path, str]] = []
    ambiguous: list[tuple[Path, str, list[Path]]] = []
    incoming: dict[Path, set[Path]] = {path: set() for path in md_files}

    for path in md_files:
        text = path.read_text(encoding="utf-8")
        for link in extract_wikilinks(text):
            targets = resolve_link(link, note_index)
            unique_targets = sorted(set(targets))
            if not unique_targets:
                broken.append((path, link))
            elif len(unique_targets) > 1:
                ambiguous.append((path, link, unique_targets))
            else:
                target = unique_targets[0]
                if target != path:
                    incoming[target].add(path)

    return broken, ambiguous, incoming


def find_orphans(md_files: list[Path], incoming: dict[Path, set[Path]]) -> list[Path]:
    return sorted(path for path in md_files if not incoming.get(path))


def find_disallowed_files(vault_root: Path) -> list[tuple[Path, str]]:
    disallowed: list[tuple[Path, str]] = []
    for path in vault_root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in ALLOWED_CONFIG_DIR_NAMES for part in path.relative_to(vault_root).parts[:-1]):
            continue
        if path.suffix.lower() in ALLOWED_TEXT_SUFFIXES:
            continue
        if path.name == ".gitkeep":
            continue
        size = path.stat().st_size
        if size > MAX_ALLOWED_FILE_BYTES:
            disallowed.append((path, f"{size} bytes > {MAX_ALLOWED_FILE_BYTES} byte limit"))
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            disallowed.append((path, "binary content"))
    return disallowed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vault_path", type=Path, help="Path to the Obsidian vault root")
    parser.add_argument(
        "--strict-orphans", action="store_true", help="Also fail (non-zero exit) if any orphan note is found"
    )
    args = parser.parse_args(argv)

    vault_root = args.vault_path.resolve()
    if not vault_root.is_dir():
        print(f"Error: vault path does not exist or is not a directory: {vault_root}", file=sys.stderr)
        return 2

    md_files = find_markdown_files(vault_root)
    print(f"Vault: {vault_root}")
    print(f"Markdown notes found: {len(md_files)}")

    broken, ambiguous, incoming = check_wikilinks(md_files, vault_root)
    orphans = find_orphans(md_files, incoming)
    disallowed = find_disallowed_files(vault_root)

    ok = True

    print(f"\nBroken wikilinks: {len(broken)}")
    for source, link in broken:
        print(f"  - {source.relative_to(vault_root)} -> [[{link}]] (target not found)")
    if broken:
        ok = False

    print(f"\nAmbiguous wikilinks: {len(ambiguous)}")
    for source, link, targets in ambiguous:
        target_names = ", ".join(str(t.relative_to(vault_root)) for t in targets)
        print(f"  - {source.relative_to(vault_root)} -> [[{link}]] matches multiple files: {target_names}")
    if ambiguous:
        ok = False

    print(f"\nOrphan notes (no incoming wikilinks): {len(orphans)}")
    for path in orphans:
        print(f"  - {path.relative_to(vault_root)}")
    if orphans and args.strict_orphans:
        ok = False

    print(f"\nDisallowed binary/oversized files: {len(disallowed)}")
    for path, reason in disallowed:
        print(f"  - {path.relative_to(vault_root)} ({reason})")
    if disallowed:
        ok = False

    print(f"\nResult: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
