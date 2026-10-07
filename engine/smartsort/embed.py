"""Turn files and labels into EmbeddingGemma 2 vectors, with an on-disk cache."""

from __future__ import annotations

import os
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np

from .extract import Item

def cache_dir() -> Path:
    """Where vectors and names are cached, in each system's usual place for caches."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "smartsort"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SmartSort" / "Cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "smartsort"


CACHE_DB = cache_dir() / "embeddings.sqlite"


class ModelNotFound(RuntimeError):
    pass


NOT_FOUND = ("EmbeddingGemma 2 wasn’t found on this computer. Download it once with:\n"
             "    hf download google/embeddinggemma-2\n"
             "or choose its folder in Settings (or pass --model).")
CACHE_VERSION = "v1"  # bump when the way inputs are built changes


# Symmetric-task prefixes from the model card. "cluster" vectors are best for subject,
# "classify" vectors are best for document type (measured on the demo folder).
PREFIX = {"cluster": "task: clustering | query: ", "classify": "task: classification | query: "}


def doc_input(item: Item, mode: str) -> str:
    """Title + content; the filename when there's nothing else to go on."""
    body = item.text.strip() or item.path.stem.replace("_", " ")
    return f"{PREFIX[mode]}title: {item.title or 'none'} | text: {body}"


class Embedder:
    def __init__(self, model_path: str | None = None):
        from .models import find_embedding_model

        found = find_embedding_model(model_path)
        if found is None:
            if model_path:
                raise ModelNotFound(f"“{model_path}” isn’t an EmbeddingGemma 2 folder. " + NOT_FOUND)
            raise ModelNotFound(NOT_FOUND)
        self.model_path = str(found)
        self._model = None
        CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(CACHE_DB)
        self.db.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vec BLOB)")

    @property
    def model(self):
        if self._model is None:
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            warnings.filterwarnings("ignore")
            import torch
            import transformers
            from sentence_transformers import SentenceTransformer

            transformers.logging.set_verbosity_error()
            transformers.logging.disable_progress_bar()
            if torch.backends.mps.is_available():
                device, dtype = "mps", torch.bfloat16
            elif torch.cuda.is_available():
                device = "cuda"
                dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32
            else:  # never float16: this model overflows in it
                device, dtype = "cpu", torch.float32
            self._model = SentenceTransformer(
                self.model_path,
                device=device,
                model_kwargs={"torch_dtype": dtype},
                config_kwargs={"audio_config": None},  # text + images only: smaller and faster
            )
        return self._model

    def _encode(self, inputs: list, batch_size: int) -> np.ndarray:
        vecs = self.model.encode(inputs, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    def items(self, items: list[Item], mode: str, progress=None) -> np.ndarray:
        """One vector per item ("cluster" | "classify" | "image").

        Cached by file content hash, so renamed or moved files cost nothing next time."""
        out = np.zeros((len(items), 768), dtype=np.float32)
        keys = [f"{CACHE_VERSION}:{mode}:{it.sha}" for it in items]
        todo = []
        for i, key in enumerate(keys):
            row = self.db.execute("SELECT vec FROM emb WHERE key=?", (key,)).fetchone()
            if row:
                out[i] = np.frombuffer(row[0], dtype=np.float32)
            else:
                todo.append(i)
        done = len(items) - len(todo)
        if progress and items:
            progress(done, len(items))
        step = 4 if mode == "image" else 8
        for s in range(0, len(todo), step):
            chunk = todo[s : s + step]
            if mode == "image":
                inputs = [{"image": items[i].image} for i in chunk]
            else:
                inputs = [doc_input(items[i], mode) for i in chunk]
            for i, v in zip(chunk, self._encode(inputs, step), strict=False):
                out[i] = v
                self.db.execute("INSERT OR REPLACE INTO emb VALUES (?, ?)", (keys[i], v.tobytes()))
            self.db.commit()
            done += len(chunk)
            if progress:
                progress(done, len(items))
        return out

    def labels(self, labels: list[str], mode: str) -> np.ndarray:
        """Embed short label texts; cached, since folder-name candidates number in the thousands."""
        texts = [PREFIX[mode] + label for label in labels]
        out = np.zeros((len(texts), 768), dtype=np.float32)
        todo = []
        for i, t in enumerate(texts):
            row = self.db.execute("SELECT vec FROM emb WHERE key=?", (f"{CACHE_VERSION}:label:{t}",)).fetchone()
            if row:
                out[i] = np.frombuffer(row[0], dtype=np.float32)
            else:
                todo.append(i)
        for s in range(0, len(todo), 128):
            chunk = todo[s : s + 128]
            for i, v in zip(chunk, self._encode([texts[i] for i in chunk], 128), strict=False):
                out[i] = v
                self.db.execute("INSERT OR REPLACE INTO emb VALUES (?, ?)", (f"{CACHE_VERSION}:label:{texts[i]}", v.tobytes()))
        if todo:
            self.db.commit()
        return out
