"""Work out what each file is: duplicates, document type, subject, image type, a better name.

Thresholds below were tuned on demo/make_sample.py output. Raw cosine similarities from
EmbeddingGemma 2 are squeezed into a narrow band (~0.7–0.9), so for zero-shot labelling and
clustering we centre the vectors (subtract the mean) first; that spreads them out a lot.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .embed import Embedder
from .examples import KIND_EXAMPLES
from .names import AREAS, EXTRA
from .extract import CODE_EXT, Item

DOC_KINDS = {  # descriptions are only used for scanned pages; text uses examples.py
    "Notes & Articles": "notes, an article or a chapter explaining a topic",
    "Reports": "a business or project report with summary, findings and figures",
    "Manuals & Guides": "a user manual, guide or step-by-step instructions",
    "Letters & Forms": "a letter, application or form to fill in",
    "Contracts & Agreements": "a contract, lease or legal agreement between parties",
    "Invoices & Receipts": "an invoice, bill or payment receipt with amounts and tax",
    "Statements": "a bank, credit card or salary statement with transactions",
    "Tickets & Bookings": "a ticket or booking confirmation for travel or an event",
    "Resumes": "a resume or CV with education, skills and experience",
    "Certificates": "a certificate awarded to a person",
    "Medical Records": "a medical report, prescription or lab test result",
    "Research Papers": "a research paper with abstract, methodology and references",
    "Code": "source code of a computer program",
    "Lists & To-dos": "a to-do list, checklist or quick notes",
}
# Calling an article an "invoice" is far worse than leaving it unlabelled, so these types
# need a clearer win before a document gets them.
STRICT_KINDS = {"Invoices & Receipts", "Statements", "Tickets & Bookings", "Resumes",
                "Certificates", "Contracts & Agreements", "Lists & To-dos"}

IMAGE_KINDS = {
    "Screenshots": "a screenshot of a computer screen, app, code editor or website",
    "Photos": "a photograph of a landscape, people, places or objects",
    "Scans": "a scanned page of a paper document with printed text",
    "Charts & Diagrams": "a chart, graph or diagram",
    "Graphics & Logos": "a logo, icon or graphic design",
}

# Abbreviations people type when naming their own topics (`--topics`). The model knows
# "Machine Learning" far better than "ML", so labels are embedded by their full name while
# folders keep the short name the person chose.
ALIASES = {
    "hr": "Human Resources", "ml": "Machine Learning", "ai": "Artificial Intelligence",
    "it": "Information Technology", "ui": "User Interface Design", "ux": "User Experience Design",
    "dsa": "Data Structures and Algorithms", "os": "Operating Systems", "dbms": "Databases",
    "cs": "Computer Science", "maths": "Mathematics", "math": "Mathematics", "stats": "Statistics",
    "econ": "Economics", "bio": "Biology", "chem": "Chemistry", "phys": "Physics",
    "dev": "Software Development", "ops": "Operations", "fin": "Finance", "mktg": "Marketing",
}


def expand(topic: str) -> str:
    key = topic.lower().strip(" .")
    if key in ALIASES:
        return ALIASES[key]
    if topic.isupper() and 2 <= len(topic) <= 5:  # an unknown acronym: match by initials
        for full in AREAS + list(ALIASES.values()):
            initials = "".join(w[0] for w in full.split() if w.lower() not in {"and", "of"})
            if initials.upper() == topic:
                return full
    return topic


NUMBER_KIND = {"Ch": "Notes & Articles", "Unit": "Notes & Articles", "Lecture": "Notes & Articles",
               "Exp": "Manuals & Guides"}

KIND_MIN_TOP, KIND_MIN_MARGIN = 0.15, 0.04  # vs built-in examples; correct types score 0.22+ with 0.05+ margin
# Grouping (centred cosine; measured on the demo folders): files closer than GROUP_SPLIT form
# a group; in the Grouped layout a lone file joins its closest group when at least JOIN_GROUP
# similar (an electricity bill joining payslips and statements scores ~0.24, a recipe vs. the
# same group ~0.0). Small folders can't be centred, so they use a raw-distance split instead.
GROUP_SPLIT = 0.75
JOIN_GROUP = 0.22
RAW_SPLIT = 0.12
# A group is "mixed" when fewer than this share of its files would pick the same specific name.
MIXED_GROUP = 0.75
MIN_TEXT = 40  # characters of real content needed before we label a document
MIN_CENTER = 6  # with fewer documents than this the mean is meaningless; use raw scores
# A new document is compared with each existing folder's average document (centred cosine).
# At MATCH_SURE or above it joins the closest folder. Between MATCH_ASK and MATCH_SURE topics can
# overlap (a gardening guide scores ~0.30 against "Photography Basics", a credit card statement
# ~0.35 against "Financial Documents"), so the language model is asked whether it fits the closest
# folder; without one, only MATCH_ALONE or above joins. Small samples use raw cosine (RAW_*).
# Every doubt resolves to a new folder: a misfiled document is worse than one more folder.
MATCH_SURE, MATCH_ASK, MATCH_ALONE = 0.5, 0.2, 0.4
RAW_SURE, RAW_ASK, RAW_ALONE = 0.92, 0.85, 0.9


@dataclass
class Existing:
    """A folder SmartSort organized before: what's already in its folders."""
    docs: dict[str, list[Item]]  # folder (relative path) -> sample documents from it
    shas: dict[str, Path]        # content hash -> an organized file, to spot copies
    folders: set[str]            # every existing folder, relative paths


