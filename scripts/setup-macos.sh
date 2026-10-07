#!/usr/bin/env bash
# SmartSort setup for macOS: engine + models + app, in one go.
#
#   ./scripts/setup-macos.sh                 # everything
#   ./scripts/setup-macos.sh --no-app        # engine and models only (use the CLI)
#   ./scripts/setup-macos.sh --no-naming-model
#
# Safe to run again: steps that are already done are skipped.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="$ROOT/engine"
VENV="$ENGINE/.venv"
BUILD_APP=1
NAMING_MODEL=1
for arg in "$@"; do
  case "$arg" in
    --no-app) BUILD_APP=0 ;;
    --no-naming-model) NAMING_MODEL=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg"; exit 2 ;;
  esac
done

bold() { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }

bold "1/4  Python tools (uv)"
if ! command -v uv >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then brew install uv; else curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi
fi
ok "uv $(uv --version | cut -d' ' -f2)"

bold "2/4  Engine"
[ -d "$VENV" ] || uv venv "$VENV" --python 3.12 --quiet
VIRTUAL_ENV="$VENV" uv pip install --quiet -e "$ENGINE"
ok "engine installed at $VENV/bin/smartsort"
SMARTSORT="$VENV/bin/smartsort"
HF="$VENV/bin/hf"

bold "3/4  Models"
MODELS_JSON="$("$SMARTSORT" api models)"
has() { printf '%s' "$MODELS_JSON" | "$VENV/bin/python" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('$1') else 1)"; }
if has defaultEmbedding; then
  ok "EmbeddingGemma 2 already on this Mac"
else
  echo "  Downloading EmbeddingGemma 2 (about 1.5 GB)…"
  "$HF" download google/embeddinggemma-2 >/dev/null
  ok "EmbeddingGemma 2 downloaded"
fi
if [ "$NAMING_MODEL" = 1 ]; then
  if has defaultNaming; then
    ok "a naming model is already on this Mac"
  elif [ "$(uname -m)" = "arm64" ]; then
    echo "  Downloading Llama 3.2 3B Instruct, MLX (about 1.8 GB)…"
    "$HF" download mlx-community/Llama-3.2-3B-Instruct-4bit >/dev/null
    ok "Llama 3.2 3B Instruct downloaded"
  elif command -v ollama >/dev/null 2>&1; then
    echo "  Downloading Llama 3.2 3B in Ollama (about 2 GB)…"   # Intel Macs can't run MLX
    ollama pull llama3.2:3b
    ok "Llama 3.2 3B ready in Ollama"
  else
    echo "  No naming model yet (optional). On an Intel Mac, install Ollama (https://ollama.com/download)"
    echo "  and run: ollama pull llama3.2:3b"
  fi
fi
"$SMARTSORT" models

bold "4/4  App"
if [ "$BUILD_APP" = 0 ]; then
  echo "  Skipped (--no-app). Try the command line: $SMARTSORT ~/Downloads --dry-run"
  exit 0
fi
if ! xcodebuild -version >/dev/null 2>&1; then
  echo "  Xcode isn't installed, so the app can't be built. Install Xcode from the App Store and run this again,"
  echo "  or use the command line meanwhile: $SMARTSORT ~/Downloads --dry-run"
  exit 0
fi
cd "$ROOT/macos"
xcodebuild -project SmartSort.xcodeproj -scheme SmartSort -configuration Release \
  -derivedDataPath "$ROOT/macos/build" -quiet build
APP="$ROOT/macos/build/Build/Products/Release/SmartSort.app"
DEST="/Applications"
[ -w "$DEST" ] || { DEST="$HOME/Applications"; mkdir -p "$DEST"; }
rm -rf "$DEST/SmartSort.app"
cp -R "$APP" "$DEST/"
ok "SmartSort.app installed in $DEST"
bold "Done. Open SmartSort from $DEST and drop a folder on it."
