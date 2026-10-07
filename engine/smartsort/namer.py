"""Names folders and files with a local chat model (any one SmartSort finds: see models.py;
Llama 3.2 3B Instruct when it's installed).

EmbeddingGemma decides which files belong together; this model reads short excerpts of a
group's documents and writes a natural folder name for the group and a clear name for each
file. Answers are cached by prompt, so re-running on the same folder is instant. If the
model isn't available, callers fall back to the embedding-based names.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from .embed import CACHE_DB
from .extract import Item

BATCH = 8  # documents per request; small models stay accurate with short prompts
EXCERPT = 360  # characters of each document shown to the model
PROMPT_VERSION = "v4"

FOLDER_PROMPT = (
    "You name folders on a computer. You get excerpts of documents that will go in one folder.\n"
    "Reply with the folder name only: 1 to 3 words, Title Case, no quotes, no punctuation at the end.\n"
    "Rules:\n"
    "- Name what ALL the documents have in common, the way a person would name the folder "
    "(for example: Travel, Food Orders, Bills & Statements, Job Applications, Marketing, Recipes).\n"
    "- If the documents differ, use a broader name that covers every one of them.\n"
    "- Never use a person's name, a company name or a date as the folder name.\n"
    "- Do not name it after only one of the documents."
)

SINGLE_FOLDER_PROMPT = (
    "You name folders on a computer. You get an excerpt of a document.\n"
    "Reply with the name of a general folder that would hold this kind of document: 1 or 2 words, "
    "Title Case, no quotes. For example: Legal, Insurance, Recipes, Health, Research, Code, "
    "To-do Lists, Manuals.\n"
    "Never use a person's name, a company name or a date."
)

FILE_PROMPT = (
    "You rename a document so it is easy to find later. You get an excerpt of its content.\n"
    "Reply with the new file name only: no quotes, no file extension, at most 60 characters.\n"
    "Rules:\n"
    "- If a title is given, use it as the basis of the name.\n"
    "- Start with what the document is (for example: Invoice, Bank Statement, Flight Ticket, Meeting Notes).\n"
    "- Then add the company, shop or person it is from or about, if the excerpt names one.\n"
    "- End with the document's date as YYYY-MM-DD, only if the excerpt states a date.\n"
    "- Use only facts that appear in the excerpt. Never guess a date, name or company."
)

FITS_PROMPT = (
    "You keep a computer's folders tidy. You get a folder's name, the titles of the files already in it, "
    "and an excerpt of a new document.\n"
    "Would a careful person file the new document in this folder, because it is about the same subject "
    "as the files there? Reply yes or no only."
)

# Words a file name may contain even when the excerpt doesn't (generic document words).
GENERIC = set("""
invoice receipt order orders summary statement bill bills ticket tickets booking bookings confirmation
report reports notes note letter agreement contract policy schedule resume cv certificate manual guide
user plan review meeting minutes application form chapter return acknowledgement payslip salary slip
tax income insurance medical test result results recipe list todo checklist presentation proposal
quote estimate itinerary travel flight train hotel ride trip cab taxi food grocery groceries bank
account card credit debit payment purchase delivery delivered monthly annual quarterly weekly daily
business marketing campaign performance overview update cover letter research paper article study
lab laboratory blood count reservation e-ticket eticket electricity utility rental lease
non-disclosure nda mutual business code script data export sales expense expenses shopping and the
of for with from to on at by in
""".split())
def _dictionary() -> set[str]:
    """Ordinary lowercase English words (macOS ships a word list); used to keep people's and
    companies' names out of folder names."""
    try:
        return {w.strip() for w in open("/usr/share/dict/words") if w[:1].islower()}
    except OSError:
        return set()


DICTIONARY = _dictionary()


def _is_word(w: str) -> bool:
    """An ordinary word, allowing plurals: deliveries, taxes, statements."""
    forms = {w, w[:-1], w[:-2], w[:-3] + "y"} if len(w) > 3 else {w}
    return w in GENERIC or any(f in DICTIONARY for f in forms)
MONTHS = set("january february march april may june july august september october november december".split())

def find_model(ref: str | None = None) -> str | None:
    """The model to use: the one asked for (a folder, or ollama:/lmstudio: name) if it's usable,
    otherwise the automatic choice."""
    from .models import resolve_chat_model

    return resolve_chat_model(ref)


def installed_models() -> list[dict]:
    from .models import chat_models

    return chat_models()


def excerpt(it: Item) -> str:
    text = re.sub(r"\s+", " ", f"{it.title}. {it.text}" if it.title else it.text).strip()
    return text[:EXCERPT]


def clean_name(name: str, limit: int = 60) -> str:
    # 2026/09/26, 2026.09.26 or 2026 09 26 -> 2026-09-26
    name = re.sub(r"\b((?:19|20)\d\d)[/. ](\d{1,2})[/. ](\d{1,2})\b",
                  lambda m: f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}", str(name))
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", name)
    name = re.sub(r"\.(pdf|docx?|pptx?|txt|md|xlsx?|csv)$", "", name.strip(), flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" .-_")
    return name[:limit].rstrip(" .-_")


