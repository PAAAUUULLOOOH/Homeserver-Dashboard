"""Vitalux release updates via GitHub: ZIP installation or atomic AppImage replacement."""
import json
import hashlib
import shlex
import subprocess
import time
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
import ssl
import socket
from pathlib import PurePosixPath,Path
import stat

from . import APP_NAME, APP_ID, __version__, settings, profiles, versions
from .i18n import tr

DEFAULT_REPO = "PAAAUUULLOOOH/Vitalux"  # Feste, offizielle Updatequelle; keine frei eingebbaren URLs.
HEADERS = {"User-Agent": f"{APP_NAME}-Updater", "Accept": "application/vnd.github+json"}
SKIP = {".venv", ".libs", ".backup", f"{APP_ID}.log", f"{APP_ID}.log.old", ".qtcheck", "__pycache__", ".git"}


def app_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ver(v):
    return versions.key(v)


# The bundled Python/OpenSSL runtime may use Debian's CA path on non-Debian
# systems (e.g. openSUSE). Trust the host's actual CA bundle, never disable TLS.
CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",       # Debian, Ubuntu, Arch, Fedora
    "/etc/ssl/ca-bundle.pem",                  # openSUSE
    "/var/lib/ca-certificates/ca-bundle.pem", # openSUSE
    "/etc/pki/trust/extracted/pem/tls-ca-bundle.pem", # Fedora/openSUSE
    "/etc/pki/tls/certs/ca-bundle.crt",       # RHEL
    "/etc/ssl/cert.pem",                     # Other Linux systems
)


def _tls_context():
    """Load a valid OS trust store for the embedded Python interpreter."""
    # Honor the user's explicit override when it names a real certificate file.
    explicit = os.environ.get("SSL_CERT_FILE")
    paths = (explicit,) + CA_BUNDLES if explicit else CA_BUNDLES
    for path in paths:
        if path and os.path.isfile(path):
            try:
                return ssl.create_default_context(cafile=path)
            except (OSError, ssl.SSLError):
                continue
    # Allows OpenSSL to use a CA directory (and respects SSL_CERT_DIR).
    return ssl.create_default_context()


def _github_request(request, timeout):
    return urllib.request.urlopen(request, timeout=timeout, context=_tls_context())


def _get_release():
    req = urllib.request.Request(
        f"https://api.github.com/repos/{DEFAULT_REPO}/releases/latest", headers=HEADERS)
    with _github_request(req, timeout=12) as response:
        return json.load(response)


def _get_unstable_release():
    request=urllib.request.Request(f'https://api.github.com/repos/{DEFAULT_REPO}/releases/tags/unstable',headers=HEADERS)
    with _github_request(request,timeout=12) as response:return json.load(response)


def _unstable_manifest(data):
    item=next((a for a in data.get('assets',[]) if a.get('name')=='Vitalux-unstable-channel.json'),None)
    if not item:raise ValueError('Testpaket wird noch vorbereitet.')
    url=f'https://github.com/{DEFAULT_REPO}/releases/download/unstable/Vitalux-unstable-channel.json'
    digest=str(item.get('digest',''))
    if item.get('browser_download_url')!=url or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):raise ValueError('Ungültiges Testkanal-Manifest.')
    with _github_request(urllib.request.Request(url,headers=HEADERS),timeout=12) as response:raw=response.read(65537)
    if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=digest.split(':')[1].lower():raise ValueError('Testkanal-Manifest konnte nicht geprüft werden.')
    manifest=json.loads(raw)
    if not isinstance(manifest,dict) or manifest.get('schema')!=1:raise ValueError('Ungültiges Testkanal-Manifest.')
    # Legacy version identifies the last covered test for older installations.
    if versions.channel(manifest.get('version'))!='unstable':raise ValueError('Ungültige Testversionsnummer.')
    return manifest


