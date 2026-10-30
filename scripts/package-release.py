#!/usr/bin/env python3
"""Package tracked sources and the pinned Linux runtime for a GitHub release."""
import argparse
import hashlib
import stat
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZIP_STORED,ZipFile,ZipInfo

ROOT=Path(__file__).resolve().parents[1]
NAME='Vitalux-Homeserver-v0.10.0-Test-linux-x86_64.zip'
PREFIX='Vitalux-Homeserver-v0.10.0-Test'
RUNTIME_SHA='194c62824f26239a7460c7bc12f4627eda0b616cf31b0cf861b963121081f3c8'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    runtime=ROOT/'portable-runtime/vitalux-linux-x86_64.tar.xz'
    if not runtime.is_file() or hashlib.sha256(runtime.read_bytes()).hexdigest()!=RUNTIME_SHA:
        raise SystemExit('Passende Laufzeit fehlt oder Prüfsumme ungültig.')
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    paths=[ROOT/name for name in names if name]
    paths.append(runtime)
    args.output.mkdir(parents=True,exist_ok=True)
    archive=args.output/NAME
    checks=[]
    with ZipFile(archive,'w',compression=ZIP_DEFLATED,compresslevel=6) as z:
        for source in sorted(paths):
            relative=source.relative_to(ROOT).as_posix()
            if source.is_symlink():raise SystemExit('Unerwarteter Symlink: '+relative)
            content=source.read_bytes()
            info=ZipInfo.from_file(source,PREFIX+'/'+relative,strict_timestamps=False)
            info.external_attr=(stat.S_IFREG|(0o755 if source.suffix=='.sh' else 0o644))<<16
            info.compress_type=ZIP_STORED if source.suffix=='.xz' else ZIP_DEFLATED
            z.writestr(info,content)
            checks.append(hashlib.sha256(content).hexdigest()+'  '+relative)
        info=ZipInfo(PREFIX+'/SHA256SUMS.txt');info.external_attr=(stat.S_IFREG|0o644)<<16
        z.writestr(info,'\n'.join(checks)+'\n')
    with ZipFile(archive) as z:
        if z.testzip() is not None:raise SystemExit('Ungültiges ZIP.')
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (args.output/(NAME+'.sha256')).write_text(digest+'  '+NAME+'\n')
    print(archive)
    print('SHA256: '+digest)


if __name__=='__main__':main()
