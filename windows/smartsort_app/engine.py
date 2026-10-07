"""Runs the SmartSort engine (`smartsort api …`) in the background and reads its JSON lines.

By default the engine is the `smartsort` package installed next to this app (same Python), so
there's nothing to set up. Settings can point at another `smartsort` command instead.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from . import settings


def engine_command() -> list[str] | None:
    """The command that starts the engine, or None when it can't be found."""
    custom = settings.get("enginePath", "")
    if custom:
        return [custom] if Path(custom).exists() else None
    try:
        import smartsort  # noqa: F401  installed in this Python: the usual case
        return [sys.executable, "-m", "smartsort.cli"]
    except ImportError:
        pass
    found = shutil.which("smartsort")
    return [found] if found else None


def log_path() -> Path:
    return Path(tempfile.gettempdir()) / "smartsort-engine.log"


class EngineRun(QObject):
    """One run of the engine. Emits each JSON line as a dict, then `finished` (an error
    message, or "" when it ended cleanly)."""

    event = Signal(dict)
    finished = Signal(str)

    def __init__(self, args: list[str], parent=None):
        super().__init__(parent)
        self._buffer = b""
        self._saw_error = False
        self._cancelled = False
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("TOKENIZERS_PARALLELISM", "false")
        self.proc.setProcessEnvironment(env)
        self.proc.setStandardErrorFile(str(log_path()))
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._failed_to_start)
        command = engine_command()
        if command is None:
            self._command = None
            self._args = []
        else:
            self._command, self._args = command[0], command[1:] + ["api"] + args

    def start(self):
        if self._command is None:
            self.finished.emit("SmartSort’s engine wasn’t found. Run setup.ps1 from the README, "
                               "or set the engine in Settings › Engine.")
            return
        self.proc.start(self._command, self._args)

    def cancel(self):
        self._cancelled = True
        if self.proc.state() != QProcess.NotRunning:
            self.proc.kill()

    def _read(self):
        self._buffer += bytes(self.proc.readAllStandardOutput())
        *lines, self._buffer = self._buffer.split(b"\n")
        for raw in lines:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if data.get("event") == "error":
                self._saw_error = True
            self.event.emit(data)

    def _done(self, code, status):
        self._read()
        if self._cancelled:
            return
        if code != 0 and not self._saw_error:
            try:
                last = log_path().read_text(errors="replace").strip().splitlines()[-1]
            except (OSError, IndexError):
                last = "Unknown error"
            self.finished.emit(f"The engine stopped unexpectedly. {last}")
        else:
            self.finished.emit("")

    def _failed_to_start(self, error):
        if error == QProcess.FailedToStart and not self._cancelled:
            self.finished.emit(f"Couldn’t start the engine ({self._command}).")


def open_file(path: str):
    """Open with the default app."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        QProcess.startDetached("open", [path])
    else:
        QProcess.startDetached("xdg-open", [path])


def reveal(path: str):
    """Show in Explorer / Finder / the file manager."""
    if sys.platform == "win32":
        QProcess.startDetached("explorer", ["/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        QProcess.startDetached("open", ["-R", path])
    else:
        target = path if os.path.isdir(path) else os.path.dirname(path)
        QProcess.startDetached("xdg-open", [target])
