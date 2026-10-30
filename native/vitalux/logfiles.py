"""Bounded local logs, retaining one backup and open native crash descriptors."""
import fcntl
import os
from pathlib import Path
import shutil
import tempfile

MAX_BYTES = 5 * 1024 * 1024


def append(path, record, limit=MAX_BYTES):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.encode('utf-8') if isinstance(record, str) else record
    if path.is_symlink() or path.with_name(path.name+'.1').is_symlink():
        raise OSError('Refusing a symlinked log')
    lock = os.open(str(path)+'.lock', os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with path.open('a+b') as stream:
            size = os.fstat(stream.fileno()).st_size
            if size and size + len(data) > limit:
                fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
                try:
                    with os.fdopen(fd, 'wb') as backup:
                        stream.seek(0)
                        shutil.copyfileobj(stream, backup)
                    os.replace(temporary, str(path)+'.1')
                    # faulthandler keeps its descriptor until process exit.
                    # Keep this inode so a later native trace reaches the log.
                    stream.truncate(0)
                finally:
                    if os.path.exists(temporary):os.unlink(temporary)
            stream.write(data)
            stream.flush()
    finally:
        os.close(lock)


def tail(path, limit=64 * 1024):
    """Read a bounded tail, excluding a potentially partial first record."""
    try:
        with Path(path).open('rb') as stream:
            size = os.fstat(stream.fileno()).st_size
            stream.seek(max(0, size-limit))
            if size > limit:stream.readline()
            return stream.read(limit).decode('utf-8', errors='replace')
    except OSError:
        return ''
