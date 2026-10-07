"""SmartSort's main window for Windows (and Linux): the same flow as the macOS app.

Choose or drop a folder → SmartSort analyzes it → review the plan as blocks or a list, untick
what should stay, fix names → Organize → undo any time.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QPushButton, QSizePolicy, QSplitter, QStackedWidget, QToolBar,
                               QVBoxLayout, QWidget)

from . import settings, style
from .engine import EngineRun, engine_command, reveal
from .pages import AnalyzingPage, BusyPage, DonePage, EmptyPage, MessagePage, button
from .plan import Plan
from .review import ReviewView, label
from .settings_dialog import SettingsDialog, model_detail, model_label


def has_undo(folder: str) -> bool:
    history = Path(folder) / ".smartsort" / "history"
    return history.is_dir() and any(history.glob("*.jsonl"))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartSort")
        self.resize(1240, 800)
        self.setMinimumSize(960, 600)
        self.setAcceptDrops(True)
        self.folder: str | None = None
        self.plan: Plan | None = None
        self.run: EngineRun | None = None
        self.catalog: dict | None = None
        self.last_mode, self.last_include_kept = "auto", False
        self.renamed_count = 0

        self.pages = QStackedWidget()
        self.empty = EmptyPage()
        self.analyzing = AnalyzingPage()
        self.review = ReviewView()
        self.busy = BusyPage()
        self.done = DonePage()
        self.uptodate = MessagePage("✔️", "Nothing New to Sort")
        self.failed = MessagePage("⚠️", "Couldn’t Analyze the Folder")
        for p in (self.empty, self.analyzing, self.review, self.busy, self.done, self.uptodate, self.failed):
            self.pages.addWidget(p)

        self.empty.choose.connect(self.choose_folder)
        self.empty.open_recent.connect(self.analyze)
        self.analyzing.cancel.connect(self.cancel)
        self.review.organize.connect(self.organize)
        self.review.edited.connect(self._sync_actions)
        self.review.rename_scope_changed.connect(self.set_rename_scope)
        self.review.from_scratch.connect(lambda: self.analyze(self.folder, "full", self.last_include_kept))
        self.review.include_kept.connect(lambda: self.analyze(self.folder, self.last_mode, True))
        self.done.show_folder.connect(lambda: reveal(self.folder))
        self.done.undo.connect(lambda: self.undo(self.folder))
        self.done.done.connect(self.close_folder)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(190)
        self.sidebar.setMaximumWidth(300)
        sl = QVBoxLayout(self.sidebar)
        sl.setContentsMargins(6, 4, 6, 6)
        sl.addWidget(label("RECENT FOLDERS", "SidebarTitle"))
        self.recent_list = QListWidget()
        self.recent_list.itemClicked.connect(lambda item: self.analyze(item.data(Qt.UserRole)))
        self.recent_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(self._recent_menu)
        sl.addWidget(self.recent_list)
        self.recent_empty = label("Folders you analyze appear here.", "Small", wrap=True)
        self.recent_empty.setAlignment(Qt.AlignCenter)
        sl.addWidget(self.recent_empty)

        split = QSplitter()
        split.addWidget(self.sidebar)
        split.addWidget(self.pages)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 1020])
        split.setHandleWidth(1)
        self.setCentralWidget(split)

        self._toolbar()
        self._menus()
        self.refresh_recents()
        self.show_empty()
        self.load_models()

    # ---- chrome --------------------------------------------------------------------------

    def _toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        choose = QPushButton("📂  Choose Folder")
        choose.setToolTip("Choose a folder to organize (Ctrl+O)")
        choose.clicked.connect(self.choose_folder)
        tb.addWidget(choose)
        self.again_btn = QPushButton("⟳  Analyze Again")
        self.again_btn.setToolTip("Analyze this folder again (Ctrl+R)")
        self.again_btn.clicked.connect(lambda: self.folder and self.analyze(self.folder))
        tb.addWidget(self.again_btn)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addWidget(label("Naming model", "Muted"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(240)
        self.model_combo.setToolTip("The language model that names folders and files. Applies to the next analysis.")
        self.model_combo.activated.connect(self._model_chosen)
        tb.addWidget(self.model_combo)
        gear = QPushButton("⚙  Settings")
        gear.setToolTip("Settings (Ctrl+,)")
        gear.clicked.connect(self.open_settings)
        tb.addWidget(gear)

    def _menus(self):
        def act(menu, text, slot, shortcut=None, checkable=False):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setCheckable(checkable)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        bar = self.menuBar()
        f = bar.addMenu("&File")
        act(f, "Choose Folder…", self.choose_folder, "Ctrl+O")
        self.act_again = act(f, "Analyze Again", lambda: self.folder and self.analyze(self.folder), "Ctrl+R")
        f.addSeparator()
        act(f, "Settings…", self.open_settings, "Ctrl+,")
        f.addSeparator()
        act(f, "Quit", self.close, "Ctrl+Q")
        e = bar.addMenu("&Edit")
        self.act_undo = act(e, "Undo Organize", lambda: self.undo(self.folder), "Ctrl+Z")
        v = bar.addMenu("&View")
        self.act_blocks = act(v, "Files as Blocks", lambda: self._set_style("blocks"), "Ctrl+1", True)
        self.act_list = act(v, "Files as List", lambda: self._set_style("list"), "Ctrl+2", True)
        p = bar.addMenu("&Plan")
        self.plan_actions = [
            act(p, "Select All Files", self._select_all, "Ctrl+Shift+A"),
            act(p, "Leave All in Place", self._select_none, "Ctrl+Shift+D"),
        ]
        p.addSeparator()
        self.act_suggested = act(p, "Use Suggested Names", self._toggle_suggested, "Ctrl+Shift+N", True)
        self.act_scratch = act(p, "Plan from Scratch", lambda: self.analyze(self.folder, "full"))
        self.act_revert = act(p, "Revert Changes", self._revert)
        self.plan_actions += [self.act_suggested, self.act_scratch, self.act_revert]
        organize = QAction("Organize", self)
        organize.setShortcuts([QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        organize.triggered.connect(lambda: self.pages.currentWidget() is self.review and self.organize())
        self.addAction(organize)
        self._sync_actions()

    def _sync_actions(self):
        reviewing = self.pages.currentWidget() is self.review and self.plan is not None
        for a in self.plan_actions:
            a.setEnabled(reviewing)
        if reviewing:
            self.act_suggested.setChecked(self.plan.use_suggested)
            self.act_scratch.setEnabled(self.plan.is_update)
            self.act_revert.setEnabled(self.plan.has_edits())
        self.act_undo.setEnabled(self.pages.currentWidget() is self.done)
        busy = self.pages.currentWidget() in (self.analyzing, self.busy)
        self.act_again.setEnabled(bool(self.folder) and not busy)
        self.again_btn.setVisible(self.pages.currentWidget() is self.review)
        style_name = settings.get("planStyle")
        self.act_blocks.setChecked(style_name == "blocks")
        self.act_list.setChecked(style_name == "list")
        self.setWindowTitle(f"SmartSort — {Path(self.folder).name}" if self.folder else "SmartSort")

    def show_page(self, page):
        self.pages.setCurrentWidget(page)
        self._sync_actions()

    # ---- models ---------------------------------------------------------------------------

    def load_models(self):
        """Ask the engine which models it can find (fast: nothing is loaded)."""
        run = EngineRun(["models"], self)
        run.event.connect(self._models_event)
        run.finished.connect(lambda _msg: self._fill_model_combo())
        self._models_run = run
        run.start()

    def _models_event(self, data: dict):
        if data.get("event") == "models":
            self.catalog = data

    def rescan_sync(self) -> dict | None:
        cmd = engine_command()
        if not cmd:
            return None
        try:
            out = subprocess.run(cmd + ["api", "models"], capture_output=True, text=True, timeout=60,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            self.catalog = json.loads(out.strip().splitlines()[-1])
        except Exception:
            return self.catalog
        self._fill_model_combo()
        return self.catalog

    def _fill_model_combo(self):
        c = self.model_combo
        c.blockSignals(True)
        c.clear()
        default = (self.catalog or {}).get("defaultNaming")
        c.addItem(f"Automatic ({model_label(default)})" if default else "Automatic", "")
        for m in (self.catalog or {}).get("models") or []:
            if m["supported"]:
                c.addItem(f"{m['name']}  ·  {model_detail(m)}", m["path"])
        c.insertSeparator(c.count())
        c.addItem("Off — name with EmbeddingGemma only", "\0off")
        if not settings.get("useNamingModel"):
            c.setCurrentIndex(c.count() - 1)
        else:
            saved = settings.get("namingModelPath")
            i = c.findData(saved)
            if i < 0 and saved:
                c.insertItem(1, f"Other: {model_label(saved)}", saved)
                i = 1
            c.setCurrentIndex(max(i, 0))
        c.blockSignals(False)
        self._check_setup()

    def _model_chosen(self, index: int):
        data = self.model_combo.itemData(index)
        if data == "\0off":
            settings.put("useNamingModel", False)
        else:
            settings.put("useNamingModel", True)
            settings.put("namingModelPath", data or "")

    def _check_setup(self):
        """A note on the start screen when something still needs setting up."""
        if engine_command() is None:
            self.empty.set_note("⚠️ SmartSort’s engine wasn’t found. Run setup.ps1 from the README, "
                                "or set it in Settings › Engine.")
        elif self.catalog is not None and not self.catalog.get("defaultEmbedding") \
                and not settings.get("embeddingModelPath"):
            self.empty.set_note("⚠️ EmbeddingGemma 2 wasn’t found. Download it once with "
                                "“hf download google/embeddinggemma-2”, or choose its folder in Settings › Models.")
        else:
            self.empty.set_note(None)

    def open_settings(self):
        SettingsDialog(self.catalog, self.rescan_sync, self).exec()
        self._fill_model_combo()

    # ---- recents --------------------------------------------------------------------------

    def refresh_recents(self):
        paths = [p for p in settings.get("recentFolders") if Path(p).is_dir()]
        self.recent_list.clear()
        for p in paths:
            item = QListWidgetItem("📁  " + (Path(p).name or p))
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            self.recent_list.addItem(item)
        self.recent_empty.setVisible(not paths)
        self.empty.set_recents(paths)

    def remember(self, folder: str):
        paths = [p for p in settings.get("recentFolders") if p != folder]
        settings.put("recentFolders", [folder] + paths[:7])
        self.refresh_recents()

    def _recent_menu(self, pos):
        item = self.recent_list.itemAt(pos)
        if not item:
            return
        path = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Analyze", lambda: self.analyze(path))
        menu.addAction("Show in Folder", lambda: reveal(path))
        if has_undo(path):
            menu.addSeparator()
            menu.addAction("Undo Last Organize", lambda: self.undo(path))
        menu.addSeparator()
        menu.addAction("Remove from Recents", lambda: (
            settings.put("recentFolders", [p for p in settings.get("recentFolders") if p != path]),
            self.refresh_recents()))
        menu.exec(self.recent_list.mapToGlobal(pos))

    # ---- drag and drop --------------------------------------------------------------------

    def dragEnterEvent(self, e):
        urls = e.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).is_dir() and not self._busy():
            e.acceptProposedAction()
            self.empty.set_drop_active(True)

    def dragLeaveEvent(self, e):
        self.empty.set_drop_active(False)

    def dropEvent(self, e):
        self.empty.set_drop_active(False)
        path = e.mimeData().urls()[0].toLocalFile()
        if Path(path).is_dir():
            self.analyze(path)

    # ---- the flow -------------------------------------------------------------------------

    def _busy(self) -> bool:
        return self.pages.currentWidget() in (self.analyzing, self.busy)

    def show_empty(self, message: str | None = None):
        self.empty.set_message(message)
        self.show_page(self.empty)

    def choose_folder(self):
        if self._busy():
            return
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to organize")
        if path:
            self.analyze(path)

    def analyze(self, folder: str | None, mode: str = "auto", include_kept: bool = False):
        if not folder or self._busy():
            return
        if not Path(folder).is_dir():
            self.fail(f"“{Path(folder).name}” isn’t a folder.")
            return
        self.folder = str(Path(folder))
        self.plan = None
        self.last_mode, self.last_include_kept = mode, include_kept
        self.remember(self.folder)
        args = ["analyze", self.folder, "--rename", settings.get("renameMode"),
                "--max-read-mb", str(settings.get("maxReadMB")), "--mode", mode]
        if include_kept:
            args.append("--include-kept")
        if settings.get("embeddingModelPath"):
            args += ["--model", settings.get("embeddingModelPath")]
        if not settings.get("useNamingModel"):
            args.append("--no-namer")
        elif settings.get("namingModelPath"):
            args += ["--namer", settings.get("namingModelPath")]
        self.analyzing.start(Path(self.folder).name)
        self.show_page(self.analyzing)
        self._start(args, self._analyze_event, self._analyze_finished)

    def _start(self, args, on_event, on_finished):
        if self.run is not None:
            self.run.cancel()
        self.run = EngineRun(args, self)
        self.run.event.connect(on_event)
        self.run.finished.connect(on_finished)
        self.run.start()

    def _analyze_event(self, data: dict):
        kind = data.get("event")
        if kind == "progress":
            self.analyzing.update_stage(data.get("stage", ""), data.get("done", 0), data.get("total", 0))
        elif kind == "result":
            self.plan = Plan(data)
            self.review.set_plan(self.plan)
            self.show_page(self.review)
        elif kind == "error" and data.get("code") == "nothing-new":
            self.show_up_to_date(data.get("message", ""), data.get("keptCount", 0))
        elif kind == "error":
            self.fail(data.get("message", "Something went wrong."), settings_hint=data.get("code") == "no-embedding-model")

    def _analyze_finished(self, error: str):
        if error:
            self.fail(error, settings_hint=engine_command() is None)
        elif self.pages.currentWidget() is self.analyzing:
            self.fail("The analysis finished without a result.")

    def cancel(self):
        if self.run:
            self.run.cancel()
        self.show_empty()

    def set_rename_scope(self, scope: str):
        if scope != settings.get("renameMode"):
            settings.put("renameMode", scope)
            self.analyze(self.folder, self.last_mode, self.last_include_kept)

    def organize(self):
        if not self.plan or not self.plan.moving():
            return
        payload = self.plan.payload()
        self.renamed_count = self.plan.rename_count()
        file = Path(tempfile.gettempdir()) / f"smartsort-{uuid.uuid4().hex}.json"
        file.write_text(json.dumps(payload))
        n = len(payload["moves"])
        self.busy.set_text(f"Organizing {n} file{'s' if n != 1 else ''}…")
        self.show_page(self.busy)
        result = {}

        def on_event(data):
            result.update(data)

        def on_finished(error):
            file.unlink(missing_ok=True)
            if error or result.get("event") == "error":
                self.fail(error or result.get("message", "The files couldn’t be moved."))
                return
            self.done.show_result(Path(self.folder).name, result.get("moved", 0), self.renamed_count,
                                  result.get("problems", []))
            self.show_page(self.done)

        self._start(["apply", self.folder, str(file)], on_event, on_finished)

    def undo(self, folder: str | None):
        if not folder:
            return
        self.busy.set_text("Putting files back…")
        self.show_page(self.busy)
        result = {}

        def on_finished(error):
            if error or result.get("event") == "error":
                self.fail(error or result.get("message", "SmartSort couldn’t undo."))
                return
            self.folder = folder
            n = result.get("restored", 0)
            self.show_empty(f"Moved {n} file{'s' if n != 1 else ''} back to “{Path(folder).name}”.")

        self._start(["undo", folder], result.update, on_finished)

    def close_folder(self):
        self.folder, self.plan = None, None
        self.show_empty()

    def show_up_to_date(self, message: str, kept: int):
        self.uptodate.set_message(message)
        buttons = []
        if kept:
            b = button(f"Sort the {'File' if kept == 1 else f'{kept} Files'} Left in Place", primary=True)
            b.clicked.connect(lambda: self.analyze(self.folder, self.last_mode, True))
            buttons.append(b)
        b = button("Show in Folder")
        b.clicked.connect(lambda: reveal(self.folder))
        buttons.append(b)
        b = button("Choose Another Folder…")
        b.clicked.connect(self.choose_folder)
        buttons.append(b)
        self.uptodate.set_buttons(buttons)
        self.show_page(self.uptodate)

    def fail(self, message: str, settings_hint: bool = False):
        self.failed.set_message(message)
        buttons = []
        if self.folder:
            b = button("Try Again", primary=True)
            b.clicked.connect(lambda: self.analyze(self.folder))
            buttons.append(b)
        if settings_hint:
            b = button("Open Settings…")
            b.clicked.connect(self.open_settings)
            buttons.append(b)
        b = button("Choose Another Folder…")
        b.clicked.connect(self.choose_folder)
        buttons.append(b)
        self.failed.set_buttons(buttons)
        self.show_page(self.failed)

    # ---- plan menu ------------------------------------------------------------------------

    def _set_style(self, key: str):
        settings.put("planStyle", key)
        if self.plan:
            self.review.rebuild()
        self._sync_actions()

    def _select_all(self):
        self.plan.select_all()
        self.review.rebuild()

    def _select_none(self):
        self.plan.select_none()
        self.review.rebuild()

    def _toggle_suggested(self):
        self.plan.use_suggested = not self.plan.use_suggested
        self.review.rebuild()
        self._sync_actions()

    def _revert(self):
        self.plan.revert()
        self.review.rebuild()
        self._sync_actions()

    def closeEvent(self, e):
        if self.run:
            self.run.cancel()
        super().closeEvent(e)


def main() -> int:
    if sys.platform == "win32":  # own taskbar icon instead of Python's
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SmartSort.SmartSort")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("SmartSort")
    app.setOrganizationName("SmartSort")
    icon = Path(__file__).with_name("icon.png")
    if icon.exists():
        from PySide6.QtGui import QIcon

        app.setWindowIcon(QIcon(str(icon)))
    style.apply(app)
    window = MainWindow()
    window.show()
    return app.exec()
