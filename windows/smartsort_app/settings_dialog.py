"""Settings: General, Models and Engine. Models are found automatically; picking one by hand is
optional."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from . import settings
from .engine import engine_command
from .review import RENAME_SCOPES, label

EMBED_HINT = "hf download google/embeddinggemma-2"


def tilde(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def model_label(ref: str) -> str:
    if ref.startswith(("ollama:", "lmstudio:")):
        return ref.split(":", 1)[1].split("/")[-1]
    p = Path(ref)
    if p.parent.name == "snapshots":
        return p.parent.parent.name.split("--")[-1]
    return p.name


def model_detail(m: dict) -> str:
    size = f"{m['sizeBytes'] / 1e9:.1f} GB" if m.get("sizeBytes") else ""
    via = {"ollama": "Ollama", "lmstudio": "LM Studio server"}.get(m.get("backend"), "")
    return " · ".join(x for x in [m.get("parameters"), f"{m['bits']}-bit" if m.get("bits") else "", size, via] if x)


class SettingsDialog(QDialog):
    def __init__(self, catalog: dict | None, rescan, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(640)
        self.catalog = catalog or {}
        self.rescan = rescan
        tabs = QTabWidget()
        tabs.addTab(self._general(), "General")
        tabs.addTab(self._models(), "Models")
        tabs.addTab(self._engine(), "Engine")
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)

    # ---- General ------------------------------------------------------------------------

    def _general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)
        size = QComboBox()
        for mb in (10, 25, 50, 100, 250):
            size.addItem(f"{mb} MB", mb)
        size.setCurrentIndex(max(0, [10, 25, 50, 100, 250].index(settings.get("maxReadMB"))
                                 if settings.get("maxReadMB") in (10, 25, 50, 100, 250) else 2))
        size.currentIndexChanged.connect(lambda i: settings.put("maxReadMB", size.itemData(i)))
        form.addRow("Don’t read files larger than", size)
        form.addRow("", label("Larger documents and images are left unopened, which keeps analysis fast. "
                              "They’re still sorted by file type, or put in Needs Review.", "Small", wrap=True))
        rename = QComboBox()
        for key, title in RENAME_SCOPES:
            rename.addItem(title, key)
        rename.setCurrentIndex([k for k, _ in RENAME_SCOPES].index(settings.get("renameMode")))
        rename.currentIndexChanged.connect(lambda i: settings.put("renameMode", rename.itemData(i)))
        form.addRow("Suggest new names for", rename)
        form.addRow("", label("Unhelpful names are ones like “document(3).pdf” or “scan_0012.pdf”. "
                              "Applies to the next analysis.", "Small", wrap=True))
        return w

    # ---- Models -------------------------------------------------------------------------

    def _models(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        lay.addWidget(label("Understanding files: EmbeddingGemma 2", "Heading"))
        self.embed = QComboBox()
        self._fill_embedding()
        self.embed.currentIndexChanged.connect(lambda _: self._save_combo(self.embed, "embeddingModelPath"))
        lay.addLayout(self._picker_row(self.embed, self._choose_embedding))
        self.embed_status = label("", "Small", wrap=True)
        lay.addWidget(self.embed_status)
        lay.addLayout(self._hint_row(EMBED_HINT))

        lay.addSpacing(10)
        lay.addWidget(label("Naming", "Heading"))
        self.use_naming = QCheckBox("Write folder and file names with a language model")
        self.use_naming.setChecked(settings.get("useNamingModel"))
        self.use_naming.toggled.connect(self._toggle_naming)
        lay.addWidget(self.use_naming)
        self.naming = QComboBox()
        self._fill_naming()
        self.naming.currentIndexChanged.connect(lambda _: self._save_combo(self.naming, "namingModelPath"))
        lay.addLayout(self._picker_row(self.naming, self._choose_naming))
        self.naming_status = label("", "Small", wrap=True)
        lay.addWidget(self.naming_status)
        lay.addWidget(label("Any instruct model works: a model folder from LM Studio or Hugging Face "
                            "(run with Transformers), or a model in Ollama or LM Studio’s local server. "
                            "Bigger models write better names but take longer.", "Small", wrap=True))
        lay.addStretch()
        self._update_status()
        self._toggle_naming(self.use_naming.isChecked())
        return w

    def _picker_row(self, combo: QComboBox, choose) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(combo, 1)
        b = QPushButton("Choose Folder…")
        b.clicked.connect(choose)
        row.addWidget(b)
        again = QPushButton("Look Again")
        again.clicked.connect(self._rescan)
        row.addWidget(again)
        return row

    def _hint_row(self, command: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(label("Don’t have it? Run:", "Small"))
        code = QLineEdit(command)
        code.setReadOnly(True)
        code.setStyleSheet("font-family: Consolas, Menlo, monospace;")
        row.addWidget(code, 1)
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(command))
        row.addWidget(copy)
        return row

    def _fill_embedding(self):
        self.embed.blockSignals(True)
        self.embed.clear()
        default = self.catalog.get("defaultEmbedding")
        self.embed.addItem(f"Automatic ({model_label(default)})" if default else "Automatic", "")
        for c in self.catalog.get("embedding") or []:
            self.embed.addItem(f"{c['name']}  ·  {c['source']}", c["path"])
        self._select(self.embed, settings.get("embeddingModelPath"))
        self.embed.blockSignals(False)

    def _fill_naming(self):
        self.naming.blockSignals(True)
        self.naming.clear()
        default = self.catalog.get("defaultNaming")
        self.naming.addItem(f"Automatic ({model_label(default)})" if default else "Automatic", "")
        for m in self.catalog.get("models") or []:
            if m["supported"]:
                self.naming.addItem(f"{m['name']}  ·  {model_detail(m)}", m["path"])
        self._select(self.naming, settings.get("namingModelPath"))
        self.naming.blockSignals(False)

    @staticmethod
    def _select(combo: QComboBox, value: str):
        index = combo.findData(value)
        if index < 0 and value:
            combo.addItem(f"Other: {model_label(value)}", value)
            index = combo.count() - 1
        combo.setCurrentIndex(max(index, 0))

    def _save_combo(self, combo: QComboBox, key: str):
        settings.put(key, combo.currentData() or "")
        self._update_status()

    def _choose_embedding(self):
        path = QFileDialog.getExistingDirectory(self, "Choose the EmbeddingGemma 2 folder (with config.json and modules.json)")
        if path:
            settings.put("embeddingModelPath", path)
            self._fill_embedding()
            self._update_status()

    def _choose_naming(self):
        path = QFileDialog.getExistingDirectory(self, "Choose the folder of an instruct model (with config.json)")
        if path:
            settings.put("namingModelPath", path)
            self._fill_naming()
            self._update_status()

    def _toggle_naming(self, on: bool):
        settings.put("useNamingModel", on)
        self.naming.setEnabled(on)
        self._update_status()

    def _rescan(self):
        self.catalog = self.rescan() or {}
        self._fill_embedding()
        self._fill_naming()
        self._update_status()

    def _update_status(self):
        if not hasattr(self, "naming_status"):
            return
        saved = settings.get("embeddingModelPath")
        if saved:
            ok = (Path(saved) / "modules.json").exists() and (Path(saved) / "config.json").exists()
            self.embed_status.setText("✅ Ready" if ok else "❌ That folder doesn’t contain EmbeddingGemma 2.")
        elif self.catalog.get("defaultEmbedding"):
            self.embed_status.setText(f"✅ Ready (found automatically at {tilde(self.catalog['defaultEmbedding'])})")
        elif self.catalog:
            self.embed_status.setText("⚠️ Not found. Download it with the command below, then click Look Again.")
        else:
            self.embed_status.setText("The engine couldn’t be reached, so models couldn’t be looked for.")
        if not settings.get("useNamingModel"):
            self.naming_status.setText("Off: folders are named by EmbeddingGemma alone.")
            return
        ref = settings.get("namingModelPath") or self.catalog.get("defaultNaming")
        if not ref:
            self.naming_status.setText("No language model found: folders are named by EmbeddingGemma alone.")
            return
        known = next((m for m in self.catalog.get("models") or [] if m["path"] == ref), None)
        if known and not known["supported"]:
            self.naming_status.setText(f"⚠️ {known['note']}")
        else:
            where = ("Ollama" if ref.startswith("ollama:") else "LM Studio’s local server"
                     if ref.startswith("lmstudio:") else tilde(ref))
            self.naming_status.setText(f"✅ {model_label(ref)} ({where})")

    # ---- Engine -------------------------------------------------------------------------

    def _engine(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(18, 18, 18, 18)
        form.setSpacing(12)
        row = QHBoxLayout()
        self.engine_edit = QLineEdit(settings.get("enginePath"))
        self.engine_edit.setPlaceholderText("Automatic (the smartsort package installed with this app)")
        self.engine_edit.editingFinished.connect(self._save_engine)
        row.addWidget(self.engine_edit, 1)
        b = QPushButton("Choose…")
        b.clicked.connect(self._choose_engine)
        row.addWidget(b)
        form.addRow("Engine", row)
        self.engine_status = QLabel()
        form.addRow("Status", self.engine_status)
        form.addRow("", label("The engine runs both models on this computer. Nothing leaves your computer.",
                              "Small", wrap=True))
        self._update_engine_status()
        return w

    def _save_engine(self):
        settings.put("enginePath", self.engine_edit.text().strip())
        self._update_engine_status()

    def _choose_engine(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the smartsort command (smartsort.exe in the engine’s .venv\\Scripts)")
        if path:
            self.engine_edit.setText(path)
            self._save_engine()

    def _update_engine_status(self):
        cmd = engine_command()
        self.engine_status.setText("✅ Ready: " + " ".join(cmd) if cmd else "❌ Not found")
