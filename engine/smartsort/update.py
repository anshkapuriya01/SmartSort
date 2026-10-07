"""Sorting new files into a folder SmartSort has organized before.

After an organize, the folder holds SmartSort's folders plus, over time, new loose files.
Re-analyzing it should only look at the new files and put each one into the existing folder
it belongs to; only files that fit none of them get new folders. Files the person chose to
leave in place last time are remembered and skipped.

State lives next to the undo history in `<folder>/.smartsort/`:
    history/*.jsonl   every move made (apply.py); tells us which folders are SmartSort's
    state.json        {"scheme": "grouped", "kept": [{"name": "...", "size": 123}]}
"""

from __future__ import annotations

import json
from pathlib import Path

from .apply import STATE_DIR
from .extract import CODE_EXT, DOC_EXT, list_files

SAMPLES_PER_FOLDER = 12  # documents read from each existing folder to learn what it holds
SPECIAL = {"Needs Review", "Duplicates"}  # catch-alls: never a destination by similarity


def _state_file(root: Path) -> Path:
    return root / STATE_DIR / "state.json"


def load_state(root: Path) -> dict:
    try:
        return json.loads(_state_file(root).read_text())
    except (OSError, ValueError):
        return {}


def save_state(root: Path, scheme: str | None, kept: list[Path]) -> None:
    """Remember the layout used and the files left in place. Files kept on earlier runs that
    are still loose (and unchanged) stay remembered."""
    old = load_state(root)
    entries = {(k["name"], k["size"]) for k in old.get("kept", [])
               if (root / k["name"]).is_file() and (root / k["name"]).stat().st_size == k["size"]}
    for p in kept:
        if p.is_file() and p.parent == root:
            entries.add((p.name, p.stat().st_size))
    state = {"scheme": scheme or old.get("scheme"), "kept": [{"name": n, "size": s} for n, s in sorted(entries)]}
    _state_file(root).parent.mkdir(parents=True, exist_ok=True)
    _state_file(root).write_text(json.dumps(state, indent=1))


def kept_files(root: Path) -> set[Path]:
    """Loose files the person chose to leave in place, if they haven't changed since."""
    out = set()
    for k in load_state(root).get("kept", []):
        p = root / k["name"]
        if p.is_file() and p.stat().st_size == k["size"]:
            out.add(p)
    return out


def existing_folders(root: Path) -> dict[str, list[Path]]:
    """SmartSort's folders that still exist (relative path -> the files in them now).

    Only folders SmartSort made are used, so a person's own folders are never filled."""
    history = root / STATE_DIR / "history"
    folders: set[str] = set()
    for journal in sorted(history.glob("*.jsonl")) if history.is_dir() else []:
        for line in journal.read_text().splitlines():
            try:
                e = json.loads(line)
                src, dst = Path(e["from"]), Path(e["to"])
            except (ValueError, KeyError):
                continue
            # Relative to the folder as it was then (the moved file's old home), so a folder
            # that has since been moved or renamed still knows its own subfolders.
            if not dst.parent.is_relative_to(src.parent) or dst.parent == src.parent:
                continue
            rel = dst.parent.relative_to(src.parent)
            if (root / rel).is_dir():
                folders.add(rel.as_posix())
    return {rel: list_files(root / rel) for rel in sorted(folders)}


def is_organized(root: Path) -> bool:
    return bool(existing_folders(root))


def document_samples(folders: dict[str, list[Path]]) -> dict[str, list[Path]]:
    """Up to SAMPLES_PER_FOLDER recent documents from each folder that can take new documents."""
    out = {}
    for rel, files in folders.items():
        if rel.split("/")[0] in SPECIAL or rel.split("/")[0] == "Images":
            continue
        docs = [p for p in files if p.suffix.lower() in DOC_EXT or p.suffix.lower() in CODE_EXT]
        docs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if docs:
            out[rel] = docs[:SAMPLES_PER_FOLDER]
    return out
