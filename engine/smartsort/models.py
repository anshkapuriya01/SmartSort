"""Finding the models on this computer, so nobody has to type a path.

Two kinds of model are used:

* **EmbeddingGemma 2** (required) understands files. It's looked for in the Hugging Face
  download cache, LM Studio's models folder and the usual "Models" folders.
* **A chat model** (optional) writes folder and file names. Any of these work:
  - a model folder (safetensors) from LM Studio, Hugging Face or a Models folder, run with
    MLX on Apple silicon or with Transformers anywhere else;
  - a model in **Ollama** or in **LM Studio's local server** (GGUF models included), reached
    over localhost: nothing leaves the computer.

Everything here is fast (no model is loaded) so the apps can call it on every launch.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import urllib.request
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = "http://" + OLLAMA_URL
LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234").rstrip("/")

# Small instruct models known to name files well, best first. The automatic choice is the
# first of these that's installed, else the smallest model that can run.
PREFERRED = ["llama-3.2-3b-instruct", "qwen3.5-4b", "qwen3-4b", "qwen2.5-3b-instruct", "gemma-3-4b",
             "phi-3.5-mini", "llama3.2:3b", "llama3.2", "qwen3:4b", "qwen2.5:3b", "gemma3:4b"]

EMBEDDING_TYPES = {"embedding_gemma2", "embeddinggemma2", "embedding_gemma_2"}
EMBEDDING_REPO = "google/embeddinggemma-2"


# ---------------------------------------------------------------------------------------
# Where models live

def _home() -> Path:
    return Path.home()


def hf_hub() -> Path:
    env = os.environ.get("HF_HUB_CACHE")
    if env:
        return Path(env).expanduser()
    return Path(os.environ.get("HF_HOME") or _home() / ".cache" / "huggingface").expanduser() / "hub"


def lmstudio_folders() -> list[Path]:
    home = _home()
    folders = [home / ".lmstudio" / "models", home / ".cache" / "lm-studio" / "models"]
    try:  # LM Studio lets people move its models folder
        custom = json.loads((home / ".lmstudio" / "settings.json").read_text()).get("downloadsFolder")
        if custom:
            folders.insert(0, Path(custom).expanduser())
    except (OSError, ValueError):
        pass
    return folders


def models_folders() -> list[Path]:
    """Folders people (and our setup scripts) put models in."""
    home = _home()
    out = [Path(p).expanduser() for p in os.environ.get("SMARTSORT_MODELS_DIR", "").split(os.pathsep) if p]
    out += [home / "Models", home / "models", home / "mlx_models", home / ".mlx" / "models",
            Path(__file__).resolve().parents[2] / "models"]  # <repo>/models
    if sys.platform == "win32":
        for var in ("LOCALAPPDATA", "USERPROFILE"):
            if os.environ.get(var):
                out.append(Path(os.environ[var]) / "SmartSort" / "models")
    else:
        out.append(home / ".local" / "share" / "smartsort" / "models")
    return out


def _children(root: Path, depth: int):
    """Folders exactly `depth` levels below root (0 = root itself)."""
    if not root.is_dir():
        return
    level = [root]
    for _ in range(depth):
        nxt = []
        for p in level:
            try:
                nxt += [c for c in p.iterdir() if c.is_dir() and not c.name.startswith(".")]
            except OSError:
                pass
        level = nxt
    yield from level


def _candidate_folders():
    """(source, folder) for every folder that might hold a model."""
    for snap in hf_hub().glob("models--*/snapshots/*"):
        yield "Hugging Face", snap
    for root in lmstudio_folders():
        for p in _children(root, 2):  # publisher/model
            yield "LM Studio", p
    for root in models_folders():
        for depth in (0, 1, 2):
            for p in _children(root, depth):
                yield "Models folder", p


def _identity(p: Path):
    """The same folder reached two ways (a symlink, or ~/Models vs ~/models on a
    case-insensitive disk) has one identity."""
    try:
        st = p.stat()
        return st.st_dev, st.st_ino
    except OSError:
        return None


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def _display_name(source: str, p: Path) -> str:
    if source == "Hugging Face" and p.parent.name == "snapshots":  # models--org--Name/snapshots/<hash>
        return p.parent.parent.name.split("--")[-1]
    return p.name


def _size(p: Path, pattern: str = "*.safetensors") -> int:
    total = 0
    for f in p.glob(pattern):
        try:
            total += f.stat().st_size  # follows Hugging Face's symlinks to the real blobs
        except OSError:
            pass
    return total


# ---------------------------------------------------------------------------------------
# EmbeddingGemma 2

EMBEDDING_FILES = ["config.json", "modules.json", "tokenizer.json", "tokenizer_config.json"]


def is_embedding_folder(p: Path) -> bool:
    if not (p.is_dir() and all((p / f).exists() for f in EMBEDDING_FILES) and any(p.glob("*.safetensors"))):
        return False
    config = _read_json(p / "config.json")
    kind = str(config.get("model_type", "")).lower()
    archs = " ".join(config.get("architectures") or []).lower()
    return kind in EMBEDDING_TYPES or "embeddinggemma2" in archs


def embedding_models() -> list[dict]:
    """Every copy of EmbeddingGemma 2 on this computer."""
    seen, found = set(), []
    explicit = os.environ.get("SMARTSORT_MODEL")
    candidates = ([("Environment", Path(explicit).expanduser())] if explicit else []) + [
        ("Models folder", _home() / "gemma")] + list(_candidate_folders())
    for source, p in candidates:
        key = _identity(p)
        if key is None:
            continue
        if key in seen or not is_embedding_folder(p):
            continue
        seen.add(key)
        found.append({"name": _display_name(source, p), "path": str(p), "source": source,
                      "sizeBytes": _size(p)})
    return found


def find_embedding_model(path: str | None = None) -> Path | None:
    """An explicit folder if it's valid, else the first EmbeddingGemma 2 found."""
    if path:
        p = Path(path).expanduser()
        return p if is_embedding_folder(p) else None
    found = embedding_models()
    return Path(found[0]["path"]) if found else None


