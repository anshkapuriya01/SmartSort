"""The plan the person reviews: the engine's suggestion plus their changes.

No interface code here, so it can be tested on its own. Mirrors AppModel in the macOS app.
"""

from __future__ import annotations

from dataclasses import dataclass, field

REVIEW = "Needs Review"
DUPLICATES = "Duplicates"
IMAGES = "Images"


def _sort_key(text: str):
    """Finder/Explorer-like order: case-insensitive, numbers by value."""
    import re

    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


@dataclass
class Edits:
    kept: set[str] = field(default_factory=set)               # files left in place (unselected)
    keep_name: set[str] = field(default_factory=set)          # files that keep their original name
    custom_names: dict[str, str] = field(default_factory=dict)
    moved_to: dict[str, str] = field(default_factory=dict)     # file -> folder
    renamed_folders: dict[str, str] = field(default_factory=dict)  # original folder path -> new name

    def is_empty(self) -> bool:
        return not (self.kept or self.keep_name or self.custom_names or self.moved_to or self.renamed_folders)


@dataclass(frozen=True)
class Choice:
    move: dict
    folder: str            # where it goes, even when left in place
    file_name: str
    is_kept: bool
    suggested_name: str | None
    is_custom_name: bool

    @property
    def id(self) -> str:
        return self.move["src"]

    @property
    def is_renamed(self) -> bool:
        return self.file_name != self.move["name"]

    @property
    def destination(self) -> str:
        return f"{self.folder}/{self.file_name}"


@dataclass(frozen=True)
class Group:
    path: str
    files: tuple[Choice, ...]
    is_existing: bool

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def parent(self) -> str | None:
        return self.path.rsplit("/", 1)[0] if "/" in self.path else None

    @property
    def selected_count(self) -> int:
        return sum(not f.is_kept for f in self.files)

    @property
    def is_special(self) -> bool:
        return self.path.split("/")[0] in (REVIEW, DUPLICATES)


def clean_name(text: str) -> str:
    text = text.strip().replace("/", "-").replace("\\", "-").replace(":", "-")
    for ch in '*?"<>|':
        text = text.replace(ch, "")
    return text.lstrip(".").strip()


