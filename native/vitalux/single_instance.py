"""A per-user, process-lifetime lock shared by every Vitalux package/channel."""
import errno
import fcntl
import json
import os
import stat
import time
from pathlib import Path


class InstanceGuard:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else Path('/tmp') / f'vitalux-{os.getuid()}'
        self._fd = None
        self.restarting = False

    def acquire(self, wait=.2, restart_wait=5.):
        if self._fd is not None:
            return True
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError('Unsafe Vitalux instance-lock directory')
        fd = os.open(self.directory / 'instance.lock', os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise PermissionError('Unsafe Vitalux instance-lock file')
            deadline=time.monotonic()+wait
            extended=False
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):raise
                    try:
                        state=json.loads(os.pread(fd,1024,0))
                        self.restarting=(state.get('phase')=='restarting'
                                         and 0<=time.monotonic()-state.get('at',0)<15)
                    except (ValueError,TypeError,AttributeError):self.restarting=False
                    if self.restarting and not extended:
                        deadline=max(deadline,time.monotonic()+restart_wait);extended=True
                    remaining=deadline-time.monotonic()
                    if remaining<=0:return False
                    time.sleep(min(.025,remaining))
            self._fd, fd = fd, None
            self.restarting=False
            self._state('running')
            return True
        finally:
            if fd is not None:
                os.close(fd)

    def _state(self,phase):
        data=json.dumps({'pid':os.getpid(),'phase':phase,'at':time.monotonic()}).encode()
        os.pwrite(self._fd,data,0);os.ftruncate(self._fd,len(data))

    def mark_restarting(self):
        if self._fd is not None:self._state('restarting')

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        # Never unlink: waiting starters must all lock the same inode.


def already_running(restarting=False):
    """Show a localized notice without initializing a profile or GPU backend."""
    from PySide6.QtWidgets import QApplication, QMessageBox
    from . import APP_NAME, i18n, settings
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    i18n.set_lang(settings.get('lang') or ('de' if os.environ.get('LANG', '').lower().startswith('de') else 'en'))
    message='Vitalux wird gerade neu gestartet. Bitte einen Moment warten.' if restarting else 'Vitalux läuft bereits.'
    QMessageBox.information(None, APP_NAME, i18n.tr(message))
    return 0