# ---------------------------------------------------------------------------------------
# Chat models

CHAT_FILES = ["config.json", "tokenizer_config.json"]


def mlx_available() -> bool:
    """MLX runs on Apple silicon Macs only."""
    if sys.platform != "darwin" or platform.machine() != "arm64":
        return False
    import importlib.util

    return importlib.util.find_spec("mlx_lm") is not None


def _mlx_types() -> tuple[set[str], dict[str, str]] | None:
    """Architectures this engine's mlx_lm can run, found without loading MLX."""
    import importlib.util

    spec = importlib.util.find_spec("mlx_lm")
    if not spec or not spec.submodule_search_locations:
        return None
    base = Path(list(spec.submodule_search_locations)[0])
    types = {f.stem for f in (base / "models").glob("*.py")}
    remap = {}
    m = re.search(r"MODEL_REMAPPING\s*=\s*\{(.*?)\}", (base / "utils.py").read_text(errors="ignore"), re.S)
    if m:
        remap = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', m.group(1)))
    return types, remap


def _transformers_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("transformers") is not None and importlib.util.find_spec("torch") is not None


def parameters(name: str, size: int, bits: int | None) -> str:
    """"3B", "9B", "135M"… from the name, else estimated from the weights' size."""
    m = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*([BbMm])(?![A-Za-z])", name.replace("_", "-"))
    if m:
        return f"{m[1]}{m[2].upper()}"
    if not size:
        return ""
    count = size * 8 / (bits or 16)
    return f"~{count / 1e9:.1f}B" if count >= 1e9 else f"~{count / 1e6:.0f}M"


def is_chat_folder(p: Path) -> bool:
    if not (p.is_dir() and all((p / f).exists() for f in CHAT_FILES) and any(p.glob("*.safetensors"))):
        return False
    if (p / "modules.json").exists():  # a sentence-transformers (embedding) model
        return False
    tok = _read_json(p / "tokenizer_config.json")
    # base models (no chat template) can't follow instructions
    return bool(tok.get("chat_template") or (p / "chat_template.jinja").exists() or (p / "chat_template.json").exists())


def _folder_models() -> list[dict]:
    use_mlx = mlx_available()
    mlx_types = _mlx_types() if use_mlx else None
    has_tf = _transformers_available()
    seen, found = set(), []
    for source, p in _candidate_folders():
        key = _identity(p)
        if key is None:
            continue
        if key in seen or not is_chat_folder(p):
            continue
        seen.add(key)
        config = _read_json(p / "config.json")
        model_type = config.get("model_type", "")
        mlx_quantized = isinstance(config.get("quantization"), dict)  # MLX's own format
        other_quant = bool(config.get("quantization_config")) and not mlx_quantized
        bits = (config.get("quantization") or {}).get("bits") if mlx_quantized else None
        size = _size(p)
        name = _display_name(source, p)
        if use_mlx:
            backend, note = "mlx", ""
            ok = True
            if mlx_types:
                types, remap = mlx_types
                ok = remap.get(model_type, model_type) in types
                note = "" if ok else f"MLX can't run the {model_type} architecture yet"
        else:
            backend = "transformers"
            ok = has_tf and not mlx_quantized and not other_quant
            note = ("This is an MLX model, which needs an Apple silicon Mac" if mlx_quantized
                    else "Quantized models need Ollama or LM Studio on this computer" if other_quant
                    else "" if ok else "Transformers isn't installed")
        found.append({
            "name": name, "path": str(p), "source": source, "backend": backend,
            "parameters": parameters(name, size, bits), "bits": bits, "sizeBytes": size,
            "architecture": model_type, "supported": ok, "note": note,
        })
    return found


