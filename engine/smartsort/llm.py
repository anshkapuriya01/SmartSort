"""Running a chat model, whichever way it's installed. All of them run on this computer:

* ``mlx``          a model folder, with MLX (Apple silicon Macs)
* ``transformers`` a model folder, with PyTorch (Windows, Linux, Intel Macs; uses CUDA if present)
* ``ollama``       a model in Ollama, through its local API (``ollama:llama3.2:3b``)
* ``lmstudio``     a model in LM Studio's local server (``lmstudio:qwen2.5-3b-instruct``)

Every backend answers deterministically (temperature 0) and with "thinking" turned off, so
reasoning models answer straight away instead of spending the token budget thinking.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from . import models


class Backend:
    def chat(self, system: str, user: str, max_tokens: int) -> str:
        raise NotImplementedError


class MLXBackend(Backend):
    def __init__(self, path: str):
        from mlx_lm import load

        self.model, self.tok = load(path)

    def chat(self, system, user, max_tokens):
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = self.tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False,
                                              enable_thinking=False)
        return generate(self.model, self.tok, prompt=prompt, max_tokens=max_tokens,
                        sampler=make_sampler(temp=0.0), verbose=False)


class TransformersBackend(Backend):
    def __init__(self, path: str):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from transformers.utils import logging

        logging.set_verbosity_error()
        if torch.cuda.is_available():
            device, dtype = "cuda", torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        elif torch.backends.mps.is_available():
            device, dtype = "mps", torch.bfloat16
        else:
            device, dtype = "cpu", torch.float32
        self.device = device
        self.tok = AutoTokenizer.from_pretrained(path)
        self.model = AutoModelForCausalLM.from_pretrained(path, dtype=dtype).to(device).eval()

    def chat(self, system, user, max_tokens):
        import torch

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = self.tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False,
                                              enable_thinking=False)
        inputs = self.tok(prompt, return_tensors="pt", add_special_tokens=False).to(self.device)
        with torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=max_tokens, do_sample=False,
                                      pad_token_id=self.tok.pad_token_id or self.tok.eos_token_id)
        return self.tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def _post(url: str, body: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class OllamaBackend(Backend):
    def __init__(self, name: str):
        self.name = name
        if models._get_json(f"{models.OLLAMA_URL}/api/tags") is None:
            raise RuntimeError("Ollama isn't running. Open Ollama, then analyze again.")

    def chat(self, system, user, max_tokens):
        r = _post(f"{models.OLLAMA_URL}/api/chat", {
            "model": self.name, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_predict": max_tokens},
        })
        return (r.get("message") or {}).get("content", "")


class OpenAIServerBackend(Backend):
    """LM Studio's server speaks the OpenAI chat API."""

    def __init__(self, base: str, name: str):
        self.base, self.name = base, name
        if models._get_json(f"{base}/v1/models") is None:
            raise RuntimeError("LM Studio's local server isn't running. Start it in LM Studio, then analyze again.")

    def chat(self, system, user, max_tokens):
        r = _post(f"{self.base}/v1/chat/completions", {
            "model": self.name, "temperature": 0, "max_tokens": max_tokens, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        })
        return ((r.get("choices") or [{}])[0].get("message") or {}).get("content", "")


def open_backend(ref: str) -> Backend:
    if ref.startswith("ollama:"):
        return OllamaBackend(ref.split(":", 1)[1])
    if ref.startswith("lmstudio:"):
        return OpenAIServerBackend(models.LMSTUDIO_URL, ref.split(":", 1)[1])
    path = str(Path(ref).expanduser())
    config = models._read_json(Path(path) / "config.json")
    if models.mlx_available():
        return MLXBackend(path)
    if isinstance(config.get("quantization"), dict):
        raise RuntimeError(f"“{Path(path).name}” is an MLX model, which needs an Apple silicon Mac. "
                           "Choose another naming model in Settings.")
    return TransformersBackend(path)


def clean_reply(text: str) -> str:
    """Drop any reasoning a model wrote despite being asked not to."""
    return re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.S).strip()
