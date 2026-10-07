"""Turn the analysis into a concrete list of moves for a chosen folder layout."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .analyze import FileInfo

SCHEMES = {
    "grouped": ("Grouped", "Similar files together; one-off files join their closest group"),
    "detailed": ("Detailed", "A folder for every group of similar files"),
    "type": ("By Type", "Receipts, statements, contracts, notes…"),
}
REVIEW = "Needs Review"
DUPLICATES = "Duplicates"


@dataclass
class Move:
    src: Path  # absolute
    dst: Path  # relative to the folder being organised
    why: str

    @property
    def renamed(self) -> bool:
        return self.dst.name != self.src.name


def _counts(files: list[FileInfo]) -> tuple[Counter, Counter, dict[str, set]]:
    live = [f for f in files if f.duplicate_of is None]
    pairs = Counter((f.subject, f.kind) for f in live if f.subject and f.kind)
    images = Counter(f.kind for f in live if f.item.group == "image" and f.kind)
    kinds = defaultdict(set)
    for subject, kind in pairs:
        kinds[subject].add(kind)
    return pairs, images, kinds


def recommend(files: list[FileInfo]) -> str:
    return "grouped"


def folder_for(f: FileInfo, scheme: str, pairs: Counter, images: Counter, kinds: dict[str, set]) -> tuple[str, str]:
    """Subfolders are only made when they'd hold at least two files; a folder per file is
    just a different kind of mess."""
    it = f.item
    if f.duplicate_of is not None:
        return DUPLICATES, f"copy of {f.duplicate_of.name}"
    if f.target:
        return f.target, f"fits your existing “{f.target.replace('/', ' › ')}” folder"
    if it.group == "image":
        sub = f"Images/{f.kind}" if f.kind and images[f.kind] >= 2 else "Images"
        return sub, f.kind or "image"
    if it.group == "other":
        return it.category, it.category.lower()
    # documents
    group = f.detail if scheme == "detailed" else f.subject
    why = " · ".join(x for x in [group, f.kind, f.note] if x)
    if scheme == "type":
        return (f.kind or REVIEW), why or "unsure what this is"
    if not group:
        return REVIEW, why or "not like any other file"
    # In the Grouped layout a big group splits by document type when that makes 2+ real subfolders.
    if scheme == "grouped" and f.kind and len(kinds[group]) >= 2 and pairs[(group, f.kind)] >= 2 \
            and sum(1 for (g, _k), n in pairs.items() if g == group and n >= 2) >= 2:
        return f"{group}/{f.kind}", why
    return group, why


def build_plan(files: list[FileInfo], scheme: str, rename: bool = True, root: Path | None = None) -> list[Move]:
    """With `root`, names already taken inside existing folders are avoided too."""
    pairs, images, kinds = _counts(files)
    moves, taken = [], set()
    for f in sorted(files, key=lambda f: f.item.name.lower()):
        folder, why = folder_for(f, scheme, pairs, images, kinds)
        name = (f.new_name if rename and f.new_name and f.duplicate_of is None else None) or f.item.name
        dst = Path(folder) / name
        n = 2
        while dst.as_posix().lower() in taken or (root is not None and (root / dst).exists()):
            dst = Path(folder) / f"{Path(name).stem} ({n}){Path(name).suffix}"
            n += 1
        taken.add(dst.as_posix().lower())
        moves.append(Move(src=f.item.path, dst=dst, why=why))
    return moves


def render_tree(moves: list[Move], color: bool = True, show_files: bool = True) -> str:
    def c(code, s):
        return f"\033[{code}m{s}\033[0m" if color else s

    tree: dict = {}
    for m in moves:
        node = tree
        for part in m.dst.parent.parts:
            node = node.setdefault(part + "/", {})
        node.setdefault("__files__", []).append(m)

    def count(node) -> int:
        return len(node.get("__files__", [])) + sum(count(v) for k, v in node.items() if k != "__files__")

    def order(name):  # real folders first, catch-alls last
        last = {REVIEW + "/": 3, DUPLICATES + "/": 4, "Images/": 2}
        return (last.get(name, 0), name.lower())

    lines = []

    def walk(node, indent):
        for name in sorted((k for k in node if k != "__files__"), key=order):
            sub = node[name]
            colour = "33" if name in (REVIEW + "/", DUPLICATES + "/") else "1;34"
            lines.append(f"{indent}{c(colour, name)} {c('2', f'({count(sub)})')}")
            walk(sub, indent + "    ")
        if show_files:
            for m in sorted(node.get("__files__", []), key=lambda m: m.dst.name.lower()):
                if m.renamed:
                    lines.append(f"{indent}{c('2', m.src.name)} {c('2', '→')} {c('32', m.dst.name)}")
                else:
                    lines.append(f"{indent}{m.dst.name}")

    walk(tree, "  ")
    return "\n".join(lines)
