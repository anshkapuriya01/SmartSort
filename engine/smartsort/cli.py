"""smartsort command line.

    smartsort ~/Desktop                 # look, suggest layouts, preview, then ask before moving
    smartsort ~/Desktop --dry-run       # only show the plan
    smartsort undo ~/Desktop            # put everything back
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from . import __version__

COLOR = sys.stdout.isatty()


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if COLOR else s


def status(msg: str) -> None:
    if COLOR:
        print(f"\r\033[K{msg}", end="", flush=True)


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)


def summarize(files) -> str:
    groups = Counter(f.item.group for f in files)
    dups = sum(f.duplicate_of is not None for f in files)
    renames = sum(bool(f.new_name) and f.duplicate_of is None for f in files)
    parts = [f"{groups['document']} documents", f"{groups['image']} images", f"{groups['other']} other files"]
    extra = []
    if dups:
        extra.append(c("33", f"{dups} duplicate{'s' * (dups > 1)}"))
    if renames:
        extra.append(c("32", f"{renames} file{'s' * (renames > 1)} with unhelpful names"))
    subjects = Counter(f.subject for f in files if f.subject and f.duplicate_of is None)
    out = f"Found {len(files)} files: " + ", ".join(parts) + "."
    if extra:
        out += "\nAlso spotted " + " and ".join(extra) + "."
    if subjects:
        out += "\nGroups: " + ", ".join(f"{s} ({n})" for s, n in subjects.most_common()) + "."
    return out


def top_level(moves) -> str:
    counts = Counter(m.dst.parts[0] for m in moves)
    return ", ".join(f"{k} ({v})" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:6]) + (
        ", …" if len(counts) > 6 else ""
    )


def cmd_organize(args) -> int:
    from .analyze import analyze
    from .apply import apply_plan
    from .embed import Embedder
    from .extract import list_files, read_file
    from .plan import SCHEMES, build_plan, recommend, render_tree

    root = Path(args.folder).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a folder: {root}")
        return 2
    paths = list_files(root)
    if not paths:
        print("No files to organise here (subfolders and hidden files are left alone).")
        return 0
    interactive = sys.stdin.isatty() and not args.yes

    subjects = [s.strip() for s in args.topics.split(",") if s.strip()] if args.topics else None

    t0 = time.time()
    items = []
    for i, p in enumerate(paths, 1):
        status(f"Reading files {i}/{len(paths)}")
        items.append(read_file(p, args.max_read_mb))
    status("Loading the model…")
    namer = None
    if not args.no_namer:
        from .namer import Namer, find_model

        found = find_model(args.namer)
        namer = Namer(found) if found else None
    from .embed import ModelNotFound

    try:
        embedder = Embedder(args.model)
    except ModelNotFound as e:
        print(c("31", str(e)))
        return 4
    files = analyze(
        items, embedder, subjects=subjects, rename=args.rename, namer=namer,
        progress=lambda name, d, t: status(f"{name} {d}/{t}"),
    )
    status("")
    print(summarize(files) + c("2", f"  ({time.time() - t0:.1f}s)"))
    unreadable = [f.item.name for f in files if f.item.error]
    if unreadable:
        print(c("33", f"Couldn't read {len(unreadable)} file(s), sorted by name only: ") + ", ".join(unreadable[:5]))

    scheme = args.scheme or recommend(files)
    rename = args.rename != "none"
    if interactive and not args.scheme:
        best = scheme
        print("\nHow would you like them organised?")
        keys = list(SCHEMES)
        for i, key in enumerate(keys, 1):
            label = SCHEMES[key][0] + (c("32", "  (recommended)") if key == best else "")
            print(f"  {c('1', str(i))}. {label}\n     {c('2', top_level(build_plan(files, key, rename)))}")
        choice = ask(f"Choose 1-{len(keys)} [Enter = {keys.index(best) + 1}]: ")
        if choice.isdigit() and 1 <= int(choice) <= len(keys):
            scheme = keys[int(choice) - 1]

    while True:
        moves = build_plan(files, scheme, rename)
        changing = [m for m in moves if m.dst != Path(m.src.name)]
        print(f"\n{c('1', 'Plan: ' + SCHEMES[scheme][0])}  {c('2', f'{len(changing)} moves, {sum(m.renamed for m in moves)} renames')}")
        print(render_tree(moves, color=COLOR))
        if args.dry_run:
            print(c("2", "\nDry run: nothing was changed."))
            return 0
        if not interactive:
            break
        print(c("2", "\nNothing has been moved yet. Duplicates are moved to a folder, never deleted."))
        choice = ask(
            f"[{c('1', 'a')}]pply  [{c('1', 'l')}]ayout  [{c('1', 'r')}]enaming {'off' if rename else 'on'}  "
            f"[{c('1', 'q')}]uit: "
        ).lower()
        if choice.startswith("a"):
            break
        if choice.startswith("q") or not choice:
            print("Left everything as it was.")
            return 0
        if choice.startswith("r"):
            rename = not rename
        elif choice.startswith("l"):
            keys = list(SCHEMES)
            for i, key in enumerate(keys, 1):
                print(f"  {i}. {SCHEMES[key][0]}")
            pick = ask("Choose: ")
            if pick.isdigit() and 1 <= int(pick) <= len(keys):
                scheme = keys[int(pick) - 1]

    moved, problems, journal = apply_plan(root, moves)
    print(c("32", f"\nDone: organised {moved} files.") + f" Undo any time with: smartsort undo \"{root}\"")
    for p in problems:
        print(c("33", "  " + p))
    return 0


def cmd_undo(args) -> int:
    from .apply import undo_last

    root = Path(args.folder).expanduser().resolve()
    try:
        restored, problems = undo_last(root)
    except FileNotFoundError as e:
        print(e)
        return 1
    print(c("32", f"Put {restored} files back where they were."))
    for p in problems:
        print(c("33", "  " + p))
    return 0


def cmd_models(args) -> int:
    """What SmartSort found on this computer, and what it will use."""
    from .models import chat_models, default_chat_model, embedding_models, mlx_available

    embedding = embedding_models()
    print(c("1", "Understanding files (EmbeddingGemma 2)"))
    if embedding:
        for i, m in enumerate(embedding):
            mark = c("32", "✓ in use ") if i == 0 else "         "
            print(f"  {mark}{m['name']}  {c('2', m['path'])}")
    else:
        print(c("31", "  Not found.") + " Download it once with: hf download google/embeddinggemma-2")
    chat = chat_models()
    default = default_chat_model(chat)
    print(c("1", "\nNaming (chat models)") + c("2", f"  MLX: {'yes' if mlx_available() else 'no'}"))
    if not chat:
        print("  None found. Folders are then named by EmbeddingGemma alone.")
    for m in chat:
        mark = c("32", "✓ in use ") if m["path"] == default else "         "
        size = f"{m['sizeBytes'] / 1e9:.1f} GB" if m["sizeBytes"] else ""
        detail = " · ".join(x for x in [m["parameters"], size, m["source"], m["backend"]] if x)
        line = f"  {mark}{m['name']}  {c('2', detail)}"
        if not m["supported"]:
            line = c("2", f"  ✗        {m['name']}  ({m['note'] or 'not supported'})")
        print(line)
    if chat:
        print(c("2", "\nUse another one with --namer <path | ollama:name | lmstudio:name>."))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "api":  # JSON-lines interface used by the macOS app
        from .api import run

        return run(argv[1:])
    if argv and argv[0] not in {"organize", "organise", "undo", "models", "-h", "--help", "--version"}:
        argv.insert(0, "organize")  # `smartsort ~/Desktop` is the common case

    parser = argparse.ArgumentParser(prog="smartsort", description="Organise a messy folder by what's inside the files.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    org = sub.add_parser("organize", aliases=["organise"], help="suggest a layout and organise a folder")
    org.add_argument("folder")
    org.add_argument("--scheme", choices=["grouped", "detailed", "type"],
                     help="grouped (default), detailed, or by type; skips the layout question")
    org.add_argument("--topics", "--subjects", dest="topics",
                     help='name the folders yourself, e.g. "Clients, Taxes, Trips"; files go to the closest one')
    org.add_argument("--rename", choices=["junk", "all", "none"], default="junk",
                     help="rename files with unhelpful names (default), all documents, or none")
    org.add_argument("--dry-run", action="store_true", help="show the plan without changing anything")
    org.add_argument("-y", "--yes", action="store_true", help="don't ask, use the recommended layout and apply")
    org.add_argument("--model", help="folder of EmbeddingGemma 2 (default: found automatically)")
    org.add_argument("--namer", help="chat model that writes folder and file names: a model folder, "
                                     "ollama:<name> or lmstudio:<name> (default: found automatically; "
                                     "see `smartsort models`)")
    org.add_argument("--no-namer", action="store_true", help="name folders with the embedding model only")
    org.add_argument("--max-read-mb", type=float, help="don't open files bigger than this many MB (default 50)")
    org.set_defaults(func=cmd_organize)

    und = sub.add_parser("undo", help="reverse the last organise in a folder")
    und.add_argument("folder")
    und.set_defaults(func=cmd_undo)

    mod = sub.add_parser("models", help="show the models SmartSort found on this computer")
    mod.set_defaults(func=cmd_models)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
