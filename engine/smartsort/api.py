"""Machine-readable interface for the macOS app.

Every command prints one JSON object per line on stdout:
    {"event": "progress", "stage": "...", "done": 3, "total": 36}
    {"event": "result", ...}            # analyze
    {"event": "applied", ...}           # apply
    {"event": "undone", ...}            # undo
    {"event": "models", "models": [...]} # models
    {"event": "error", "message": "..."}
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def emit(event: str, **data) -> None:
    sys.stdout.write(json.dumps({"event": event, **data}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _plan_json(files, scheme: str, rename: bool, root: Path) -> list[dict]:
    from .plan import build_plan

    info = {f.item.path: f for f in files}
    out = []
    for m in build_plan(files, scheme, rename, root):
        f = info[m.src]
        out.append({
            "src": str(m.src),
            "name": m.src.name,
            "dst": m.dst.as_posix(),
            "folder": m.dst.parent.as_posix(),
            "newName": m.dst.name,
            "why": m.why,
            "renamed": m.renamed,
            "group": f.item.group,
            "kind": f.kind,
            "topic": f.detail if scheme == "detailed" else f.subject,
            "duplicateOf": f.duplicate_of.name if f.duplicate_of else None,
            "existing": (root / m.dst.parent).is_dir(),
        })
    return out


def analyze_cmd(folder: str, subjects: list[str] | None, rename: str, model: str | None,
                namer_path: str | None = None, use_namer: bool = True, max_read_mb: float | None = None,
                mode: str = "auto", include_kept: bool = False) -> int:
    """mode: "update" sorts the loose files into the folders SmartSort made last time (only
    files that fit none get new folders); "full" plans the loose files from scratch; "auto"
    is "update" whenever the folder has been organized before."""
    from .analyze import Existing, analyze
    from .embed import Embedder
    from .extract import list_files, read_file, sha256
    from .plan import SCHEMES, recommend
    from .update import document_samples, existing_folders, kept_files, load_state

    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        emit("error", message=f"“{root.name}” isn’t a folder.")
        return 2
    folders = existing_folders(root) if mode != "full" else {}
    updating = bool(folders)
    paths = list_files(root)
    kept = sorted(kept_files(root) & set(paths)) if not include_kept else []
    paths = [p for p in paths if p not in kept]
    if not paths:
        if updating or kept:
            left = ("" if not kept else " The file you chose to leave in place stays where it is." if len(kept) == 1
                    else f" The {len(kept)} files you chose to leave in place stay where they are.")
            emit("error", code="nothing-new", keptCount=len(kept),
                 message=f"Everything in “{root.name}” is already organized.{left} Add new files and analyze again.")
        else:
            emit("error", code="nothing-new", keptCount=0,
                 message="There are no loose files in this folder to organize.")
        return 3
    from .embed import ModelNotFound

    try:
        embedder = Embedder(model)
    except ModelNotFound as e:
        emit("error", code="no-embedding-model", message=str(e))
        return 4
    namer = None
    if use_namer:
        from .namer import Namer, find_model

        found = find_model(namer_path)
        if namer_path and not found:
            emit("error", message=f"The naming model “{Path(namer_path).name}” wasn’t found. "
                                  "Choose another one in Settings, or turn the naming model off.")
            return 4
        namer = Namer(found) if found else None
    existing = None
    samples = document_samples(folders) if updating else {}
    organized = [p for files in folders.values() for p in files]
    total = len(paths) + sum(map(len, samples.values())) + len(organized)
    done = 0
    items = []
    for p in paths:
        done += 1
        emit("progress", stage="Reading files", done=done, total=total)
        items.append(read_file(p, max_read_mb))
    if updating:
        docs = {}
        for rel, sample in samples.items():
            docs[rel] = []
            for p in sample:
                done += 1
                emit("progress", stage="Reading files", done=done, total=total)
                it = read_file(p, max_read_mb)
                if it.text.strip() and not it.error:
                    docs[rel].append(it)
        shas = {it.sha: it.path for its in docs.values() for it in its}
        for p in organized:
            done += 1
            emit("progress", stage="Reading files", done=done, total=total)
            if p not in shas.values():
                try:
                    shas.setdefault(sha256(p), p)
                except OSError:
                    pass
        existing = Existing(docs=docs, shas=shas, folders=set(folders))
    emit("progress", stage="Waking up the model", done=0, total=1)
    files = analyze(items, embedder, subjects=subjects, rename=rename, namer=namer, existing=existing,
                    progress=lambda stage, d, t: emit("progress", stage=stage, done=d, total=t))
    emit("progress", stage="Planning layouts", done=1, total=1)
    state = load_state(root)
    recommended = recommend(files)
    if updating and state.get("scheme") in SCHEMES:
        recommended = state["scheme"]

    groups = Counter(f.item.group for f in files)
    subjects_found = Counter(f.subject for f in files if f.subject and f.duplicate_of is None)
    emit(
        "result",
        folder=str(root),
        namer=namer.ref if namer else None,
        mode="update" if updating else "full",
        existingFolders=[{"path": rel, "count": len(files)} for rel, files in folders.items()],
        keptFiles=[p.name for p in kept],
        summary={
            "files": len(files),
            "documents": groups["document"],
            "images": groups["image"],
            "other": groups["other"],
            "duplicates": sum(f.duplicate_of is not None for f in files),
            "renames": sum(bool(f.new_name) and f.duplicate_of is None for f in files),
            "topics": [{"name": s, "count": n} for s, n in subjects_found.most_common()],
            "unreadable": [f.item.name for f in files if f.item.error],
            "tooLarge": [f.item.name for f in files if f.item.too_large],
        },
        recommended=recommended,
        schemes=[
            {
                "key": key,
                "title": title,
                "example": example,
                "moves": _plan_json(files, key, True, root),
                "movesWithoutRenames": _plan_json(files, key, False, root),
            }
            for key, (title, example) in SCHEMES.items()
        ],
    )
    return 0


def apply_cmd(folder: str, moves_file: str) -> int:
    """moves_file: a list of {"src", "dst"}, or {"moves": [...], "kept": [paths], "scheme": key}
    where `kept` are files the person chose to leave in place (remembered for next time)."""
    from .apply import apply_plan
    from .plan import Move
    from .update import save_state

    root = Path(folder).expanduser().resolve()
    raw = json.loads(Path(moves_file).read_text())
    kept, scheme = [], None
    if isinstance(raw, dict):
        kept = [Path(p) for p in raw.get("kept", [])]
        scheme = raw.get("scheme")
        raw = raw.get("moves", [])
    moves = []
    for m in raw:
        src, dst = Path(m["src"]), Path(m["dst"])
        # Only ever move loose files of this folder to somewhere inside it.
        if src.parent != root or dst.is_absolute() or ".." in dst.parts:
            emit("error", message=f"Refused an unsafe move for {src.name}.")
            return 2
        moves.append(Move(src=src, dst=dst, why=""))
    moved, problems, _ = apply_plan(root, moves)
    try:
        save_state(root, scheme, kept)
    except OSError as e:
        problems.append(f"Couldn’t remember the files left in place: {e}")
    emit("applied", moved=moved, problems=problems)
    return 0


def undo_cmd(folder: str) -> int:
    from .apply import undo_last

    try:
        restored, problems = undo_last(Path(folder).expanduser().resolve())
    except FileNotFoundError as e:
        emit("error", message=str(e))
        return 1
    emit("undone", restored=restored, problems=problems)
    return 0


def models_cmd() -> int:
    """Every model SmartSort can use on this computer, and what "Automatic" picks."""
    from .models import chat_models, default_chat_model, embedding_models, mlx_available

    chat = chat_models()
    embedding = embedding_models()
    emit("models", models=chat, embedding=embedding,
         defaultNaming=default_chat_model(chat),
         defaultEmbedding=embedding[0]["path"] if embedding else None,
         mlx=mlx_available())
    return 0


def run(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="smartsort api")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("folder")
    a.add_argument("--topics", "--subjects", dest="subjects")
    a.add_argument("--rename", default="junk", choices=["junk", "all", "none"])
    a.add_argument("--model")
    a.add_argument("--namer", help="folder of the MLX language model that writes names")
    a.add_argument("--no-namer", action="store_true")
    a.add_argument("--max-read-mb", type=float, help="don't open files bigger than this (default 50)")
    a.add_argument("--mode", default="auto", choices=["auto", "update", "full"],
                   help="update: sort new files into the folders made last time; full: plan from scratch")
    a.add_argument("--include-kept", action="store_true", help="also plan files left in place last time")
    b = sub.add_parser("apply")
    b.add_argument("folder")
    b.add_argument("moves_file")
    u = sub.add_parser("undo")
    u.add_argument("folder")
    sub.add_parser("models", help="list the language models on this Mac that can write names")
    args = p.parse_args(argv)
    try:
        if args.cmd == "analyze":
            subjects = [s.strip() for s in args.subjects.split(",") if s.strip()] if args.subjects else None
            return analyze_cmd(args.folder, subjects, args.rename, args.model, args.namer, not args.no_namer,
                               args.max_read_mb, args.mode, args.include_kept)
        if args.cmd == "models":
            return models_cmd()
        if args.cmd == "apply":
            return apply_cmd(args.folder, args.moves_file)
        return undo_cmd(args.folder)
    except Exception as e:  # report instead of a traceback the app can't show
        emit("error", message=f"{type(e).__name__}: {e}")
        return 1
