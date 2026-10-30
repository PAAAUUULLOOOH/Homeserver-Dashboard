"""Offline, versioned Vitalux release history in German and English."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
ENGLISH_CHANGELOG_PATH = ROOT / "CHANGELOG.en.md"
_HEADING = re.compile(r"^## \[v(\d+\.\d+\.\d+(?:\.\d+)?(?:-unstable\.\d+)?)\](?:[ \t]+-.*)?$", re.M)
_LANGUAGE_SECTION = re.compile(r"^## (Deutsch|English)\s*$", re.M)
RETIRED_VERSIONS = frozenset({'0.9.6.1-unstable.2'})


def visible_version(version):
    return str(version).lstrip('v') not in RETIRED_VERSIONS


def entries(path=None, lang=None):
    """Newest-first (version, changes), following the UI language by default."""
    if lang is None:
        from .i18n import lang as active_language
        lang = active_language()
    source = (Path(path) if path is not None else
              ENGLISH_CHANGELOG_PATH if lang == "en" else CHANGELOG_PATH)
    try:
        data = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    heads = list(_HEADING.finditer(data))
    results = []
    seen_versions = set()
    for idx, match in enumerate(heads):
        if match.group(1) in seen_versions or not visible_version(match.group(1)):
            continue
        seen_versions.add(match.group(1))
        until = heads[idx + 1].start() if idx + 1 < len(heads) else len(data)
        body = data[match.end():until]
        changes = [line.strip()[2:].strip() for line in body.splitlines()
                   if line.strip().startswith("- ") and len(line.strip()) > 2]
        if changes:
            results.append((match.group(1), changes))
    return results


def version_notes(version, path=None, lang=None):
    for ident, changes in entries(path, lang):
        if ident == str(version).lstrip("v"):
            return changes
    return []


def localized_release_notes(body, lang=None):
    """Extract one language from GitHub's bilingual release text.

    Older release descriptions with no language sections remain readable.
    """
    if not isinstance(body, str) or not body.strip():
        return ""
    if lang is None:
        from .i18n import lang as active_language
        lang = active_language()
    markers = list(_LANGUAGE_SECTION.finditer(body))
    if not markers:
        return body.strip()
    wanted = "English" if lang == "en" else "Deutsch"
    for index, marker in enumerate(markers):
        if marker.group(1) == wanted:
            end = markers[index+1].start() if index+1 < len(markers) else len(body)
            return body[marker.end():end].strip()
    return ""


def displayed_changes(changes):
    return "\n".join("• " + change for change in changes)


def channel_history(channel, record=None, lang=None):
    """Read-only, channel-specific history, including fresh or cached remote notes."""
    from . import versions
    history = {version: displayed_changes(changes) for version, changes in entries(lang=lang)
               if versions.channel(version) == channel}
    record = record or {}
    version = record.get('latest', '')
    try:
        matching = versions.channel(version) == channel and visible_version(version)
    except ValueError:
        matching = False
    if matching:
        # Inactive Unstable records can use Stable notes for availability/status.
        # Those notes must never be filed under a historical test version.
        raw = record.get('release_notes', '')
        if not raw and (channel == 'stable' or record.get('eligible')):
            raw = record.get('notes', '')
        body = localized_release_notes(raw, lang)
        if body or version not in history:
            history[version] = body
    return sorted(history.items(), key=lambda item: versions.key(item[0]), reverse=True)
