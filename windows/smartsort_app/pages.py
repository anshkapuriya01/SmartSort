"""The screens around the review: start, analyzing, busy, done, up to date and failed."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from .review import label

STAGES = ["Reading files", "Waking up the model", "Reading documents", "Classifying documents",
          "Looking at images", "Matching your folders", "Naming folders and files", "Planning layouts"]
STEPS = ["Reading files", "Understanding content", "Naming folders and files", "Planning layouts"]


def fit_height(lab: QLabel) -> None:
    """Wrapped text inside centered layouts doesn't grow on its own: give it its exact height."""
    lab.setFixedHeight(max(lab.heightForWidth(lab.width()), lab.fontMetrics().lineSpacing()))


def centered(*widgets, spacing: int = 14) -> QWidget:
    page = QWidget()
    page.setObjectName("Page")
    outer = QVBoxLayout(page)
    outer.addStretch(1)
    column = QVBoxLayout()
    column.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, QWidget):
            column.addWidget(w, 0, Qt.AlignHCenter)
        else:
            column.addLayout(w)
    outer.addLayout(column)
    outer.addStretch(1)
    return page


def big_icon(text: str, color: str | None = None, size: int = 44) -> QLabel:
    w = QLabel(text)
    w.setAlignment(Qt.AlignCenter)
    w.setStyleSheet(f"font-size: {size}pt;" + (f" color: {color};" if color else ""))
    return w


def button(text: str, primary: bool = False, big: bool = False) -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setObjectName("Primary")
    if big:
        b.setMinimumHeight(42)
        b.setStyleSheet("font-size: 12pt; padding: 8px 24px;")
    return b


def row(*widgets) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(10)
    lay.addStretch()
    for w in widgets:
        lay.addWidget(w)
    lay.addStretch()
    return lay


class EmptyPage(QWidget):
    """One obvious thing to do: give SmartSort a folder."""

    choose = Signal()
    open_recent = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.addStretch(1)
        self.zone = QFrame()
        self.zone.setObjectName("DropZone")
        self.zone.setProperty("active", False)
        self.zone.setFixedWidth(600)  # wrapped text needs a known width to measure its height
        zl = QVBoxLayout(self.zone)
        zl.setContentsMargins(48, 40, 48, 40)
        zl.setSpacing(12)
        self.icon = big_icon("📂", size=48)
        zl.addWidget(self.icon)
        self.title = label("Organize a Folder", "Title")
        self.title.setAlignment(Qt.AlignCenter)
        zl.addWidget(self.title)
        self.message = label("SmartSort reads your files on this computer and suggests folders and clearer names. "
                             "Nothing changes until you click Organize.", "Subtitle", wrap=True)
        self.message.setAlignment(Qt.AlignCenter)
        zl.addWidget(self.message)
        b = button("Choose Folder…", primary=True, big=True)
        b.clicked.connect(lambda: self.choose.emit())
        zl.addLayout(row(b))
        hint = label("or drag a folder here  ·  Ctrl+O choose  ·  Ctrl+, settings", "Small")
        hint.setAlignment(Qt.AlignCenter)
        zl.addWidget(hint)
        outer.addWidget(self.zone, 0, Qt.AlignHCenter)
        self.recents = QHBoxLayout()
        self.recents.setSpacing(8)
        outer.addSpacing(16)
        outer.addLayout(self.recents)
        outer.addStretch(1)
        self.note = label("", "Muted", wrap=True)
        self.note.setAlignment(Qt.AlignCenter)
        self.note.setVisible(False)
        outer.addWidget(self.note)

    def set_recents(self, paths: list[str]):
        while self.recents.count():
            item = self.recents.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not paths:
            return
        self.recents.addStretch()
        self.recents.addWidget(label("Recent", "Muted"))
        from pathlib import Path

        for p in paths[:4]:
            b = QPushButton("📁  " + (Path(p).name or p))
            b.setToolTip(p)
            b.clicked.connect(lambda _=False, path=p: self.open_recent.emit(path))
            self.recents.addWidget(b)
        self.recents.addStretch()

    def set_drop_active(self, active: bool):
        self.zone.setProperty("active", active)
        self.zone.style().polish(self.zone)
        self.title.setText("Drop to Analyze" if active else "Organize a Folder")
        self.icon.setText("⬇️" if active else "📂")

    def set_message(self, text: str | None):
        self.message.setText(text or "SmartSort reads your files on this computer and suggests folders and clearer "
                                     "names. Nothing changes until you click Organize.")

    def set_note(self, text: str | None):
        self.note.setText(text or "")
        self.note.setVisible(bool(text))