def check(channel=None, stable_result=None):
    """Only releases from the official GitHub repo with the exact app binary."""
    repo = DEFAULT_REPO
    channel=channel or profiles.selected()
    if channel not in ('stable','unstable'):return {'ok':False,'error':tr('Unbekannter Update-Kanal.')}
    manifest=None
    try:
        data = _get_release() if channel=='stable' else _get_unstable_release()
        if not isinstance(data,dict):raise ValueError('Invalid release response')
        if channel=='unstable':
            if data.get('tag_name')!='unstable' or data.get('prerelease') is not True:raise ValueError('Invalid test release')
            manifest=_unstable_manifest(data)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "missing":True, "error": tr('Noch kein Unstable-Testpaket veröffentlicht.' if channel=='unstable' else "Noch keine Vitalux-Version über GitHub Releases veröffentlicht.")}
        return {"ok": False, "error": f"GitHub: HTTP {e.code}"}
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLCertVerificationError):
            message = tr('GitHub-Zertifikat konnte nicht geprüft werden. Bitte Systemzeit und CA-Zertifikate prüfen. Details: {reason}').format(reason=reason)
        elif isinstance(reason, socket.gaierror):
            message = tr('GitHub-DNS-Auflösung fehlgeschlagen: {reason}').format(reason=reason)
        else:
            message = tr('GitHub ist nicht erreichbar: {reason}').format(reason=reason)
        return {"ok": False, "error": str(message)[:320]}
    except (ValueError, TypeError):
        return {"ok": False, "error": tr("Unerwartete Antwort von GitHub.")}

    tag = str(data.get("tag_name", ""))
    version=str(manifest.get('baseline_version') or manifest['version']) if manifest and manifest.get('has_test_changes') is False else str(manifest['version']) if manifest else tag.lstrip('v')
    try:valid=((versions.channel(version)==channel or bool(manifest and manifest.get('has_test_changes') is False and version==manifest.get('stable_version'))) and (tag=='unstable' if manifest else not data.get('prerelease',False)))
    except ValueError:valid=False
    if not valid:
        return {"ok": False, "error": tr("Ungültige Versionsangabe bei GitHub.")}
    is_appimage = bool(os.environ.get("APPIMAGE"))
    notes=(data.get('body') or '').strip()
    common={'ok':True,'latest':version,'notes':notes,'url':'','sha256':'',
            'kind':'appimage' if is_appimage else 'zip','newer':False,
            'channel':channel,'eligible':channel=='stable'}
    if channel=='unstable':
        stable_result=stable_result if stable_result is not None else check('stable')
        baseline=manifest.get('stable_version','')
        stable_version=stable_result.get('latest','') if stable_result.get('ok') else ''
        try:
            eligible=(manifest.get('has_test_changes') is True and baseline==stable_version
                      and versions.channel(baseline)=='stable' and _ver(version)>_ver(stable_version))
        except ValueError:eligible=False
        common.update(covered_test_version=manifest['version'],manifest_verified=True,stable_contains_test=manifest.get('stable_contains_test') is True and baseline==stable_version,release_notes=notes,eligible=eligible,stable_version=stable_version or baseline,
                      has_test_changes=manifest.get('has_test_changes') is True,
                      stable_verified=bool(stable_result.get('ok')),same_as_stable=manifest.get('same_as_stable') is True and baseline==stable_version)
        if not eligible:
            # Metadata without a verified Stable baseline never enables a switch.
            # Retain the real Stable notes instead of advertising a mirrored build.
            common.update(notes=stable_result.get('notes','') if stable_result.get('ok') else notes,
                          reason='no_newer_test')
            return common
    # Current releases still provide their notes for channel browsing.
    switching=versions.channel(__version__)!=channel
    if not switching and _ver(version) <= _ver(__version__):
        return common
    # Neuer Standardname ohne „Portabel“; ältere Releases bleiben kompatibel.
    suffixes = ("-x86_64.AppImage",) if is_appimage else (
        "-linux-x86_64.zip", "-linux-x86_64-Portabel.zip")
    expected_names = [f"Vitalux-v{version}{suffix}" for suffix in suffixes]
    item = next((a for name in expected_names for a in data.get("assets", [])
                 if a.get("name") == name), None)
    expected_name = str(item.get("name", "")) if item else expected_names[0]
    if not item:
        # When a release was just published, the AppImage may still be building.
        return {"ok": False, "error":
                tr("Das offizielle Vitalux-Update wird auf GitHub noch erstellt oder ist nicht verfügbar.")}
    download_url = str(item.get('browser_download_url', ''))
    expected_url = f"https://github.com/{repo}/releases/download/{tag}/{expected_name}"
    if download_url != expected_url:
        return {"ok": False, "error": tr("Ungültige Adresse der Vitalux-Release-Datei.")}
    checksum = str(item.get('digest') or '')
    if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', checksum):
        return {"ok": False, "error": tr('GitHub Release liefert keine SHA-256-Prüfsumme für die Programmdatei.')}
    if manifest:
        record=manifest.get('assets',{}).get(expected_name,{})
        if record.get('sha256')!=checksum.split(':',1)[1].lower():
            return {'ok':False,'error':tr('Testpaket und Manifest stimmen nicht überein. Bitte erneut prüfen.')}
    common.update(url=download_url,sha256=checksum.split(':',1)[1].lower(),
                  bytes=manifest['assets'][expected_name].get('bytes') if manifest else item.get('size'),
                  newer=switching or _ver(version)>_ver(__version__))
    return common