def _get_json(url: str, timeout: float = 0.6):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _looks_like_embedding(name: str) -> bool:
    return bool(re.search(r"embed|bge|e5-|nomic|minilm|rerank", name, re.I))


def ollama_models() -> list[dict]:
    """Models in Ollama. Listed from the running app, or from its folder when it isn't running."""
    tags = _get_json(f"{OLLAMA_URL}/api/tags")
    found = []
    if tags is not None:
        for m in tags.get("models", []):
            name = m.get("name", "")
            if not name or _looks_like_embedding(name):
                continue
            d = m.get("details") or {}
            found.append({
                "name": name, "path": f"ollama:{name}", "source": "Ollama", "backend": "ollama",
                "parameters": d.get("parameter_size", "") or parameters(name, 0, None),
                "bits": None, "sizeBytes": int(m.get("size") or 0),
                "architecture": d.get("family", ""), "supported": True, "note": "",
            })
        return found
    base = Path(os.environ.get("OLLAMA_MODELS") or _home() / ".ollama" / "models") / "manifests"
    for manifest in base.glob("*/*/*/*"):  # registry/namespace/model/tag
        if not manifest.is_file():
            continue
        model, tag = manifest.parent.name, manifest.name
        name = f"{model}:{tag}" if manifest.parent.parent.name == "library" else \
            f"{manifest.parent.parent.name}/{model}:{tag}"
        if _looks_like_embedding(name):
            continue
        found.append({
            "name": name, "path": f"ollama:{name}", "source": "Ollama", "backend": "ollama",
            "parameters": parameters(tag if re.search(r"\d+[bm]", tag, re.I) else model, 0, None),
            "bits": None, "sizeBytes": 0, "architecture": "", "supported": False,
            "note": "Open Ollama to use this model",
        })
    return found


def lmstudio_server_models(folder_names: set[str]) -> list[dict]:
    """Models LM Studio's local server offers (GGUF included), when the server is on. Models
    already found as MLX folders are skipped."""
    data = _get_json(f"{LMSTUDIO_URL}/v1/models")
    found = []
    for m in (data or {}).get("data", []):
        mid = m.get("id", "")
        short = mid.split("/")[-1]
        if not mid or _looks_like_embedding(mid) or short.lower() in folder_names:
            continue
        found.append({
            "name": short, "path": f"lmstudio:{mid}", "source": "LM Studio server", "backend": "lmstudio",
            "parameters": parameters(short, 0, None), "bits": None, "sizeBytes": 0,
            "architecture": "", "supported": True, "note": "",
        })
    return found


def chat_models() -> list[dict]:
    """Every chat model that could write names, runnable ones first."""
    folders = _folder_models()
    found = folders + ollama_models() + lmstudio_server_models({m["name"].lower() for m in folders})
    return sorted(found, key=lambda m: (not m["supported"], m["name"].lower()))


def default_chat_model(models: list[dict] | None = None) -> str | None:
    """What "Automatic" means: SMARTSORT_NAMER, else a known-good small model, else the
    smallest one that runs (bigger is slower, and naming needs little)."""
    env = os.environ.get("SMARTSORT_NAMER")
    if env:
        return env
    usable = [m for m in (models if models is not None else chat_models()) if m["supported"]]
    if not usable:
        return None
    for pref in PREFERRED:
        for m in usable:
            if pref in m["name"].lower():
                return m["path"]
    sized = sorted((m for m in usable if m["sizeBytes"] > 300_000_000), key=lambda m: m["sizeBytes"])
    return (sized or usable)[0]["path"]


def is_server_ref(ref: str) -> bool:
    return ref.startswith(("ollama:", "lmstudio:"))


def resolve_chat_model(ref: str | None) -> str | None:
    """A model reference that can be opened: the one asked for if it's usable, else the default."""
    if ref:
        if is_server_ref(ref):
            return ref
        p = Path(ref).expanduser()
        return str(p) if is_chat_folder(p) else None
    return default_chat_model()


def label(ref: str) -> str:
    """A short name for a model reference."""
    if is_server_ref(ref):
        return ref.split(":", 1)[1].split("/")[-1]
    p = Path(ref)
    if p.parent.name == "snapshots":
        return p.parent.parent.name.split("--")[-1]
    return p.name