class Plan:
    def __init__(self, result: dict):
        self.result = result
        self.scheme_key: str = result["recommended"]
        self.use_suggested = True
        self._edits: dict[str, Edits] = {}

    # ---- basics -----------------------------------------------------------------------

    @property
    def is_update(self) -> bool:
        return self.result.get("mode") == "update"

    @property
    def schemes(self) -> list[dict]:
        return self.result["schemes"]

    @property
    def scheme(self) -> dict:
        return next(s for s in self.schemes if s["key"] == self.scheme_key)

    @property
    def edits(self) -> Edits:
        return self._edits.setdefault(self.scheme_key, Edits())

    # ---- what will happen --------------------------------------------------------------

    def choices(self) -> list[Choice]:
        e = self.edits
        plain = {m["src"]: m["newName"] for m in self.scheme["movesWithoutRenames"]}
        renames = sorted(e.renamed_folders.items(), key=lambda kv: -len(kv[0]))  # deepest first
        out = []
        for move in self.scheme["moves"]:
            src = move["src"]
            folder = e.moved_to.get(src, move["folder"])
            for old, new in renames:
                if folder == old or folder.startswith(old + "/"):
                    parent = old.rsplit("/", 1)[0] if "/" in old else ""
                    folder = (f"{parent}/{new}" if parent else new) + folder[len(old):]
            suggested = move["newName"] if move["renamed"] else None
            use = self.use_suggested and suggested is not None and src not in e.keep_name
            custom = e.custom_names.get(src)
            name = custom or (move["newName"] if use else plain.get(src, move["name"]))
            out.append(Choice(move, folder, name, src in e.kept, suggested, custom is not None))
        return out

    def moving(self) -> list[Choice]:
        return [c for c in self.choices() if not c.is_kept]

    def rename_count(self) -> int:
        return sum(c.is_renamed for c in self.moving())

    def folder_count(self) -> int:
        return len({c.folder for c in self.moving()})

    def suggestion_count(self) -> int:
        return sum(c.suggested_name is not None for c in self.choices())

    def _existing_paths(self) -> set[str]:
        paths = {f["path"] for f in self.result.get("existingFolders") or []}
        return paths | {m["folder"] for m in self.scheme["moves"] if m.get("existing")}

    def groups(self) -> list[Group]:
        existing = self._existing_paths()
        by_folder: dict[str, list[Choice]] = {}
        for c in self.choices():
            by_folder.setdefault(c.folder, []).append(c)
        groups = [Group(path, tuple(sorted(files, key=lambda c: _sort_key(c.file_name))), path in existing)
                  for path, files in by_folder.items()]

        def rank(g: Group) -> int:
            top = g.path.split("/")[0]
            if top == IMAGES:
                return 3
            if top == REVIEW:
                return 4
            if top == DUPLICATES:
                return 5
            if {c.move["group"] for c in g.files} == {"other"}:
                return 2
            return 0 if g.is_existing else 1

        return sorted(groups, key=lambda g: (rank(g), _sort_key(g.path)))

    def all_folders(self) -> list[str]:
        paths = {c.folder for c in self.choices()} | self._existing_paths() | {REVIEW}
        return sorted(paths, key=_sort_key)

    # ---- changes -----------------------------------------------------------------------

    def set_kept(self, ids, kept: bool) -> None:
        if kept:
            self.edits.kept.update(ids)
        else:
            self.edits.kept.difference_update(ids)

    def toggle(self, choice: Choice) -> None:
        self.set_kept([choice.id], not choice.is_kept)

    def select_all(self) -> None:
        self.set_kept([c.id for c in self.choices()], False)

    def select_none(self) -> None:
        self.set_kept([c.id for c in self.choices()], True)

    def toggle_group(self, group: Group) -> None:
        self.set_kept([c.id for c in group.files], group.selected_count == len(group.files))

    def set_keeps_name(self, choice: Choice, keeps: bool) -> None:
        self.edits.custom_names.pop(choice.id, None)
        if keeps:
            self.edits.keep_name.add(choice.id)
        else:
            self.edits.keep_name.discard(choice.id)

    def set_custom_name(self, choice: Choice, new_name: str) -> None:
        """The person's own name. The extension is kept unless they typed one; empty goes back
        to the suggestion."""
        name = clean_name(new_name)
        e = self.edits
        if not name:
            e.custom_names.pop(choice.id, None)
            return
        ext = choice.move["name"].rsplit(".", 1)[1] if "." in choice.move["name"] else ""
        if ext and not name.lower().endswith("." + ext.lower()):
            name += "." + ext
        if name == choice.move["name"]:
            e.custom_names.pop(choice.id, None)
            e.keep_name.add(choice.id)
        else:
            e.custom_names[choice.id] = name

    def move_to(self, choice: Choice, folder: str) -> None:
        self.edits.kept.discard(choice.id)
        self.edits.moved_to[choice.id] = folder

    def can_rename_folder(self, group: Group) -> bool:
        return not group.is_existing and not group.is_special

    def rename_folder(self, path: str, new_name: str) -> None:
        name = clean_name(new_name)
        current = path.rsplit("/", 1)[-1]
        if not name or name == current:
            return
        e = self.edits
        original = path
        for old, new in e.renamed_folders.items():  # store against the original path
            parent = old.rsplit("/", 1)[0] if "/" in old else ""
            if (f"{parent}/{new}" if parent else new) == path:
                original = old
                break
        e.renamed_folders[original] = name

    def has_edits(self) -> bool:
        return not self.edits.is_empty() or not self.use_suggested

    def revert(self) -> None:
        self._edits[self.scheme_key] = Edits()
        self.use_suggested = True

    def payload(self) -> dict:
        """What `smartsort api apply` takes."""
        moving = self.moving()
        return {
            "moves": [{"src": c.move["src"], "dst": c.destination} for c in moving],
            "kept": [c.move["src"] for c in self.choices() if c.is_kept],
            "scheme": self.scheme_key,
        }