@dataclass
class FileInfo:
    item: Item
    duplicate_of: Path | None = None
    kind: str | None = None  # document or image type
    subject: str | None = None  # group name in the Grouped layout
    detail: str | None = None  # group name in the Detailed layout
    llm_name: str | None = None  # file name written by the language model (no extension)
    target: str | None = None  # an existing folder this file belongs in (update mode)
    new_name: str | None = None
    note: str = ""


def _norm(x: np.ndarray) -> np.ndarray:
    return x / np.clip(np.linalg.norm(x, axis=-1, keepdims=True), 1e-9, None)


def _centered(x: np.ndarray) -> np.ndarray:
    """Subtract the folder's 'average document'. Near-copies (v1, v2, final, final2…) are
    counted once, otherwise twenty versions of one file would drag the average toward it."""
    if len(x) < MIN_CENTER:
        return x
    mean = x.mean(0)
    if len(x) <= 4000:  # pairwise clustering is O(n^2) memory
        from sklearn.cluster import AgglomerativeClustering

        groups = AgglomerativeClustering(
            n_clusters=None, metric="cosine", linkage="average", distance_threshold=0.05
        ).fit_predict(x)
        mean = np.mean([x[groups == g].mean(0) for g in np.unique(groups)], axis=0)
    return _norm(x - mean)


def _zero_shot(X: np.ndarray, L: np.ndarray, min_top: float, min_margin: float):
    """Best label per row (-1 when the winner isn't clearly ahead), plus all the scores."""
    S = X @ L.T
    order = np.argsort(-S, axis=1)
    top = S[np.arange(len(S)), order[:, 0]]
    second = S[np.arange(len(S)), order[:, 1]]
    ok = (top >= min_top) & (top - second >= min_margin)
    return np.where(ok, order[:, 0], -1), S


_PROTOTYPES: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def kind_scores(embedder: Embedder, vecs: np.ndarray) -> np.ndarray:
    """Similarity of each document to each type's examples, measured from a fixed reference
    point (the average of all examples) instead of the folder's own average."""
    key = id(embedder)
    if key not in _PROTOTYPES:
        texts, owner = [], []
        for k, examples in KIND_EXAMPLES.items():
            texts += [f"title: none | text: {e}" for e in examples]
            owner += [k] * len(examples)
        V = embedder.labels(texts, "classify")
        ref = V.mean(0)
        Vc = _norm(V - ref)
        owner = np.array(owner)
        P = _norm(np.stack([Vc[owner == k].mean(0) for k in DOC_KINDS]))
        _PROTOTYPES[key] = (ref, P)
    ref, P = _PROTOTYPES[key]
    return _norm(vecs - ref) @ P.T