class AnalyzingPage(QWidget):
    cancel = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Page")
        self.title = label("Analyzing", "Title")
        self.title.setAlignment(Qt.AlignCenter)
        self.detail = label("", "Muted")
        self.detail.setAlignment(Qt.AlignCenter)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(340)
        steps = QFrame()
        steps.setObjectName("Card")
        steps.setFixedWidth(340)
        sl = QVBoxLayout(steps)
        sl.setContentsMargins(18, 14, 18, 14)
        self.step_labels = []
        for s in STEPS:
            lab = label("○  " + s)
            sl.addWidget(lab)
            self.step_labels.append(lab)
        cancel = button("Cancel")
        cancel.clicked.connect(lambda: self.cancel.emit())
        lay = QVBoxLayout(self)
        page = centered(big_icon("🔍"), self.title, self.detail, self.bar, steps, cancel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(page)
        self.progress = 0.0

    def start(self, folder_name: str):
        self.title.setText(f"Analyzing “{folder_name}”")
        self.progress = 0.0
        self.update_stage(STAGES[0], 0, 0)

    def update_stage(self, stage: str, done: int, total: int):
        if stage not in STAGES:
            return
        index = STAGES.index(stage)
        within = done / total if total else 0
        self.progress = max(self.progress, min(1.0, (index + within) / len(STAGES)))
        self.bar.setValue(int(self.progress * 1000))
        self.detail.setText(f"{stage} — {done} of {total}" if total > 1 else stage)
        current = 0 if index == 0 else 1 if index <= 5 else 2 if index == 6 else 3
        for i, (lab, name) in enumerate(zip(self.step_labels, STEPS, strict=False)):
            if i < current:
                lab.setText("✅  " + name)
                lab.setStyleSheet("")
            elif i == current:
                lab.setText("⏳  " + name)
                lab.setStyleSheet("font-weight: 600;")
            else:
                lab.setText("○  " + name)
                lab.setStyleSheet("color: gray;")


class BusyPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Page")
        self.text = label("", "Heading")
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setFixedWidth(260)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(centered(self.text, bar))

    def set_text(self, text: str):
        self.text.setText(text)


class DonePage(QWidget):
    show_folder = Signal()
    undo = Signal()
    done = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Page")
        self.summary = label("", "Subtitle", wrap=True)
        self.summary.setAlignment(Qt.AlignCenter)
        self.summary.setFixedWidth(460)
        self.moved = label("", "Title")
        self.renamed = label("", "Title")
        stats = QHBoxLayout()
        stats.setSpacing(14)
        stats.addStretch()
        for value, caption in ((self.moved, "moved"), (self.renamed, "renamed")):
            card = QFrame()
            card.setObjectName("Card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(24, 12, 24, 12)
            value.setAlignment(Qt.AlignCenter)
            cl.addWidget(value)
            cap = label(caption, "Muted")
            cap.setAlignment(Qt.AlignCenter)
            cl.addWidget(cap)
            stats.addWidget(card)
        stats.addStretch()
        b1, b2, b3 = button("Show in Folder", primary=True), button("Undo"), button("Done")
        b1.clicked.connect(lambda: self.show_folder.emit())
        b2.clicked.connect(lambda: self.undo.emit())
        b3.clicked.connect(lambda: self.done.emit())
        self.problems = label("", "Small", wrap=True)
        self.problems.setFixedWidth(460)
        self.problems.setAlignment(Qt.AlignCenter)
        title = label("All Tidy", "Title")
        title.setAlignment(Qt.AlignCenter)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(centered(big_icon("✅", size=48), title, self.summary, stats, row(b1, b2, b3), self.problems))

    def show_result(self, folder: str, moved: int, renamed: int, problems: list[str]):
        self.summary.setText(f"“{folder}” is organized. Add new files any time and analyze again: "
                             "only the new ones are sorted.")
        fit_height(self.summary)
        self.moved.setText(str(moved))
        self.renamed.setText(str(renamed))
        self.problems.setText("\n".join(problems))
        fit_height(self.problems)
        self.problems.setVisible(bool(problems))


class MessagePage(QWidget):
    """Up to date, or failed: an icon, a title, a message and a few buttons."""

    def __init__(self, icon: str, title: str):
        super().__init__()
        self.setObjectName("Page")
        self.message = label("", "Subtitle", wrap=True)
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setFixedWidth(500)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.title = label(title, "Title")
        self.title.setAlignment(Qt.AlignCenter)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(10)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(centered(big_icon(icon), self.title, self.message, self.buttons))

    def set_message(self, text: str):
        self.message.setText(text)
        fit_height(self.message)

    def set_buttons(self, buttons: list[QPushButton]):
        while self.buttons.count():
            item = self.buttons.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.buttons.addStretch()
        for b in buttons:
            self.buttons.addWidget(b)
        self.buttons.addStretch()
