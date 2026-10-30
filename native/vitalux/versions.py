"""Comparable release and test versions; stable sorts after its test builds."""
import re

PATTERN=re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?(?:-unstable\.([1-9]\d*))?$')


def parse(value):
    match=PATTERN.fullmatch(str(value))
    if not match:raise ValueError('Invalid Vitalux version')
    major,minor,patch,build,test=match.groups()
    if build is not None and int(build)>9:raise ValueError('Release suffix must be 0–9')
    return tuple(map(int,(major,minor,patch,build or '0'))),int(test) if test else None


def key(value):
    base,test=parse(value)
    return (*base,int(test is None),test or 0)


def channel(value):
    return 'unstable' if parse(value)[1] is not None else 'stable'


def has_automatic_restart(value):
    """The updater belongs to the running build, not its download target."""
    return key(value) >= key('0.9.6.3-unstable.2')