def match_existing(embedder: Embedder, items: list[Item], vecs: np.ndarray, existing: Existing,
                   namer=None, progress=None) -> list[str | None]:
    """The existing folder each new document belongs in, or None when none fits.

    New documents and samples from each folder are centred together (as in a normal
    analysis), and each document is compared with every folder's average document."""
    names = [r for r, its in existing.docs.items() if its]
    if not names or not len(vecs):
        return [None] * len(vecs)
    samples = [it for r in names for it in existing.docs[r]]
    owner = np.array([i for i, r in enumerate(names) for _ in existing.docs[r]])
    E = embedder.items(samples, "cluster")
    Z = np.vstack([vecs, E])
    centered = len(Z) >= MIN_CENTER
    Zc = _centered(Z)
    X, Ec = Zc[: len(vecs)], Zc[len(vecs):]
    C = _norm(np.stack([Ec[owner == i].mean(0) for i in range(len(names))]))
    S = X @ C.T
    sure, ask, alone = (MATCH_SURE, MATCH_ASK, MATCH_ALONE) if centered else (RAW_SURE, RAW_ASK, RAW_ALONE)
    out: list[str | None] = []
    for i, row in enumerate(S):
        if progress:
            progress(i, len(S))
        best = int(row.argmax())
        name = names[best]
        if row[best] >= sure:
            out.append(name)
        elif row[best] < ask:
            out.append(None)
        elif namer is None:
            out.append(name if row[best] >= alone else None)
        else:
            titles = [it.title or it.path.stem for it in existing.docs[name]]
            out.append(name if namer.fits_folder(items[i], name, titles) else None)
    if progress:
        progress(len(S), len(S))
    return out


def _cluster(X: np.ndarray, centered: bool) -> np.ndarray:
    if len(X) < 2:
        return np.zeros(len(X), dtype=int)
    from sklearn.cluster import AgglomerativeClustering

    return AgglomerativeClustering(
        n_clusters=None, metric="cosine", linkage="average",
        distance_threshold=GROUP_SPLIT if centered else RAW_SPLIT,
    ).fit_predict(X)


