"""Read each file and pull out what the model needs: text, a title, or an image."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

try:  # iPhone photos are HEIC; support them when the plugin is installed.
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

DOC_EXT = {".pdf", ".docx", ".pptx", ".txt", ".md", ".doc", ".ppt", ".rtf", ".odt", ".pages", ".key"}
CODE_EXT = {
    ".py", ".ipynb", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".sql", ".sh", ".html", ".css", ".m", ".r",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"}
OTHER_CATEGORIES = {
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"},
    "Installers": {".dmg", ".pkg", ".exe", ".msi", ".deb", ".apk", ".iso"},
    "Audio": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff"},
    "Videos": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"},
    "Spreadsheets": {".xlsx", ".xls", ".csv", ".numbers", ".ods", ".tsv"},
    "Fonts": {".ttf", ".otf", ".woff", ".woff2"},
    "Design Files": {".psd", ".ai", ".fig", ".sketch", ".xd", ".svg", ".eps"},
}

MAX_CHARS = 3000  # ~800 tokens: plenty to tell what a document is about, and fast.

# Filenames that say nothing about the content, so a rename is worth suggesting.
JUNK_NAME = re.compile(
    r"""^(
        (document|doc|file|download|downloads|untitled|new\ document|new\ file|scan|scanned|img|image|
         photo|pic|screenshot|ppt|presentation|notes?|lab|copy\ of|final|output|print|page|cam\s?scanner)
        [\s_\-.]*(\(?\d*\)?)?[\s_\-.]*(final|copy|new)?[\s_\-.]*(\(?\d*\)?)?
      | [0-9a-f]{6,}            # hashes
      | [\d\s_\-.()]+           # only digits
      | [a-z]{1,4}[\s_\-]?\d+(\s*\(\d+\))?   # ch3, u2, phy1, abc12
    )$""",
    re.IGNORECASE | re.VERBOSE,
)

NUMBERING = [
    ("Ch", re.compile(r"\b(?:chapter|ch\.)\s*[-:]?\s*(\d{1,2})\b", re.I)),
    ("Unit", re.compile(r"\b(?:unit|module)\s*[-:]?\s*(\d{1,2})\b", re.I)),
    ("Lecture", re.compile(r"\b(?:lecture|lec\.)\s*[-:]?\s*(\d{1,2})\b", re.I)),
    ("Exp", re.compile(r"\b(?:experiment|practical)\s*(?:no\.?|number|#)?\s*[-:]?\s*(\d{1,2})\b", re.I)),
    ("Assignment", re.compile(r"\bassignment\s*(?:no\.?|#)?\s*[-:]?\s*(\d{1,2})\b", re.I)),
]


@dataclass
class Item:
    path: Path
    size: int
    sha: str
    group: str  # "document" | "image" | "other"
    category: str = ""  # for "other": Archives, Videos, ...
    text: str = ""
    title: str = ""
    number: tuple[str, int] | None = None  # e.g. ("Ch", 3)
    image: Image.Image | None = field(default=None, repr=False)
    scanned: bool = False  # PDF with no text layer; embedded as an image of page 1
    error: str = ""
    too_large: bool = False  # skipped on purpose: bigger than the reading limit

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def has_junk_name(self) -> bool:
        stem = self.path.stem.strip()
        # "statement (1)", "report copy", "notes_v2_FINAL": copies and versions say nothing
        return bool(JUNK_NAME.match(stem) or re.search(r"\(\d+\)$|\bcopy( \d+)?$|[_\s-]v?\d*[_\s-]?final$", stem, re.I))


# Files bigger than this are never opened or read in full (overridden by --max-read-mb).
MAX_READ_MB = float(os.environ.get("SMARTSORT_MAX_READ_MB", "50"))
MAX_IMAGE_PIXELS = 40_000_000  # bigger images aren't decoded (a 113-megapixel poster, for example)
QUICK_HASH_OVER = 64 << 20  # files above 64 MB get a fingerprint instead of a full hash


def sha256(path: Path) -> str:
    """Content hash for spotting duplicates. Big files (videos, disk images) are fingerprinted
    from their size plus three 1 MB samples, so a 5 GB file costs 3 MB of reading, not 5 GB."""
    h = hashlib.sha256()
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > QUICK_HASH_OVER:
            h.update(f"quick:{size}".encode())
            for offset in (0, size // 2, max(0, size - (1 << 20))):
                f.seek(offset)
                h.update(f.read(1 << 20))
        else:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


# System files that live in folders but are never the person's documents.
SYSTEM_FILES = {"desktop.ini", "thumbs.db", "ehthumbs.db", ".ds_store", "icon\r"}


def _hidden(p: Path) -> bool:
    if p.name.startswith((".", "~$")) or p.name.lower() in SYSTEM_FILES:
        return True
    attrs = getattr(p.stat(), "st_file_attributes", 0)  # Windows: hidden or system attribute
    return bool(attrs & 0x6)


def list_files(folder: Path) -> list[Path]:
    """Top-level, visible, regular files only. Existing subfolders are left alone."""
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.is_symlink() and not _hidden(p))


def classify_ext(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    if ext in DOC_EXT or ext in CODE_EXT:
        return "document", ""
    if ext in IMAGE_EXT:
        return "image", ""
    for category, exts in OTHER_CATEGORIES.items():
        if ext in exts:
            return "other", category
    return "other", "Other Files"


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip(" -_:|.")
    if re.match(r"^(microsoft (word|powerpoint) - |untitled|slide \d)", title, re.I) or title.lower().endswith(
        (".doc", ".docx", ".pdf", ".ppt", ".pptx")
    ):
        return ""
    if len(title) < 4 or len(re.findall(r"[A-Za-z]", title)) < 3:
        return ""
    return title[:90]


def _pdf(item: Item) -> None:
    import pymupdf as fitz

    with fitz.open(item.path) as doc:
        if doc.page_count == 0:
            return
        meta_title = clean_title((doc.metadata or {}).get("title", ""))
        text = ""
        for page in doc.pages(0, min(3, doc.page_count)):
            text += page.get_text() + "\n"
            if len(text) > MAX_CHARS:
                break
        item.text = text[:MAX_CHARS]
        item.title = _largest_line(doc[0]) or meta_title
        if len(item.text.strip()) < 80:  # scanned: no text layer, look at the page instead
            page = doc[0]  # render at most ~1400 px on the long side, whatever the page size
            zoom = min(110 / 72, 1400 / max(page.rect.width, page.rect.height, 1))
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            item.image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            item.scanned = True


def _largest_line(page) -> str:
    """The biggest text on page 1 is almost always the title."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text:
                lines.append((max(s["size"] for s in line["spans"]), line["bbox"][1], text))
    if not lines:
        return ""
    biggest = max(size for size, _, _ in lines)
    body = sorted(size for size, _, _ in lines)[len(lines) // 2]
    if biggest < body * 1.15:  # no line stands out, so there's no clear title
        return ""
    top = [t for size, _, t in sorted(lines, key=lambda l: l[1]) if size >= biggest - 0.5]
    return clean_title(" ".join(top[:3]))


def _docx(item: Item) -> None:
    import docx

    d = docx.Document(str(item.path))
    paras = [p for p in d.paragraphs if p.text.strip()]
    item.text = "\n".join(p.text for p in paras)[:MAX_CHARS]
    heading = next((p.text for p in paras if p.style is not None and p.style.name.startswith(("Title", "Heading"))), "")
    item.title = clean_title(heading) or clean_title(d.core_properties.title or "")


def _pptx(item: Item) -> None:
    from pptx import Presentation

    prs = Presentation(str(item.path))
    chunks, first_title = [], ""
    for slide in prs.slides:
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            first_title = first_title or slide.shapes.title.text_frame.text
        for shape in slide.shapes:
            if shape.has_text_frame:
                chunks.append(shape.text_frame.text)
        if sum(map(len, chunks)) > MAX_CHARS:
            break
    item.text = "\n".join(chunks)[:MAX_CHARS]
    item.title = clean_title(first_title) or clean_title(prs.core_properties.title or "")


def _plain(item: Item) -> None:
    with item.path.open("rb") as f:
        item.text = f.read(MAX_CHARS * 2).decode("utf-8", errors="ignore")[:MAX_CHARS]
    if item.path.suffix.lower() == ".md":
        m = re.search(r"^#\s+(.+)$", item.text, re.M)
        item.title = clean_title(m.group(1)) if m else ""


def _image(item: Item) -> None:
    img = Image.open(item.path)  # reads only the header, not the pixels
    if img.width * img.height > MAX_IMAGE_PIXELS:
        item.too_large = True
        return
    img.draft("RGB", (1024, 1024))  # fast decode for big JPEGs
    img = img.convert("RGB")
    img.thumbnail((1024, 1024))
    item.image = img


READERS = {".pdf": _pdf, ".docx": _docx, ".pptx": _pptx}


def read_file(path: Path, max_read_mb: float | None = None) -> Item:
    group, category = classify_ext(path)
    item = Item(path=path, size=path.stat().st_size, sha=sha256(path), group=group, category=category)
    ext = path.suffix.lower()
    limit = (max_read_mb if max_read_mb is not None else MAX_READ_MB) * (1 << 20)
    if group != "other" and item.size > limit:  # too big: don't open it, sort it by name and type only
        item.too_large = True
        return item
    try:
        if group == "image":
            _image(item)
        elif ext in READERS:
            READERS[ext](item)
        elif ext in {".txt", ".md"} or ext in CODE_EXT:
            _plain(item)
    except Exception as e:  # corrupt or password-protected: fall back to the filename
        item.text, item.image = "", None
        item.title = ""
        item.scanned = False
        item.error = str(e)
    if item.text:
        for label, rx in NUMBERING:
            m = rx.search(item.text[:800])
            if m:
                item.number = (label, int(m.group(1)))
                break
    return item