class Namer:
    def __init__(self, ref: str | Path):
        from .models import label

        self.ref = str(ref)
        self.model_path = Path(self.ref)  # kept for callers that show the model's name
        self.name = label(self.ref)
        self._backend = None
        CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(CACHE_DB)
        self.db.execute("CREATE TABLE IF NOT EXISTS names (key TEXT PRIMARY KEY, reply TEXT)")

    def _ask(self, system: str, user: str, max_tokens: int) -> str:
        key = hashlib.sha256(f"{PROMPT_VERSION}|{self.name}|{system}|{user}".encode()).hexdigest()
        row = self.db.execute("SELECT reply FROM names WHERE key=?", (key,)).fetchone()
        if row:
            return row[0]
        from .llm import clean_reply, open_backend

        if self._backend is None:
            self._backend = open_backend(self.ref)
        reply = clean_reply(self._backend.chat(system, user, max_tokens))
        self.db.execute("INSERT OR REPLACE INTO names VALUES (?, ?)", (key, reply))
        self.db.commit()
        return reply

    def folder_name(self, items: list[Item], taken: set[str] | None = None) -> str | None:
        """A folder name for a group, from short excerpts of (up to) its first eight files.
        When `taken` names are given (other groups already use them), the model is asked for
        three options and the first acceptable one that isn't taken wins."""
        if not items:
            return None
        if len(items) == 1:
            system, user = SINGLE_FOLDER_PROMPT, excerpt(items[0])[:300]
        else:
            system = FOLDER_PROMPT
            user = "\n".join(f"{i + 1}. {excerpt(it)[:220]}" for i, it in enumerate(items[:BATCH]))
        if not taken:
            return self._check_folder((self._ask(system, user, 16).strip().splitlines() or [""])[0])
        system += ("\n\nInstead of one name, reply with three different possible folder names, one per line, "
                   "most fitting first.")
        lowered = {t.lower() for t in taken}
        for line in self._ask(system, user, 40).strip().splitlines():
            name = self._check_folder(re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", line))
            if name and name.lower() not in lowered:
                return name
        return None

    def fits_folder(self, it: Item, folder: str, titles: list[str]) -> bool:
        """Whether the document belongs in `folder`, judging by the titles of files already there.
        Yes/no is asked about one folder at a time: small models answer that far more reliably
        than picking from a list, and a wrong "no" only means a new folder, not a misfiled file."""
        user = (f"Folder: {folder.replace('/', ' > ')}\nFiles in it: " + "; ".join(t[:60] for t in titles[:6])
                + f"\n\nNew document: {excerpt(it)[:300]}")
        return self._ask(FITS_PROMPT, user, 3).strip().lower().startswith("yes")

    @staticmethod
    def _check_folder(reply: str) -> str | None:
        name = clean_name(reply.strip('"\'*'), 40)
        words = name.split()
        if not 1 <= len(words) <= 4 or re.search(r"\d", name):
            return None
        if DICTIONARY:  # every word must be an ordinary word: no people, companies or brands
            for w in re.findall(r"[A-Za-z]+", name):
                if not _is_word(w.lower()):
                    return None
        return name

    def file_name(self, it: Item) -> str | None:
        """A new name for one file, written from its own content only, then fact-checked:
        every specific word and any date must appear in the document, or the name is refused."""
        body = re.sub(r"\s+", " ", it.text).strip()[:EXCERPT]
        if len(body) < 40:
            return None
        text = (f"Title: {it.title}\n" if it.title else "") + f"Excerpt: {body}"
        reply = (self._ask(FILE_PROMPT, text, 32).strip().splitlines() or [""])[0]
        reply = re.split(r"(?<=[a-z])\.\s", reply)[0]  # drop a trailing sentence fragment
        name = clean_name(reply.strip('"\'*'))
        words = name.split()
        for size in range(len(words) // 2, 1, -1):  # "Chemical Bonding X Chemical Bonding" -> drop the repeat
            for i in range(len(words) - size):
                if [w.lower() for w in words[i:i + size]] in (
                        [[w.lower() for w in words[j:j + size]] for j in range(i + size, len(words) - size + 1)]):
                    words = words[:i + size] + [w for w in words[i + size:] if w.lower() not in
                                                {x.lower() for x in words[i:i + size]}]
                    break
        name = " ".join(words)
        if re.search(r"[=(){}\[\]]", name):  # copied a formula or code, not a name
            return None
        if len(name) > 60:
            name = name[:60].rsplit(" ", 1)[0]
        if len(name) < 3 or name.lower() == it.path.stem.lower():
            return None
        source = re.sub(r"\s+", " ", f"{it.title} {it.text}").lower()
        source_digits = re.sub(r"\D", "", source)
        for year in re.findall(r"(?:19|20)\d\d", name):
            if year not in source:
                return None
        for date in re.findall(r"\d{4}-\d{2}-\d{2}", name):  # day and month must be stated too
            y, m, d = date.split("-")
            if str(int(d)) not in source_digits and d not in source:
                return None
        for acronym in re.findall(r"\b[A-Z]{2,3}\b", name):  # e.g. "ABC Bank"
            if acronym.lower() not in source and acronym.lower() not in GENERIC:
                return None
        for word in re.findall(r"[A-Za-z][A-Za-z'\-]{3,}", name):
            w = word.lower()
            if w not in GENERIC and w not in MONTHS and w not in source:
                return None
        return name