def _join_lone_files(X: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """A file with no group joins the group it is most like, if it's close enough."""
    counts = Counter(labels.tolist())
    multi = [g for g, n in counts.items() if n > 1]
    if not multi:
        return labels
    C = _norm(np.stack([X[labels == g].mean(0) for g in multi]))
    out = labels.copy()
    for i in np.where([counts[l] == 1 for l in labels.tolist()])[0]:
        sims = X[i] @ C.T
        if sims.max() >= JOIN_GROUP:
            out[i] = multi[int(sims.argmax())]
    return out


def name_groups(X: np.ndarray, labels: np.ndarray, L: np.ndarray, names: list[str],
                broad: set[str] | None = None) -> dict[int, str]:
    """The model names each group from the candidates.

    Fit is measured on centred vectors (documents relative to this folder, names relative
    to each other), weighted toward the worst-fitting file and away from names that fit
    other groups too. When the files in a group would each get a *different* specific name
    on their own (a hotel booking, a flight ticket, a cab ride), the group is mixed and gets
    a broad name instead ("Travel"); when they agree, the specific name is kept
    ("Food Delivery Receipts"). Bigger groups choose first; every group gets its own name.
    """
    Lc = _norm(L - L.mean(0)) if len(L) > 2 else L
    groups = sorted(np.unique(labels).tolist(), key=lambda g: -(labels == g).sum())
    cents = _norm(np.stack([_norm(X[labels == g].mean(0)) for g in groups]))
    S = Lc @ cents.T
    is_broad = np.array([n in broad for n in names]) if broad else None
    used, out = set(), {}
    for gi, g in enumerate(groups):
        fit = Lc @ X[labels == g].T  # candidates x files
        others = np.delete(S, gi, axis=1).max(1) if len(groups) > 1 else 0
        score = 0.7 * fit.min(1) + 0.3 * fit.mean(1) - 0.5 * others
        if is_broad is not None and fit.shape[1] > 1:
            own_best = Counter(fit.argmax(0).tolist()).most_common(1)[0][1] / fit.shape[1]
            if own_best < MIXED_GROUP:
                score = np.where(is_broad, score, -np.inf)
        for j in np.argsort(-score):
            if np.isfinite(score[j]) and names[j].lower() not in used:
                used.add(names[j].lower())
                out[g] = names[j]
                break
        else:
            out[g] = "Documents"
    return out


def _name_with_language_model(namer, docs: list[FileInfo], fine: np.ndarray, joined: np.ndarray,
                              rename: str, progress=None) -> None:
    """The language model writes the folder name for every group (both layouts) and, file by
    file, a new name for each file that needs one. Embedding-chosen names stay as the fallback
    when it can't answer, its answer fails the fact check, or two groups would share a name."""
    jobs: dict[tuple[int, ...], list[str]] = {}
    for layout, labels in (("subject", joined), ("detail", fine)):
        for g in np.unique(labels):
            jobs.setdefault(tuple(np.where(labels == g)[0].tolist()), []).append(layout)
    to_rename = [f for f in docs if rename == "all" or f.item.has_junk_name]
    total, done = len(jobs) + len(to_rename), 0
    used = {"subject": set(), "detail": set()}
    for members, layouts in sorted(jobs.items(), key=lambda kv: -len(kv[0])):  # big groups first
        if progress:
            progress(done, total)
        done += 1
        items = [docs[i].item for i in members]
        folder = namer.folder_name(items)
        taken = set().union(*(used[layout] for layout in layouts))
        if folder and folder.lower() in taken:  # another group has it: ask again, listing the taken names
            folder = namer.folder_name(items, {n.title() for n in taken})
        if not folder:
            folder = _shared_title(items)
            if not folder or folder.lower() in taken:
                continue
        for layout in layouts:
            if folder.lower() not in used[layout]:
                used[layout].add(folder.lower())
                for i in members:
                    setattr(docs[i], layout, folder)
    for f in to_rename:
        if progress:
            progress(done, total)
        done += 1
        f.llm_name = namer.file_name(f.item)
    if progress:
        progress(total, total)


def _shared_title(items: list[Item]) -> str | None:
    """The title most files in a group share (copies or versions of one document), minus
    any "Chapter 3:" style numbering."""
    titles = Counter(re.sub(r"^.*?\b(chapter|unit|lecture|experiment|part)\s*(no\.?)?\s*\d+\s*[:.-]?\s*", "",
                            it.title, flags=re.I).strip(" :-") for it in items if it.title)
    if not titles:
        return None
    title, n = titles.most_common(1)[0]
    if n / len(items) < 0.6 or not 3 <= len(title) <= 40:
        return None
    return re.sub(r'[\\/:*?"<>|]', " ", title).strip()


def _dhash(img: Image.Image) -> int:
    g = img.convert("L").resize((9, 8), Image.LANCZOS)
    px = list(g.getdata())
    return sum(1 << i for i in range(64) if px[(i // 8) * 9 + i % 8] > px[(i // 8) * 9 + i % 8 + 1])


def _keeper_rank(it: Item):
    return (it.has_junk_name, bool(re.search(r"\(\d+\)|copy", it.path.stem, re.I)), len(it.name), it.path.stat().st_mtime)


def _group(files: list[FileInfo], buckets) -> None:
    for group in buckets:
        group = list({id(f): f for f in group}.values())
        if len(group) < 2:
            continue
        keeper = min(group, key=lambda f: _keeper_rank(f.item))
        while keeper.duplicate_of is not None:  # already a copy of something else
            keeper = next(f for f in files if f.item.path == keeper.duplicate_of)
        for f in group:
            if f is not keeper and f.duplicate_of is None:
                f.duplicate_of = keeper.item.path


def find_duplicates(files: list[FileInfo]) -> None:
    """Exact copies (same bytes) and documents with the same text (e.g. re-saved PDFs)."""
    buckets: dict[str, list[FileInfo]] = {}
    for f in files:
        buckets.setdefault("sha:" + f.item.sha, []).append(f)
        text = re.sub(r"\s+", " ", f.item.text).strip().lower()
        if f.item.group == "document" and len(text) >= 200:
            buckets.setdefault("txt:" + text[:4000], []).append(f)
    _group(files, buckets.values())


def find_similar_images(files: list[FileInfo], images: list[FileInfo], vecs: np.ndarray) -> None:
    """The same picture resized or re-compressed. Needs BOTH a near-identical perceptual hash
    and near-identical meaning: two different screenshots of the same dark editor share a
    layout (similar hash) but not content (embedding ~0.82 vs ~0.92 for a real resize)."""
    hashes = [_dhash(f.item.image) for f in images]
    pairs = []
    for i in range(len(images)):
        for j in range(i):
            if bin(hashes[i] ^ hashes[j]).count("1") <= 5 and float(vecs[i] @ vecs[j]) >= 0.9:
                pairs.append([images[i], images[j]])
    _group(files, pairs)


def suggest_name(it: Item) -> str | None:
    """'Chapter 3: Laws of Motion' -> 'Ch 03 - Laws of Motion.pdf'. None if no good title."""
    title = it.title
    if not title:
        return None
    if it.number:
        label, n = it.number
        rest = re.sub(
            r"^.*?\b(chapter|ch\.|unit|module|lecture|lec\.|experiment|practical|assignment)\s*"
            r"(no\.?|number|#)?\s*[-:]?\s*\d{1,2}\s*[-:.)]?\s*",
            "", title, count=1, flags=re.I,
        )
        title = f"{label} {n:02d} - {rest}" if rest and rest != title else title
    title = title.replace(":", " -")
    title = re.sub(r'[\\/*?"<>|\x00-\x1f]', "", title)
    title = re.sub(r"\s+", " ", title).strip(" .-")[:80].rstrip(" .-")
    if not title or title.lower() == it.path.stem.lower():
        return None
    return title + it.path.suffix.lower()


def analyze(items: list[Item], embedder: Embedder, subjects: list[str] | None = None,
            rename: str = "junk", progress=None, namer=None, existing: Existing | None = None) -> list[FileInfo]:
    """With `existing` (a folder organized before), documents that fit one of its folders go
    there; only the rest are grouped into new folders."""
    files = [FileInfo(item=it) for it in items]
    find_duplicates(files)
    if existing:  # a copy of something already organized
        for f in files:
            if f.duplicate_of is None and f.item.sha in existing.shas:
                f.duplicate_of = existing.shas[f.item.sha]
    live = [f for f in files if f.duplicate_of is None]

    docs = [f for f in live if f.item.group == "document"]
    # Too little to go on (unreadable, encrypted, near-empty): don't guess from the filename.
    for f in docs:
        if f.item.image is None and len(f.item.text.strip()) < MIN_TEXT:
            if f.item.too_large:
                f.note = f"too large to read ({f.item.size / (1 << 20):.0f} MB)"
            else:
                f.note = "couldn't read it" if f.item.error else "too little content to tell"
    text_docs = [f for f in docs if f.item.image is None and len(f.item.text.strip()) >= MIN_TEXT]
    scans = [f for f in docs if f.item.image is not None]
    images = [f for f in live if f.item.group == "image" and f.item.image is not None]

    def step(name):
        return (lambda d, t: progress(name, d, t)) if progress else None

    topic_vecs = embedder.items([f.item for f in text_docs], "cluster", step("Reading documents"))
    kind_vecs = embedder.items([f.item for f in text_docs], "classify", step("Classifying documents"))
    pic_vecs = embedder.items([f.item for f in images + scans], "image", step("Looking at images"))
    img_vecs, scan_vecs = pic_vecs[: len(images)], pic_vecs[len(images):]
    find_similar_images(files, images, img_vecs)
    keep = [i for i, f in enumerate(images) if f.duplicate_of is None]
    images, img_vecs = [images[i] for i in keep], img_vecs[keep]

    kind_names = list(DOC_KINDS)
    # ---- document type -------------------------------------------------------------
    if text_docs:
        scores = kind_scores(embedder, kind_vecs)
        order = np.argsort(-scores, axis=1)
        for f, row, o in zip(text_docs, scores, order, strict=False):
            top, margin = row[o[0]], row[o[0]] - row[o[1]]
            name = kind_names[o[0]]
            need = (KIND_MIN_TOP + 0.05, KIND_MIN_MARGIN * 2) if name in STRICT_KINDS else (KIND_MIN_TOP, KIND_MIN_MARGIN)
            f.kind = name if top >= need[0] and margin >= need[1] else None
    for f in docs:
        if f.item.path.suffix.lower() in CODE_EXT:
            f.kind = "Code"
        elif f.kind is None and f.item.number:  # "Unit 3: ..." is notes, "Experiment 2" a lab
            f.kind = NUMBER_KIND.get(f.item.number[0])
    if scans:  # image of a page vs text labels: raw scores work, cross-modal centring doesn't
        L = embedder.labels(list(DOC_KINDS.values()), "classify")
        for f, b in zip(scans, _zero_shot(scan_vecs, L, 0.0, 0.02)[0], strict=False):
            f.kind = kind_names[b] if b >= 0 else None
            f.note = "scanned"

    # ---- existing folders -------------------------------------------------------------
    matched: list[FileInfo] = []
    if text_docs and existing and existing.docs:
        targets = match_existing(embedder, [f.item for f in text_docs], topic_vecs, existing, namer,
                                 step("Matching your folders"))
        for f, t in zip(text_docs, targets, strict=False):
            if t:
                f.target = t
                f.subject = f.detail = t.split("/")[0]
                matched.append(f)
        rest = [i for i, t in enumerate(targets) if t is None]
        text_docs, topic_vecs = [text_docs[i] for i in rest], topic_vecs[rest]

    # ---- groups ----------------------------------------------------------------------
    # Folders come from the files: similar documents are grouped by their embeddings, and
    # the model names each group (see name_groups). Nothing is decided by a fixed list.
    if text_docs:
        X = _centered(topic_vecs)
        centered = len(text_docs) >= MIN_CENTER
        fine = _cluster(X, centered)
        joined = _join_lone_files(X, fine) if centered else fine
        if subjects:  # the person named their own folders
            candidates, texts = subjects, [expand(n) for n in subjects]
        else:
            candidates = list(dict.fromkeys(AREAS + EXTRA))
            texts = candidates
        L = embedder.labels(texts, "cluster")
        broad = None if subjects else set(AREAS)
        detail_names = name_groups(X, fine, L, candidates, broad)
        group_names = name_groups(X, joined, L, candidates, broad)
        for f, d, g in zip(text_docs, fine, joined, strict=False):
            f.detail, f.subject = detail_names[d], group_names[g]
        if namer is not None and not subjects:
            _name_with_language_model(namer, text_docs, fine, joined, rename, step("Naming folders and files"))
    if namer is not None and rename != "none":  # documents going into existing folders keep that name
        to_rename = [f for f in matched if rename == "all" or f.item.has_junk_name]
        report = step("Naming folders and files")
        for i, f in enumerate(to_rename):
            if report:
                report(i, len(to_rename))
            f.llm_name = namer.file_name(f.item)
        if report and to_rename:
            report(len(to_rename), len(to_rename))

    # ---- images --------------------------------------------------------------------
    if images:
        L = embedder.labels(list(IMAGE_KINDS.values()), "classify")
        names = list(IMAGE_KINDS)
        for f, b in zip(images, _zero_shot(img_vecs, L, 0.0, 0.01)[0], strict=False):
            f.kind = names[b] if b >= 0 else None
            if existing and f.kind and f"Images/{f.kind}" in existing.folders:
                f.target = f"Images/{f.kind}"

    # ---- names ---------------------------------------------------------------------
    if rename != "none":
        for f in docs:
            if rename == "all" or f.item.has_junk_name:
                if f.llm_name:
                    f.new_name = f.llm_name + f.item.path.suffix.lower()
                else:
                    f.new_name = suggest_name(f.item)
    return files