def catalog():
    """One consistent Stable baseline and both channels, including current notes."""
    stable=check('stable')
    unstable=check('unstable',stable_result=stable)
    if unstable.get('missing') and stable.get('ok'):
        unstable=dict(ok=True,latest='',notes=stable.get('notes',''),url='',sha256='',newer=False,
                      eligible=False,channel='unstable',stable_version=stable['latest'],reason='no_test_package')
    return {'stable':stable,'unstable':unstable}



def _require_space(path, required):
    if shutil.disk_usage(path).free < required+16*1024*1024:
        raise RuntimeError(tr('Für das Update ist nicht genügend freier Speicherplatz vorhanden.'))


def _directory_bytes(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(folder, name))
               for folder, _dirs, files in os.walk(path) for name in files
               if not os.path.islink(os.path.join(folder, name)))


def _download_verified(url, output_path, sha256, progress, download_limit, expected_size=None):
    """Stream to disk with size cap and SHA-256 check (digest taken from GitHub Releases API)."""
    if not re.fullmatch('[0-9a-fA-F]{64}', sha256 or ''):
        raise RuntimeError(tr('SHA-256-Prüfsumme fehlt. Update aus Sicherheitsgründen abgebrochen.'))
    digest = hashlib.sha256()
    length = 0
    request = urllib.request.Request(url, headers={'User-Agent': HEADERS['User-Agent']})
    progress(0.)
    last_report = time.monotonic()
    with _github_request(request, timeout=15) as response, open(output_path, 'wb') as f:
        if response.geturl().split(':', 1)[0] != 'https':
            raise RuntimeError(tr('Update-Download ohne HTTPS abgebrochen.'))
        declared = int(response.headers.get('Content-Length') or '0')
        known = expected_size if type(expected_size) is int and expected_size > 0 else 0
        if known and declared and known != declared:
            raise RuntimeError(tr('Der Update-Download wurde unterbrochen. Bitte erneut versuchen.'))
        total = declared or known
        if total > download_limit:
            raise RuntimeError(tr('Updatepaket überschreitet Größenlimit.'))
        _require_space(os.path.dirname(os.path.abspath(output_path)), total)
        # HTTPResponse.read(n) waits for n bytes and can make a slow transfer
        # appear frozen. read1 returns the available data within one socket read.
        read = getattr(response, 'read1', response.read)
        while True:
            chunk = read(64 * 1024)
            if not chunk:
                break
            length += len(chunk)
            if length > download_limit:
                raise RuntimeError(tr('Updatepaket überschreitet Größenlimit.'))
            f.write(chunk)
            digest.update(chunk)
            now = time.monotonic()
            if now-last_report >= .1 or (total and length >= total):
                progress(min(80., 80.*length/total) if total else 0.)
                last_report = now
        f.flush()
        os.fsync(f.fileno())
    if total and length != total:
        raise RuntimeError(tr('Der Update-Download wurde unterbrochen. Bitte erneut versuchen.'))
    progress(80.)
    if digest.hexdigest() != sha256.lower():
        raise RuntimeError(tr('Sicherheitsprüfung fehlgeschlagen: SHA-256 stimmt nicht überein.'))


def appimage_path():
    return os.environ.get('APPIMAGE') or ''


