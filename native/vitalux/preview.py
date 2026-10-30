"""Local design preview with separate preferences and no release updates."""
import argparse
import os
from pathlib import Path


from .design_catalog import VISIBLE as DESIGNS


def prepare(design=None):
    # Resolve before importing settings: ordinary installed Vitalux preferences
    # and desktop integration must never be touched by a local design test.
    root = Path(__file__).resolve().parent.parent
    data = root / 'design-test-data'
    for variable, suffix in (
            ('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'),
            ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')):
        directory = data / suffix
        directory.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(directory)
    os.environ['VITALUX_LOCAL_PREVIEW'] = '1'
    from . import settings
    changes = {}
    if not Path(settings.PATH).exists():
        changes.update(theme='obsidian_gold', lang='de', render_backend='software',
                       guide_intro_choice='never', motion='smooth')
    if design is not None:
        if design not in DESIGNS:
            raise ValueError('Unknown Vitalux preview design')
        changes.update(theme=design, background_style='theme_default', ultra_eco=False,
                       _crystal_design_revision=2)
    if changes and not settings.set_many(changes):
        raise RuntimeError('Unable to save local preview preferences')


def main():
    parser = argparse.ArgumentParser(description='Vitalux local glass design preview')
    parser.add_argument('design', nargs='?', choices=DESIGNS)
    args = parser.parse_args()
    prepare(args.design)
    from .__main__ import main as run
    run()


if __name__ == '__main__':
    main()
