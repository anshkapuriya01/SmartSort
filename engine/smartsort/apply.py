"""Carry out a plan safely, and undo it.

Safety rules: never delete or overwrite a file, only move within the chosen folder,
and journal every move *before* making it so an interrupted run can still be undone.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .plan import Move

STATE_DIR = ".smartsort"


def _free_name(path: Path) -> Path:
    n, candidate = 2, path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def apply_plan(root: Path, moves: list[Move]) -> tuple[int, list[str], Path]:
    history = root / STATE_DIR / "history"
    history.mkdir(parents=True, exist_ok=True)
    journal = history / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    moved, problems = 0, []
    with journal.open("a") as log:
        for m in moves:
            dst = root / m.dst
            if m.src.parent == dst.parent and m.src.name == dst.name:
                continue
            if not m.src.exists():
                problems.append(f"{m.src.name}: no longer there, skipped")
                continue
            new_dirs = [p for p in reversed(dst.parents) if p.is_relative_to(root) and not p.exists()]
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst = _free_name(dst)
            log.write(json.dumps({"from": str(m.src), "to": str(dst), "dirs": [str(d) for d in new_dirs]}) + "\n")
            log.flush()
            os.fsync(log.fileno())
            os.rename(m.src, dst)  # same folder tree, so this is an atomic rename
            moved += 1
    return moved, problems, journal


def undo_last(root: Path) -> tuple[int, list[str]]:
    history = root / STATE_DIR / "history"
    journals = sorted(history.glob("*.jsonl")) if history.exists() else []
    if not journals:
        raise FileNotFoundError("Nothing to undo in this folder.")
    journal = journals[-1]
    entries = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    restored, problems, dirs = 0, [], []
    for e in reversed(entries):
        src, dst = Path(e["from"]), Path(e["to"])
        dirs_now = [Path(d) for d in e["dirs"]]
        old_root = src.parent
        if old_root != root:  # the folder was moved or renamed since: follow it
            src, dst = root / src.name, root / dst.relative_to(old_root)
            dirs_now = [root / d.relative_to(old_root) for d in dirs_now]
        dirs.extend(dirs_now)
        if not dst.exists():
            problems.append(f"{dst.name}: not found (moved or deleted since), skipped")
            continue
        if src.exists():
            problems.append(f"{src.name}: something new already has this name, left {dst.name} where it is")
            continue
        src.parent.mkdir(parents=True, exist_ok=True)
        os.rename(dst, src)
        restored += 1
    for d in sorted(set(dirs), key=lambda p: len(p.parts), reverse=True):
        try:
            junk = d / ".DS_Store"
            if junk.exists() and len(list(d.iterdir())) == 1:
                junk.unlink()
            d.rmdir()  # only succeeds if empty, so nothing of the user's is touched
        except OSError:
            pass
    journal.rename(journal.with_suffix(".undone"))
    return restored, problems