def _stage_appimage(url, sha256, progress, expected_size=None):
    target = os.path.realpath(appimage_path())
    if not target or not os.path.isfile(target):
        raise RuntimeError(tr('Vitalux ist nicht als AppImage gestartet.'))
    folder = os.path.dirname(target)
    if not os.access(folder, os.W_OK):
        raise RuntimeError(tr('AppImage liegt in einem schreibgeschützten Ordner. Bitte Vitalux im Benutzerordner installieren.'))
    fd, staged = tempfile.mkstemp(prefix='.vitalux-next-', suffix='.AppImage', dir=folder)
    os.close(fd)
    try:
        _download_verified(url, staged, sha256, progress, 900 * 1024 * 1024, expected_size=expected_size)
        with open(staged, 'rb') as f:
            head = f.read(11)
        if not head.startswith(b'\x7fELF') or head[8:11] != b'AI\x02':
            raise RuntimeError(tr('Heruntergeladene Datei ist kein gültiges AppImage vom Typ 2.'))
        os.chmod(staged, 0o755)
        progress(95.)
        return staged
    except Exception:
        os.unlink(staged)
        raise


def _appimage_mailbox(target):
    request=os.environ.get('VITALUX_APPIMAGE_REQUEST_FILE','')
    guarded_target=os.environ.get('VITALUX_APPIMAGE_TARGET','')
    if not request or not guarded_target or os.path.realpath(guarded_target)!=target:return None
    import stat
    path=Path(request);info=path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid():
        raise RuntimeError('Unsafe AppImage activation mailbox')
    return path


def queue_appimage_restart():
    """Let the current AppRun restart this same image after an intentional close."""
    image=appimage_path()
    if not image:return False
    target=os.path.realpath(image);path=_appimage_mailbox(target)
    if path is None:return False
    profiles.atomic_json(path,dict(schema=1,action='restart',source_version=__version__,
                                  source_pid=os.getpid(),target=target))
    return True


