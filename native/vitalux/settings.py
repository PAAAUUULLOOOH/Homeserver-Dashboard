"""Atomic, cached per-user preferences. Reads follow external file changes."""
import copy
import json
import os
import tempfile
import warnings

from . import profiles

PATH = str(profiles.directory('config')/'settings.json')
_cache_identity = None
_cache_value = None


def _identity():
    try:
        info = os.stat(PATH)
        return (PATH, info.st_mtime_ns, info.st_size, info.st_ino)
    except OSError:
        return (PATH, None, None, None)


def _snapshot():
    global _cache_identity, _cache_value
    identity = _identity()
    if identity == _cache_identity and _cache_value is not None:
        return _cache_value
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
            data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    _cache_identity, _cache_value = identity, data
    return data


def _load():
    """A caller-owned complete snapshot (used for atomic preference writes)."""
    return copy.deepcopy(_snapshot())


def get(key, default=None):
    return copy.deepcopy(_snapshot().get(key, default))


def observed(key, default=None):
    """Read the latest observed snapshot in paint paths, without filesystem I/O.

    Normal getters still detect external edits immediately. GUI changes update
    this snapshot atomically; regular sample/settings reads discover external
    changes without thousands of stat calls in an animation frame.
    """
    if _cache_value is None or not _cache_identity or _cache_identity[0]!=PATH:
        return get(key,default)
    value=_cache_value.get(key,default)
    return value if type(value) in (str,int,float,bool,type(None)) else copy.deepcopy(value)


def migrate_crystal_designs():
    from . import design_catalog
    before=_load();after=design_catalog.migrate(before)
    changes={key:value for key,value in after.items() if before.get(key)!=value}
    return set_many(changes) if changes else True


def get_many(defaults):
    """Read several settings using just one snapshot of the settings file."""
    if not isinstance(defaults, dict):
        raise TypeError("Preferences defaults must be a dictionary")
    data = _snapshot()
    return copy.deepcopy({key: data.get(key, default) for key, default in defaults.items()})


def _report_write_error(exc):
    message = f"Vitalux konnte die Einstellungen nicht speichern: {exc}"
    warnings.warn(message, RuntimeWarning, stacklevel=2)
    try:
        # Error dialogs are allowed on the Qt GUI thread only.
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import QThread
        app = QApplication.instance()
        if app is not None and QThread.currentThread() == app.thread():
            QMessageBox.warning(app.activeWindow(), "Vitalux – Einstellungen", message)
    except (ImportError, RuntimeError):
        pass


def set(key, value):
    """Update one preference using the shared atomic writer."""
    return set_many({key: value})


def set_many(changes):
    """Save multiple preferences with one fsync/replace and one cache update.

    A no-op update skips disk writes only if a preferences file already exists.
    The caller-owned values are copied so later mutation cannot alter the cache.
    """
    global _cache_identity, _cache_value
    if not isinstance(changes, dict):
        raise TypeError("Preferences changes must be a dictionary")
    if not changes:
        return True
    data = _load()
    if os.path.isfile(PATH) and all(key in data and data[key] == value
                                    for key, value in changes.items()):
        return True
    data.update(copy.deepcopy(changes))
    temporary = None
    try:
        parent = os.path.dirname(PATH)
        os.makedirs(parent, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=parent)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, PATH)
        temporary = None
        _cache_identity, _cache_value = _identity(), copy.deepcopy(data)
        return True
    except OSError as exc:
        _report_write_error(exc)
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass

