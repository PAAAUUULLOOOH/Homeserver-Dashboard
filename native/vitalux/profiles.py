"""Independent stable/test preferences, resources and versioned backups."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from . import __version__
from .versions import channel as version_channel

SCHEMA=1
KINDS={'config':'.config','cache':'.cache','data':'.local/share','state':'.local/state'}


def installed():return version_channel(__version__)


def root(kind):
    # The homeserver test package must never read/write the installed Vitalux profile.
    data=Path(os.environ.get('VITALUX_DATA',Path(__file__).resolve().parents[2]/'data'))
    return data/'native-profile'/kind


def directory(kind,channel=None):
    channel=channel or installed()
    if channel not in ('stable','unstable'):raise ValueError('Unknown update channel')
    base=root(kind)
    return base if channel=='stable' else base/'profiles'/'unstable'


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,tmp=tempfile.mkstemp(prefix='.vitalux-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def read(path):
    try:
        data=json.loads(Path(path).read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}


def selected():
    target=read(root('config')/'update-channel.json').get('target')
    return target if target in ('stable','unstable') else installed()


def select(channel):
    if channel not in ('stable','unstable'):raise ValueError('Unknown update channel')
    atomic_json(root('config')/'update-channel.json',{'target':channel})


def _resources(source,target):
    folder=source/'backgrounds'
    if not folder.is_dir():return
    for image in list(folder.iterdir())[:256]:
        if image.is_symlink() or not image.is_file() or image.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.bmp'):continue
        if image.stat().st_size>40*1024*1024:continue
        (target/'backgrounds').mkdir(parents=True,exist_ok=True)
        shutil.copy2(image,target/'backgrounds'/image.name)


def backup(channel=None):
    channel=channel or installed();source=directory('config',channel)
    if not (source/'settings.json').is_file():return None
    parent=root('config')/'profile-backups'/channel
    target=parent/str(time.time_ns());target.mkdir(parents=True)
    try:
        shutil.copy2(source/'settings.json',target/'settings.json')
        _resources(source,target)
        atomic_json(target/'backup.json',{'channel':channel,'version':__version__,'schema':SCHEMA})
    except BaseException:
        shutil.rmtree(target);raise
    for old in sorted(parent.iterdir(),key=lambda p:p.name,reverse=True)[5:]:
        if old.is_dir() and not old.is_symlink() and (old/'backup.json').is_file():shutil.rmtree(old)
    return target


def validate(data):
    result=dict(data)
    from .appearance import migrate
    result = migrate(result)
    for name in ('ui_sounds', 'ui_sound_volume', '_soft_click_revision'):
        result.pop(name, None)
    booleans=('close_to_tray','alerts_enabled','ultra_eco','mini_hud_enabled')
    for name in booleans:
        if name in result and type(result[name]) is not bool:result.pop(name)
    for name,default,low,high in (('interval',1,.1,60),
                                ('cpu_temp',90,40,110),('gpu_temp',90,40,110),
                                ('ram_usage',90,1,100),('disk_usage',95,1,100)):
        value=result.get(name)
        if name in result and (type(value) not in (int,float) or not low<=value<=high):result[name]=default
    if result.get('render_backend','software') not in ('software','opengl','wayland_opengl','wayland_vulkan','x11_opengl'):
        result['render_backend']='software'
    if result.get('lang','en') not in ('de','en'):result['lang']='en'
    for name in ('custom_backgrounds','custom_accents'):
        if name in result and not isinstance(result[name],list):result[name]=[]
    if 'network_app_limits' in result and not isinstance(result['network_app_limits'],dict):result['network_app_limits']={}
    return result


def _defaults(data):
    updated=validate(data)
    updated['_schema_version']=SCHEMA
    return updated


def reset_preferences(path=None):
    """Reset the active profile and its managed copies, preserving source images.

    Move owned data aside before committing defaults. A failed settings write
    restores the originals; the other channel is never included in the purge.
    Keep an initialized marker so Unstable cannot reimport Stable after reset.
    """
    path=Path(path) if path is not None else directory('config')/'settings.json'
    marker=path.parent/'profile-state.json'
    owned=[path.parent/'backgrounds']
    if path.parent.resolve()==directory('config').resolve():
        cache=directory('cache')
        # Stable's cache root also contains Unstable's isolated profile.
        if installed()=='stable' and cache.is_dir() and not cache.is_symlink():
            owned.extend(child for child in cache.iterdir() if child.name!='profiles')
        elif installed()=='unstable':
            owned.append(cache)
        owned.append(root('config')/'profile-backups'/installed())
    moved=[]
    committing=False
    try:
        for source in (*owned,path,marker):
            if not source.exists() and not source.is_symlink():continue
            temporary=Path(tempfile.mkdtemp(prefix='.vitalux-reset-',dir=source.parent))
            try:os.replace(source,temporary/'data')
            except BaseException:
                temporary.rmdir()
                raise
            moved.append((source,temporary))
        committing=True
        atomic_json(path,_defaults({}))
        atomic_json(marker,{'initialized':True,'schema':SCHEMA})
    except BaseException:
        if committing:
            for created in (path,marker):created.unlink(missing_ok=True)
        for source,temporary in reversed(moved):
            os.replace(temporary/'data',source)
            temporary.rmdir()
        raise
    for _source,temporary in moved:
        shutil.rmtree(temporary)
    return True


def initialize():
    target=directory('config');path=target/'settings.json'
    marker=target/'profile-state.json'
    if installed()=='unstable' and not path.exists() and not read(marker).get('initialized'):
        source=directory('config','stable')
        data=read(source/'settings.json');_resources(source,target)
    else:data=read(path)
    schema=data.get('_schema_version',0)
    if type(schema) is not int or schema>SCHEMA:
        backup();data={}
        atomic_json(root('config')/'profile-notice.json',{'channel':installed(),'reason':'incompatible_profile'})
    updated=_defaults(data)
    if updated!=data or not path.exists():
        if path.exists():backup()
        atomic_json(path,updated)
    if not read(marker).get('initialized'):
        atomic_json(marker,{'initialized':True,'schema':SCHEMA})