def activate_appimage_update(staged, relaunch=True):
    """Queue activation for AppRun, retaining a helper for older unguarded starts."""
    target = os.path.realpath(appimage_path())
    if not os.path.isfile(target) or os.path.dirname(staged) != os.path.dirname(target):
        raise RuntimeError(tr('AppImage-Update konnte nicht sicher vorbereitet werden.'))
    path=_appimage_mailbox(target)
    if path is not None:
        # AppRun applies this one-use request after the GUI and launcher exit.
        candidate=Path(staged)
        if candidate.is_symlink():raise RuntimeError('Unsafe staged AppImage')
        with candidate.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        profiles.atomic_json(path,dict(schema=1,source_version=__version__,source_pid=os.getpid(),
            target=target,staged=str(candidate.resolve()),sha256=digest,relaunch=bool(relaunch)))
        return
    cache = str(profiles.directory('cache'))
    os.makedirs(cache, mode=0o700, exist_ok=True)
    logging_functions = (Path(__file__).resolve().parents[1]/'packaging/logging.sh').read_text()
    fd, script = tempfile.mkstemp(prefix='apply-update-', suffix='.sh', dir=cache)
    q = shlex.quote
    # The current process must exit before the AppImage is switched and reopened.
    script_text = f"""#!/bin/bash
set -eu
{logging_functions}
oldpid={os.getpid()}
target={q(target)}
staged={q(staged)}
backup={q(target + '.previous')}
state_dir={q(str(profiles.directory('state')))}
version={q(__version__)}
mkdir -p "$state_dir"
stamp() {{
  vitalux_log_line "$state_dir/restart.log" "$version" "$*"
}}
for i in $(seq 1 150); do
  if ! kill -0 "$oldpid" 2>/dev/null; then break; fi
  sleep 0.2
done
if kill -0 "$oldpid" 2>/dev/null; then exit 1; fi
if [ ! -f "$staged" ] || [ ! -f "$target" ]; then exit 1; fi
cp -p -- "$target" "${{backup}}.tmp"
mv -f -- "${{backup}}.tmp" "$backup"
mv -f -- "$staged" "$target"
unset APPDIR APPIMAGE LD_LIBRARY_PATH LD_PRELOAD PYTHONHOME PYTHONPATH PYTHONUSERBASE
stamp "Vitalux update activation: old version v$version, launching newly installed AppImage."
# Record even early loader failures in restart.log, with date and source version.
if [ {q('yes' if relaunch else 'no')} = yes ]; then
  ( "$target" --launch 2>&1 | while IFS= read -r line || [ -n "$line" ]; do
      stamp "$line"
    done ) &
fi
"""
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(script_text)
        os.chmod(script, 0o700)
        subprocess.Popen(['/bin/bash', script], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        try: os.unlink(script)
        except OSError: pass
        raise





def _find_root(extracted):
    for dirpath, _dirs, files in os.walk(extracted):
        if "run.sh" in files and os.path.isfile(os.path.join(dirpath, APP_ID, "__main__.py")):
            return dirpath
    return None


def backup_available(root=None):
    root = root or app_root()
    backup = os.path.join(root, '.backup')
    return (os.path.isfile(os.path.join(backup, APP_ID, '__main__.py')) and
            os.path.isfile(os.path.join(backup, 'metadata.json')))


def _stage_backup(root, root_files):
    """Prepare complete previous application + launcher + settings snapshot.

    The previous .backup remains valid until a new snapshot is fully built.
    """
    backup = os.path.join(root, '.backup')
    stage = tempfile.mkdtemp(prefix='.vitalux-backup-stage-', dir=root)
    try:
        shutil.copytree(os.path.join(root, APP_ID), os.path.join(stage, APP_ID),
                        ignore=shutil.ignore_patterns('__pycache__'))
        filesdir = os.path.join(stage, 'root_files')
        os.makedirs(filesdir, exist_ok=True)
        for name in root_files:
            original = os.path.join(root, name)
            if os.path.isfile(original):
                shutil.copy2(original, os.path.join(filesdir, name))
            elif os.path.isdir(original) and not os.path.islink(original):
                shutil.copytree(original, os.path.join(filesdir, name),
                                ignore=shutil.ignore_patterns('__pycache__'))
        if os.path.isfile(settings.PATH):
            shutil.copy2(settings.PATH, os.path.join(stage, 'settings.json'))
        with open(os.path.join(stage, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': __version__, 'root_files': list(root_files),
                       'profile_channel':profiles.installed() if os.path.abspath(settings.PATH)==str(profiles.directory('config')/'settings.json') else None,
                       'settings_saved': os.path.isfile(os.path.join(stage, 'settings.json'))}, f)
        old = backup + '.old'
        shutil.rmtree(old, ignore_errors=True)
        if os.path.exists(backup):
            os.replace(backup, old)
        os.replace(stage, backup)
        stage = None
        shutil.rmtree(old, ignore_errors=True)
    finally:
        if stage and os.path.exists(stage):
            shutil.rmtree(stage, ignore_errors=True)


def _install_from_directory(src, root, progress):
    root = os.path.abspath(root)
    pkg = os.path.join(root, APP_ID)
    if not os.path.isdir(pkg):
        raise RuntimeError(tr('Bestehende Vitalux-Installation nicht gefunden.'))
    # Preserve launcher/scripts and their last-known-good content for rollback.
    root_files = [name for name in os.listdir(src)
                  if name not in SKIP and name != APP_ID and not name.startswith('.')
                  and not os.path.islink(os.path.join(src, name))]
    backup_bytes = _directory_bytes(pkg)+sum(_directory_bytes(os.path.join(root, name)) for name in root_files)
    staging_bytes = _directory_bytes(os.path.join(src, APP_ID))+max(
        (_directory_bytes(os.path.join(src, name)) for name in root_files), default=0)
    _require_space(root, backup_bytes+staging_bytes)
    staged = tempfile.mkdtemp(prefix='.vitalux-package-', dir=root)
    stage_pkg = os.path.join(staged, APP_ID)
    former = os.path.join(staged, 'former')
    touched = False
    try:
        shutil.copytree(os.path.join(src, APP_ID), stage_pkg, ignore=shutil.ignore_patterns('__pycache__'))
        if not os.path.isfile(os.path.join(stage_pkg, '__main__.py')):
            raise RuntimeError(tr('Update enthält kein ausführbares Vitalux-Modul.'))
        _stage_backup(root, root_files)
        progress(89)
        os.replace(pkg, former)
        touched = True
        try:
            os.replace(stage_pkg, pkg)
            for name in root_files:
                source = os.path.join(src, name)
                destination = os.path.join(root, name)
                if os.path.isdir(source):
                    temp_dir = tempfile.mkdtemp(prefix='.vitalux-assets-', dir=root)
                    new_dir = os.path.join(temp_dir, 'new')
                    try:
                        shutil.copytree(source, new_dir)
                        if os.path.isdir(destination):
                            old_dir = os.path.join(temp_dir, 'old')
                            os.replace(destination, old_dir)
                        os.replace(new_dir, destination)
                    finally:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                else:
                    fd, tmp_name = tempfile.mkstemp(prefix='.vitalux-file-', dir=root)
                    os.close(fd)
                    try:
                        shutil.copy2(source, tmp_name)
                        os.replace(tmp_name, destination)
                    finally:
                        if os.path.exists(tmp_name):
                            os.unlink(tmp_name)
            progress(100)
        except Exception:
            if os.path.isdir(pkg):
                shutil.rmtree(pkg)
            os.replace(former, pkg)
            touched = False
            _restore_root_files(root, os.path.join(root, '.backup'))
            raise
    finally:
        # When successful, former is redundant (the persistent backup holds a copy).
        # Never delete a saved former install if the attempted rollback failed.
        if not touched or os.path.isdir(pkg):
            shutil.rmtree(staged, ignore_errors=True)


def _restore_root_files(root, backup):
    try:
        with open(os.path.join(backup, 'metadata.json'), encoding='utf-8') as f:
            files = json.load(f).get('root_files', [])
    except (OSError, ValueError):
        files = []
    for name in files:
        if name in SKIP or '/' in name or name.startswith('.'):
            continue
        original = os.path.join(backup, 'root_files', name)
        destination = os.path.join(root, name)
        if os.path.isfile(original):
            shutil.copy2(original, destination)
        elif os.path.isdir(original):
            if os.path.isdir(destination):
                shutil.rmtree(destination)
            shutil.copytree(original, destination)


def restore_previous(root=None, restore_settings=True):
    """Restore the last pre-update package; optionally restore its settings.

    Call only after confirmation and with no active disk benchmark.
    """
    root = root or app_root()
    if not backup_available(root):
        raise RuntimeError(tr('Keine vorherige Version gesichert.'))
    backup = os.path.join(root, '.backup')
    target = os.path.join(root, APP_ID)
    stage = tempfile.mkdtemp(prefix='.vitalux-rollback-', dir=root)
    saved_current = os.path.join(stage, 'current')
    restored = os.path.join(stage, APP_ID)
    try:
        shutil.copytree(os.path.join(backup, APP_ID), restored)
        os.replace(target, saved_current)
        try:
            os.replace(restored, target)
            _restore_root_files(root, backup)
            if restore_settings and os.path.isfile(os.path.join(backup, 'settings.json')):
                metadata=json.loads(Path(backup,'metadata.json').read_text())
                saved_channel=metadata.get('profile_channel')
                destination=str(profiles.directory('config',saved_channel)/'settings.json') if saved_channel in ('stable','unstable') else settings.PATH
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(os.path.join(backup, 'settings.json'), destination)
        except Exception:
            if os.path.isdir(target):
                shutil.rmtree(target)
            os.replace(saved_current, target)
            raise
    finally:
        if os.path.isdir(target):
            shutil.rmtree(stage, ignore_errors=True)


def _zip_members(zipped):
    members=zipped.infolist()
    if len(members)>12000 or sum(item.file_size for item in members)>1200*1024*1024:
        raise RuntimeError(tr('Updatepaket ist zu groß.'))
    for item in members:
        path=PurePosixPath(item.filename)
        if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(item.external_attr>>16) or '\\' in item.filename:
            raise RuntimeError(tr('Unsicherer Pfad im Updatepaket.'))
    names={item.filename for item in members}
    if not any(name.endswith('vitalux/__main__.py') and name[:-len('vitalux/__main__.py')]+'run.sh' in names for name in names):
        raise RuntimeError(tr('Das Update-Paket hat eine unbekannte Struktur.'))
    return members


def _apply_zip(archive,root,progress):
    with tempfile.TemporaryDirectory(prefix='vitalux-extract-') as directory:
        with zipfile.ZipFile(archive) as zipped:
            members=_zip_members(zipped)
            _require_space(directory,sum(item.file_size for item in members))
            zipped.extractall(directory)
            for item in members:
                destination=os.path.join(directory,item.filename);mode=(item.external_attr>>16)&0o777
                if mode and os.path.isfile(destination):os.chmod(destination,mode)
        source=_find_root(directory)
        if not source:raise RuntimeError(tr('Das Update-Paket hat eine unbekannte Struktur.'))
        _install_from_directory(source,root,progress)


def apply_prepared_zip(archive,root,sha256):
    with open(archive,'rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=sha256:raise RuntimeError(tr('Sicherheitsprüfung fehlgeschlagen: SHA-256 stimmt nicht überein.'))
    _apply_zip(archive,root,lambda value:None)


def activate_zip_update(archive,sha256,pending_file,relaunch=True):
    """An external helper applies prepared files only after this process exits."""
    import sys
    root=app_root();folder=Path(archive).parent
    helper=folder/'apply-after-exit.py'
    # This helper imports the current implementation before replacing its files.
    code="""import os,sys,time,json,subprocess,traceback,shutil
from pathlib import Path
root,archive,digest,pending_file,pid,relaunch=sys.argv[1:]
sys.path.insert(0,root)
from vitalux import updater
process_exited=False
try:
    deadline=time.monotonic()+45
    while True:
        try:os.kill(int(pid),0)
        except ProcessLookupError:
            process_exited=True
            break
        if time.monotonic()>deadline:raise RuntimeError('Vitalux did not exit; prepared update retained')
        time.sleep(.1)
    updater.apply_prepared_zip(archive,root,digest)
    Path(pending_file).unlink(missing_ok=True)
    shutil.rmtree(Path(archive).parent,ignore_errors=True)
except Exception as error:
    path=Path(pending_file)
    try:
        state=json.loads(path.read_text());state['activation_error']=str(error)
        updater.profiles.atomic_json(path,state)
    except Exception:pass
    traceback.print_exc()
if relaunch=='yes' and process_exited:
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','PYTHONUSERBASE','APPDIR','APPIMAGE'):env.pop(key,None)
    subprocess.Popen(['bash',str(Path(root)/'run.sh')],env=env,start_new_session=True)
"""
    helper.write_text(code);helper.chmod(0o700)
    log=Path(pending_file).parent/'activation.log';log.parent.mkdir(parents=True,exist_ok=True)
    from . import logfiles
    logfiles.append(log, b'')
    with log.open('ab') as stream:
        subprocess.Popen([sys.executable,'-I',str(helper),root,str(archive),sha256,str(pending_file),
                          str(os.getpid()),'yes' if relaunch else 'no'],stdin=subprocess.DEVNULL,
                         stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)


def install(url, root=None, progress=lambda p: None, sha256=None, defer=False, expected_size=None):
    if appimage_path():return _stage_appimage(url,sha256,progress,expected_size=expected_size)
    root=root or app_root()
    if defer:
        if not os.path.isdir(os.path.join(root,APP_ID)):
            raise RuntimeError(tr('Bestehende Vitalux-Installation nicht gefunden.'))
        if not os.access(root,os.W_OK):
            raise RuntimeError(tr('Vitalux-Ordner ist schreibgeschützt. Bitte eine beschreibbare Installation verwenden.'))
        cache=profiles.directory('cache');cache.mkdir(parents=True,exist_ok=True)
        directory=tempfile.mkdtemp(prefix='prepared-zip-',dir=cache)
        try:
            archive=Path(directory)/'package.zip'
            _download_verified(url,str(archive),sha256,progress,700*1024*1024,expected_size=expected_size)
            with zipfile.ZipFile(archive) as zipped:_zip_members(zipped)
            progress(100)
            return str(archive)
        except BaseException:
            shutil.rmtree(directory,ignore_errors=True);raise
    with tempfile.TemporaryDirectory(prefix=f'{APP_ID}-update-') as directory:
        archive=os.path.join(directory,'update.zip')
        _download_verified(url,archive,sha256,progress,700*1024*1024,expected_size=expected_size)
        progress(85)
        _apply_zip(archive,root,progress)
