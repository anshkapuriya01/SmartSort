"""The person's settings (Windows: the registry; macOS/Linux: a preferences file)."""

from __future__ import annotations

from PySide6.QtCore import QSettings

DEFAULTS = {
    "renameMode": "junk",        # junk | all | none
    "maxReadMB": 50,
    "embeddingModelPath": "",    # empty: found automatically
    "namingModelPath": "",       # empty: found automatically
    "useNamingModel": True,
    "enginePath": "",            # empty: the smartsort package next to this app
    "planStyle": "blocks",       # blocks | list
    "recentFolders": [],
}


def _store() -> QSettings:
    return QSettings("SmartSort", "SmartSort")


def get(key: str, default=None):
    fallback = DEFAULTS.get(key) if default is None else default
    value = _store().value(key, fallback)
    if isinstance(fallback, bool):  # QSettings returns "true"/"false" strings on some systems
        return value in (True, "true", "1", 1)
    if isinstance(fallback, int) and not isinstance(fallback, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
    if isinstance(fallback, list):
        if value is None:
            return []
        return [value] if isinstance(value, str) else list(value)
    return value


def put(key: str, value) -> None:
    _store().setValue(key, value)
