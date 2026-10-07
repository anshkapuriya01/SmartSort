"""The review screen: one section per destination folder, files as blocks or as a list.
Clicking a file includes it or leaves it in place; nothing moves until Organize."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImage, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileIconProvider,
                               QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout, QLineEdit, QMenu,
                               QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget)

from . import settings, style
from .engine import open_file, reveal
from .plan import Choice, Group, Plan

RENAME_SCOPES = [("junk", "Unhelpful names only"), ("all", "All documents"), ("none", "Never")]
TILE_W, TILE_H = 176, 212
THUMB = QSize(132, 96)


# ---------------------------------------------------------------------------------------
# Small helpers

def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def check_pixmap(selected: bool, tint: str, size: int = 22) -> QPixmap:
    """A round check mark: filled with the folder's color when selected, an empty ring when not."""
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRect(2, 2, size - 4, size - 4)
    if selected:
        p.setBrush(QColor(tint))
        p.setPen(Qt.NoPen)
        p.drawEllipse(r)
        pen = QPen(QColor("white"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        s = size
        p.drawPolyline([QPoint(int(s * 0.30), int(s * 0.52)), QPoint(int(s * 0.44), int(s * 0.66)),
                        QPoint(int(s * 0.71), int(s * 0.36))])
    else:
        p.setBrush(QColor(style.colors()["card"]))
        p.setPen(QPen(QColor(style.colors()["muted"]), 1.6))
        p.drawEllipse(r)
    p.end()
    return pm


def group_check_pixmap(group: Group, tint: str) -> QPixmap:
    if group.selected_count == len(group.files):
        return check_pixmap(True, tint)
    if group.selected_count == 0:
        return check_pixmap(False, tint)
    pm = check_pixmap(True, tint)  # partly selected: a dash
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(tint))
    p.drawEllipse(QRect(2, 2, 18, 18))
    p.setPen(QPen(QColor("white"), 2.2, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(7, 11, 15, 11)
    p.end()
    return pm


def elide(text: str, font: QFont, width: int, mode=Qt.ElideMiddle) -> str:
    return QFontMetrics(font).elidedText(text, mode, width)


def two_lines(text: str, font: QFont, width: int) -> str:
    """Wrap a file name onto at most two lines, cutting the middle of the second if needed
    (so the extension stays visible)."""
    fm = QFontMetrics(font)
    if fm.horizontalAdvance(text) <= width:
        return text
    cut = len(text)
    while cut > 1 and fm.horizontalAdvance(text[:cut]) > width:
        cut -= 1
    space = text.rfind(" ", 0, cut + 1)
    if space > cut // 2:  # break at a word when there's one in the second half
        cut = space + 1
    return text[:cut].rstrip() + "\n" + fm.elidedText(text[cut:].lstrip(), Qt.ElideMiddle, width)


def why_text(c: Choice) -> str:
    lines = [f"{c.move['name']}  →  {c.destination.replace('/', ' › ')}"]
    if c.move.get("why"):
        lines.append(c.move["why"][:1].upper() + c.move["why"][1:])
    lines.append("Click to organize this file." if c.is_kept else "Click to leave it where it is.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------
# Thumbnails: the file's real content (photo, first page of a PDF), loaded off the UI thread

class _ThumbSignals(QObject):
    done = Signal(str, QImage)


class _ThumbJob(QRunnable):
    def __init__(self, path: str, signals: _ThumbSignals):
        super().__init__()
        self.path, self.signals = path, signals

    def run(self):
        image = QImage()
        ext = Path(self.path).suffix.lower()
        try:
            if ext == ".pdf":
                import pymupdf as fitz

                with fitz.open(self.path) as doc:
                    if doc.page_count:
                        page = doc[0]
                        zoom = THUMB.height() * 2 / max(page.rect.height, 1)
                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                        image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                                       QImage.Format_RGB888 if pix.n == 3 else QImage.Format_RGBA8888).copy()
            elif ext in {".heic", ".heif"}:
                from PIL import Image
                from pillow_heif import register_heif_opener

                register_heif_opener()
                with Image.open(self.path) as im:
                    im.thumbnail((THUMB.width() * 2, THUMB.height() * 2))
                    im = im.convert("RGBA")
                    image = QImage(im.tobytes(), im.width, im.height, QImage.Format_RGBA8888).copy()
            else:
                reader = QImageReader(self.path)
                if reader.canRead():
                    size = reader.size()
                    if size.isValid():
                        reader.setScaledSize(size.scaled(THUMB * 2, Qt.KeepAspectRatio))
                    image = reader.read()
        except Exception:
            image = QImage()
        self.signals.done.emit(self.path, image)


class Thumbnails(QObject):
    ready = Signal(str)

    def __init__(self):
        super().__init__()
        self.cache: dict[str, QPixmap] = {}
        self.pending: set[str] = set()
        self.icons = QFileIconProvider()
        self.signals = _ThumbSignals()
        self.signals.done.connect(self._done)
        self.pool = QThreadPool.globalInstance()

    def get(self, path: str) -> QPixmap | None:
        if path in self.cache:
            return self.cache[path]
        ext = Path(path).suffix.lower()
        if ext in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif"} \
                and path not in self.pending:
            self.pending.add(path)
            self.pool.start(_ThumbJob(path, self.signals))
        return None

    def icon(self, path: str, size: int) -> QPixmap:
        from PySide6.QtCore import QFileInfo

        return self.icons.icon(QFileInfo(path)).pixmap(size, size)

    def _done(self, path: str, image: QImage):
        self.pending.discard(path)
        if not image.isNull():
            self.cache[path] = QPixmap.fromImage(image)
            self.ready.emit(path)


THUMBS: Thumbnails | None = None


def thumbs() -> Thumbnails:
    global THUMBS
    if THUMBS is None:
        THUMBS = Thumbnails()
    return THUMBS


# ---------------------------------------------------------------------------------------
# Flow layout: blocks wrap to the window width

class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 12):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _layout(self, rect: QRect, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            w, h = item.sizeHint().width(), item.sizeHint().height()
            if x + w > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self._spacing, 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += w + self._spacing
            line = max(line, h)
        return y + line - rect.y()


# ---------------------------------------------------------------------------------------
# Rename dialog

class RenameDialog(QDialog):
    def __init__(self, choice: Choice, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename File")
        self.choice = choice
        self.result_action = None  # "custom", "suggested", "original"
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        name = choice.file_name.rsplit(".", 1)[0] if "." in choice.file_name else choice.file_name
        ext = choice.move["name"].rsplit(".", 1)[1] if "." in choice.move["name"] else ""
        row = QHBoxLayout()
        self.edit = QLineEdit(name)
        self.edit.setMinimumWidth(320)
        self.edit.selectAll()
        row.addWidget(self.edit)
        if ext:
            row.addWidget(label("." + ext, "Muted"))
        lay.addLayout(row)
        info = f"Was: {choice.move['name']}"
        if choice.suggested_name and choice.suggested_name != choice.file_name:
            info += f"\nSuggested: {choice.suggested_name}"
        lay.addWidget(label(info, "Small"))
        buttons = QDialogButtonBox()
        if choice.suggested_name and choice.file_name != choice.suggested_name:
            b = buttons.addButton("Use Suggestion", QDialogButtonBox.ActionRole)
            b.clicked.connect(lambda: self._finish("suggested"))
        if choice.is_renamed:
            b = buttons.addButton("Keep Original", QDialogButtonBox.ActionRole)
            b.clicked.connect(lambda: self._finish("original"))
        buttons.addButton(QDialogButtonBox.Cancel)
        ok = buttons.addButton("Rename", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        ok.setDefault(True)
        buttons.rejected.connect(self.reject)
        ok.clicked.connect(lambda: self._finish("custom"))
        lay.addWidget(buttons)

    def _finish(self, action: str):
        self.result_action = action
        self.accept()


# ---------------------------------------------------------------------------------------
# A file: block or row

class FileItem(QFrame):
    """Shared behaviour of a block and a row: click to include or leave, hover buttons,
    right-click menu, tooltip."""

    def __init__(self, review: "ReviewView", choice: Choice, tint: str):
        super().__init__()
        self.review, self.choice, self.tint = review, choice, tint
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(why_text(choice))
        self.setAttribute(Qt.WA_Hover, True)
        self.setProperty("hover", False)
        self.buttons = QWidget()
        bl = QHBoxLayout(self.buttons)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(2)
        for text, tip, slot in (("✎", "Rename", self.rename), ("👁", "Open", lambda: open_file(choice.id))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCursor(Qt.ArrowCursor)
            b.clicked.connect(slot)
            bl.addWidget(b)
        self.buttons.setVisible(False)
        if choice.is_kept:
            fx = QGraphicsOpacityEffect(self)
            fx.setOpacity(0.5)
            self.setGraphicsEffect(fx)

    def enterEvent(self, e):
        self.review.hovered = self.choice.id
        self.buttons.setVisible(True)
        self.setProperty("hover", True)
        self.style().polish(self)

    def leaveEvent(self, e):
        if self.review.hovered == self.choice.id:
            self.review.hovered = None
        self.buttons.setVisible(False)
        self.setProperty("hover", False)
        self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.review.plan.toggle(self.choice)
            self.review.changed()

    def mouseDoubleClickEvent(self, e):
        open_file(self.choice.id)

    def contextMenuEvent(self, e):
        c, plan = self.choice, self.review.plan
        menu = QMenu(self)
        menu.addAction("Organize This File" if c.is_kept else "Leave in Place",
                       lambda: (plan.toggle(c), self.review.changed()))
        menu.addAction("Rename…", self.rename)
        if c.suggested_name:
            using = c.file_name == c.suggested_name
            menu.addAction("Keep Original Name" if using else "Use Suggested Name",
                           lambda: (plan.set_keeps_name(c, using), self.review.changed()))
        move = menu.addMenu("Move To")
        for path in plan.all_folders():
            act = move.addAction(path.replace("/", " › "), lambda p=path: (plan.move_to(c, p), self.review.changed()))
            act.setEnabled(path != c.folder)
        menu.addSeparator()
        menu.addAction("Open", lambda: open_file(c.id))
        menu.addAction("Show in Folder", lambda: reveal(c.id))
        menu.exec(e.globalPos())

    def rename(self):
        dlg = RenameDialog(self.choice, self)
        if dlg.exec() != QDialog.Accepted:
            return
        plan, c = self.review.plan, self.choice
        if dlg.result_action == "custom":
            plan.set_custom_name(c, dlg.edit.text())
        elif dlg.result_action == "suggested":
            plan.set_keeps_name(c, False)
        elif dlg.result_action == "original":
            plan.set_keeps_name(c, True)
        self.review.changed()

    def subtitle(self) -> str:
        c = self.choice
        if c.is_kept:
            return "Stays in place"
        if c.is_renamed:
            return "was " + c.move["name"]
        if c.move.get("duplicateOf"):
            return "Copy of " + c.move["duplicateOf"]
        return c.move.get("kind") or ""


class FileBlock(FileItem):
    def __init__(self, review, choice, tint):
        super().__init__(review, choice, tint)
        self.setObjectName("Tile")
        self.setFixedSize(TILE_W, TILE_H)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        top = QHBoxLayout()
        self.check = QLabel()
        self.check.setPixmap(check_pixmap(not choice.is_kept, tint))
        top.addWidget(self.check, 0, Qt.AlignTop)
        top.addStretch()
        top.addWidget(self.buttons, 0, Qt.AlignTop)
        lay.addLayout(top)
        self.thumb = QLabel()
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedHeight(THUMB.height())
        lay.addWidget(self.thumb)
        name = label(choice.file_name)
        name.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        f = name.font()
        f.setWeight(QFont.DemiBold)
        name.setFont(f)
        name.setText(two_lines(choice.file_name, f, TILE_W - 24))
        name.setFixedHeight(QFontMetrics(f).lineSpacing() * 2 + 2)
        lay.addWidget(name)
        sub = label(elide(self.subtitle(), name.font(), TILE_W - 24), "Small")
        sub.setAlignment(Qt.AlignHCenter)
        if choice.is_renamed and not choice.is_kept:
            sf = sub.font()
            sf.setStrikeOut(True)
            sub.setFont(sf)
            sub.setText(elide(choice.move["name"], sf, TILE_W - 24))
        lay.addWidget(sub)
        self.show_thumbnail()

    def show_thumbnail(self):
        pm = thumbs().get(self.choice.id)
        if pm is None:
            self.thumb.setPixmap(thumbs().icon(self.choice.id, 64))
        else:
            self.thumb.setPixmap(pm.scaled(THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.choice.is_kept:  # a colored edge marks the files that will be organized
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(style.qcolor(self.tint, 150), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
            p.end()


class FileRow(FileItem):
    def __init__(self, review, choice, tint):
        super().__init__(review, choice, tint)
        self.setObjectName("Row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)
        check = QLabel()
        check.setPixmap(check_pixmap(not choice.is_kept, tint, 20))
        lay.addWidget(check)
        icon = QLabel()
        icon.setPixmap(thumbs().icon(choice.id, 24))
        lay.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(label(choice.file_name))
        sub = self.subtitle()
        if sub:
            text.addWidget(label(sub, "Small"))
        lay.addLayout(text, 1)
        lay.addWidget(self.buttons)

    def show_thumbnail(self):
        pass


# ---------------------------------------------------------------------------------------
# A destination folder

class FolderHeader(QFrame):
    def __init__(self, review: "ReviewView", group: Group, tint: str):
        super().__init__()
        self.review, self.group = review, group
        self.setObjectName("Card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        toggle = QToolButton()
        toggle.setIcon(QIcon(group_check_pixmap(group, tint)))
        toggle.setIconSize(QSize(22, 22))
        toggle.setToolTip("Leave all of these in place" if group.selected_count == len(group.files)
                          else "Organize all of these")
        toggle.clicked.connect(lambda: (review.plan.toggle_group(group), review.changed()))
        lay.addWidget(toggle)
        text = QVBoxLayout()
        text.setSpacing(0)
        title = QHBoxLayout()
        title.setSpacing(4)
        if group.parent:
            title.addWidget(label(group.parent.replace("/", " › ") + " ›", "Muted"))
        self.name = label(group.name, "Heading")
        title.addWidget(self.name)
        self.editor = QLineEdit(group.name)
        self.editor.setVisible(False)
        self.editor.returnPressed.connect(self.commit)
        self.editor.editingFinished.connect(self.commit)
        title.addWidget(self.editor)
        title.addStretch()
        text.addLayout(title)
        n = len(group.files)
        text.addWidget(label(f"{group.selected_count} of {n} file{'s' if n != 1 else ''}", "Small"))
        lay.addLayout(text, 1)
        if group.is_existing:
            badge = label("✓ Existing folder", "Badge")
            badge.setStyleSheet(f"color: {style.EXISTING}; background: {style.qcolor(style.EXISTING, 30).name(QColor.HexArgb)};")
            lay.addWidget(badge)
        elif not group.is_special:
            badge = label("+ New folder", "Badge")
            badge.setStyleSheet(f"color: {style.NEW}; background: {style.qcolor(style.NEW, 30).name(QColor.HexArgb)};")
            lay.addWidget(badge)
        if review.plan.can_rename_folder(group):
            b = QToolButton()
            b.setText("✎")
            b.setToolTip("Rename this folder")
            b.clicked.connect(self.start_editing)
            lay.addWidget(b)

    def mouseDoubleClickEvent(self, e):
        self.start_editing()

    def start_editing(self):
        if not self.review.plan.can_rename_folder(self.group):
            return
        self.name.setVisible(False)
        self.editor.setVisible(True)
        self.editor.setFocus()
        self.editor.selectAll()

    def commit(self):
        if not self.editor.isVisible():
            return
        self.editor.setVisible(False)
        self.name.setVisible(True)
        self.review.plan.rename_folder(self.group.path, self.editor.text())
        self.review.changed()


# ---------------------------------------------------------------------------------------
# The whole screen

class ReviewView(QWidget):
    organize = Signal()
    rename_scope_changed = Signal(str)
    from_scratch = Signal()
    include_kept = Signal()
    edited = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Page")
        self.plan: Plan | None = None
        self.hovered: str | None = None
        self.blocks: dict[str, FileBlock] = {}
        thumbs().ready.connect(self._thumb_ready)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll, 1)

        bar_holder = QWidget()
        bar_holder.setObjectName("Page")
        hl = QHBoxLayout(bar_holder)
        hl.setContentsMargins(24, 10, 24, 16)
        self.bar = QFrame()
        self.bar.setObjectName("ActionBar")
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(18, 10, 12, 10)
        bl.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.selected_label = label("", "Heading")
        self.summary_label = label("", "Small")
        texts.addWidget(self.selected_label)
        texts.addWidget(self.summary_label)
        bl.addLayout(texts)
        for text, tip, slot in (("All", "Select every file", self._all), ("None", "Leave every file in place", self._none),
                                ("Revert", "Undo your changes to this plan", self._revert)):
            b = QPushButton(text)
            b.setObjectName("Link")
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bl.addWidget(b)
            setattr(self, f"btn_{text.lower()}", b)
        bl.addStretch()
        self.organize_btn = QPushButton("Organize")
        self.organize_btn.setObjectName("Primary")
        self.organize_btn.setProperty("class", "Big")
        self.organize_btn.setMinimumHeight(38)
        self.organize_btn.setToolTip("Move and rename the selected files (Ctrl+Enter). You can undo this afterwards.")
        self.organize_btn.clicked.connect(lambda: self.organize.emit())
        bl.addWidget(self.organize_btn)
        hl.addWidget(self.bar)
        outer.addWidget(bar_holder)

    # ---- building ----------------------------------------------------------------------

    def set_plan(self, plan: Plan):
        self.plan = plan
        self.rebuild(keep_scroll=False)

    def changed(self):
        self.rebuild()

    def rebuild(self, keep_scroll: bool = True):
        if self.plan is None:
            return
        pos = self.scroll.verticalScrollBar().value() if keep_scroll else 0
        body = QWidget()
        body.setObjectName("ScrollBody")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(18)
        lay.addWidget(self._header())
        style_name = settings.get("planStyle")
        self.blocks = {}
        for group in self.plan.groups():
            tint = style.tint_for(group.path, group.is_existing)
            section = QVBoxLayout()
            section.setSpacing(10)
            section.addWidget(FolderHeader(self, group, tint))
            if style_name == "list":
                card = QFrame()
                card.setObjectName("Card")
                cl = QVBoxLayout(card)
                cl.setContentsMargins(4, 4, 4, 4)
                cl.setSpacing(0)
                for f in group.files:
                    cl.addWidget(FileRow(self, f, tint))
                section.addWidget(card)
            else:
                holder = QWidget()
                flow = FlowLayout(holder, 12)
                for f in group.files:
                    block = FileBlock(self, f, tint)
                    self.blocks[f.id] = block
                    flow.addWidget(block)
                section.addWidget(holder)
            lay.addLayout(section)
        lay.addStretch()
        self.scroll.setWidget(body)
        self.scroll.verticalScrollBar().setValue(pos)
        self._update_bar()
        self.edited.emit()

    def _header(self) -> QWidget:
        plan = self.plan
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        if plan.is_update:
            card = QFrame()
            card.setObjectName("Card")
            card.setStyleSheet(f"#Card {{ border-color: {style.EXISTING}; }}")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            n = len(plan.choices())
            text = QVBoxLayout()
            text.addWidget(label(f"✨  {n} new file{'s' if n != 1 else ''} since you last organized", "Heading"))
            text.addWidget(label("Only these are sorted. They go into your existing folders when they fit, "
                                 "and into new folders when they don’t.", "Muted", wrap=True))
            cl.addLayout(text, 1)
            b = QPushButton("Plan from Scratch")
            b.setToolTip("Ignore the folders made last time and plan all loose files again")
            b.clicked.connect(lambda: self.from_scratch.emit())
            cl.addWidget(b)
            lay.addWidget(card)
        kept = plan.result.get("keptFiles") or []
        if kept:
            card = QFrame()
            card.setObjectName("Card")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 8, 16, 8)
            msg = (f"📌  “{kept[0]}” stays in place, as you chose last time." if len(kept) == 1
                   else f"📌  {len(kept)} files you left in place last time stay where they are.")
            t = label(msg, "Muted")
            t.setToolTip("\n".join(kept))
            cl.addWidget(t, 1)
            b = QPushButton("Include It" if len(kept) == 1 else "Include Them")
            b.clicked.connect(lambda: self.include_kept.emit())
            cl.addWidget(b)
            lay.addWidget(card)

        controls = QHBoxLayout()
        controls.setSpacing(16)
        controls.addWidget(label("Organize by", "Muted"))
        group = QButtonGroup(box)
        seg = QHBoxLayout()
        seg.setSpacing(2)
        for s in plan.schemes:
            b = QToolButton()
            b.setText(s["title"])
            b.setToolTip(s["example"])
            b.setCheckable(True)
            b.setChecked(s["key"] == plan.scheme_key)
            b.clicked.connect(lambda _=False, k=s["key"]: self._set_scheme(k))
            group.addButton(b)
            seg.addWidget(b)
        controls.addLayout(seg)
        controls.addSpacing(12)

        rename = QCheckBox("Rename files")
        rename.setChecked(plan.use_suggested)
        rename.setEnabled(settings.get("renameMode") != "none")
        rename.setToolTip("Use the names SmartSort suggests from each file’s content. "
                          "You can also click ✎ on any file to type your own.")
        rename.toggled.connect(self._set_use_suggested)
        controls.addWidget(rename)
        scope = QComboBox()
        for key, title in RENAME_SCOPES:
            scope.addItem(title, key)
        scope.setCurrentIndex([k for k, _ in RENAME_SCOPES].index(settings.get("renameMode")))
        scope.setToolTip("Which files get a suggested name. Changing this analyzes again.")
        scope.currentIndexChanged.connect(lambda i: self.rename_scope_changed.emit(RENAME_SCOPES[i][0]))
        controls.addWidget(scope)
        if plan.suggestion_count():
            controls.addWidget(label(f"{plan.suggestion_count()} suggested", "Small"))
        controls.addStretch()

        view = QButtonGroup(box)
        for key, title, tip in (("blocks", "▦  Blocks", "Show files as blocks (Ctrl+1)"),
                                ("list", "☰  List", "Show files as a list (Ctrl+2)")):
            b = QToolButton()
            b.setText(title)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setChecked(settings.get("planStyle") == key)
            b.clicked.connect(lambda _=False, k=key: self.set_style(k))
            view.addButton(b)
            controls.addWidget(b)
        lay.addLayout(controls)
        return box

    # ---- actions -----------------------------------------------------------------------

    def set_style(self, key: str):
        settings.put("planStyle", key)
        self.rebuild()

    def _set_scheme(self, key: str):
        self.plan.scheme_key = key
        self.rebuild(keep_scroll=False)

    def _set_use_suggested(self, on: bool):
        self.plan.use_suggested = on
        self.rebuild()

    def _all(self):
        self.plan.select_all()
        self.rebuild()

    def _none(self):
        self.plan.select_none()
        self.rebuild()

    def _revert(self):
        self.plan.revert()
        self.rebuild()

    def _update_bar(self):
        plan = self.plan
        moving, total = len(plan.moving()), len(plan.choices())
        self.selected_label.setText(f"{moving} of {total} files selected")
        if moving:
            folders, renamed = plan.folder_count(), plan.rename_count()
            self.summary_label.setText(f"Into {folders} folder{'s' if folders != 1 else ''}"
                                       + (f" · {renamed} renamed" if renamed else "") + " · undo any time")
        else:
            self.summary_label.setText("Click files to choose what to organize")
        self.organize_btn.setText(f"Organize {moving} File{'s' if moving != 1 else ''}   (Ctrl+Enter)")
        self.organize_btn.setEnabled(moving > 0)
        self.btn_all.setEnabled(moving < total)
        self.btn_none.setEnabled(moving > 0)
        self.btn_revert.setVisible(plan.has_edits())

    def _thumb_ready(self, path: str):
        block = self.blocks.get(path)
        if block is not None:
            try:
                block.show_thumbnail()
            except RuntimeError:  # the block was rebuilt meanwhile
                pass
