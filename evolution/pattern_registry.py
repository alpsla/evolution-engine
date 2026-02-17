"""
Pattern Registry — Auto-fetch pattern packages from PyPI.

Patterns are pure data (no executable code). We download the wheel from PyPI,
extract patterns.json, validate it, filter by locally-detected families, and
import into the KB.

Cache: ~/.evo/pattern_cache.json with 24h TTL. Patterns stored inline (small data).

Usage:
    from evolution.pattern_registry import fetch_available_patterns

    patterns = fetch_available_patterns(["ci", "git", "deployment"])
"""

import io
import json
import logging
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from evolution.adapter_versions import PYPI_URL, check_pypi_version

logger = logging.getLogger(__name__)

PATTERN_CACHE_PATH = Path.home() / ".evo" / "pattern_cache.json"
CACHE_TTL = 86400  # 24 hours
USER_SOURCES_PATH = Path.home() / ".evo" / "pattern_sources.json"
USER_BLOCKLIST_PATH = Path.home() / ".evo" / "pattern_blocklist.json"


def fetch_all_patterns() -> list[dict]:
    """Fetch ALL patterns from PyPI packages without family filtering.

    Used for community import — all patterns go into the KB,
    Phase 5 handles relevance matching at query time.
    """
    packages = _load_pattern_index()
    blocklist = _load_blocklist()
    packages = [p for p in packages if p not in blocklist]
    if not packages:
        return []

    all_patterns = []
    for pkg_name in packages:
        try:
            cached = _get_cached_or_fetch(pkg_name)
            if not cached:
                continue
            all_patterns.extend(cached.get("patterns", []))
        except Exception as e:
            logger.debug(f"Failed to fetch patterns from {pkg_name}: {e}")

    return all_patterns


def fetch_available_patterns(detected_families: list[str]) -> list[dict]:
    """Main entry point. Returns validated, family-filtered patterns ready for import.

    1. Load pattern index (bundled + user)
    2. Filter out blocked packages
    3. For each package: check cache or fetch from PyPI
    4. Filter patterns by detected_families
    5. Return flat list of pattern dicts

    Args:
        detected_families: List of active families (e.g. ["ci", "git"]).

    Returns:
        List of validated pattern dicts ready for kb_export.import_patterns().
    """
    packages = _load_pattern_index()
    blocklist = _load_blocklist()

    # Filter out blocked packages
    packages = [p for p in packages if p not in blocklist]
    if not packages:
        return []

    families_set = set(detected_families)
    all_patterns = []

    for pkg_name in packages:
        try:
            cached = _get_cached_or_fetch(pkg_name)
            if not cached:
                continue

            patterns = cached.get("patterns", [])
            filtered = _filter_by_families(patterns, families_set)
            all_patterns.extend(filtered)
        except Exception as e:
            logger.debug(f"Failed to fetch patterns from {pkg_name}: {e}")

    return all_patterns


def _load_pattern_index() -> list[str]:
    """Merge bundled + user pattern package lists."""
    packages = set()

    # Bundled index
    bundled_path = Path(__file__).parent / "data" / "pattern_index.json"
    if bundled_path.exists():
        try:
            data = json.loads(bundled_path.read_text())
            if isinstance(data, list):
                packages.update(data)
        except (json.JSONDecodeError, OSError):
            pass

    # User-added sources
    if USER_SOURCES_PATH.exists():
        try:
            data = json.loads(USER_SOURCES_PATH.read_text())
            if isinstance(data, list):
                packages.update(data)
        except (json.JSONDecodeError, OSError):
            pass

    return sorted(packages)


def _load_blocklist() -> set[str]:
    """Merge bundled + user blocklists."""
    blocked = set()

    bundled_path = Path(__file__).parent / "data" / "pattern_blocklist.json"
    if bundled_path.exists():
        try:
            data = json.loads(bundled_path.read_text())
            if isinstance(data, list):
                blocked.update(data)
        except (json.JSONDecodeError, OSError):
            pass

    if USER_BLOCKLIST_PATH.exists():
        try:
            data = json.loads(USER_BLOCKLIST_PATH.read_text())
            if isinstance(data, list):
                # Entries can be strings or dicts with "name" key
                for entry in data:
                    if isinstance(entry, str):
                        blocked.add(entry)
                    elif isinstance(entry, dict):
                        blocked.add(entry.get("name", ""))
        except (json.JSONDecodeError, OSError):
            pass

    blocked.discard("")
    return blocked


def _load_cache() -> dict:
    """Load pattern cache from disk."""
    if not PATTERN_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(PATTERN_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict):
    """Save pattern cache to disk."""
    try:
        PATTERN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PATTERN_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except OSError:
        pass


def _get_cached_or_fetch(package_name: str) -> Optional[dict]:
    """Check cache, then fetch from PyPI if stale or missing.

    Returns cache entry dict with keys: version, last_fetched, families, patterns.
    """
    now = time.time()
    cache = _load_cache()
    entry = cache.get(package_name)

    # Check if cache is fresh
    if entry and (now - entry.get("last_fetched", 0)) < CACHE_TTL:
        return entry

    # Check PyPI for latest version
    latest_version = check_pypi_version(package_name, use_cache=True)
    if not latest_version:
        # Package not found on PyPI — return stale cache if available
        return entry

    # If cached version matches, update timestamp and return
    if entry and entry.get("version") == latest_version:
        entry["last_fetched"] = now
        cache[package_name] = entry
        _save_cache(cache)
        return entry

    # Need to download new version
    patterns = _fetch_package_patterns(package_name, latest_version)
    if patterns is None:
        return entry  # Download failed, return stale cache

    # Extract family coverage
    families = set()
    for p in patterns:
        for s in p.get("sources", []):
            families.add(s)

    new_entry = {
        "version": latest_version,
        "last_fetched": now,
        "families": sorted(families),
        "patterns": patterns,
    }

    cache[package_name] = new_entry
    _save_cache(cache)
    return new_entry


def _fetch_package_patterns(package_name: str, version: str) -> Optional[list[dict]]:
    """Download wheel from PyPI and extract patterns.json.

    Returns parsed list of pattern dicts, or None on failure.
    """
    try:
        # Get the wheel URL from the PyPI JSON API
        url = PYPI_URL.format(package=package_name)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Find a wheel URL for the requested version
        wheel_url = None
        releases = data.get("urls", [])

        # Also check the releases dict for the specific version
        version_releases = data.get("releases", {}).get(version, [])
        all_urls = releases + version_releases

        for file_info in all_urls:
            filename = file_info.get("filename", "")
            if filename.endswith(".whl"):
                wheel_url = file_info.get("url")
                break

        # Fall back to sdist if no wheel
        if not wheel_url:
            for file_info in all_urls:
                filename = file_info.get("filename", "")
                if filename.endswith(".tar.gz"):
                    wheel_url = file_info.get("url")
                    break

        if not wheel_url:
            logger.debug(f"No wheel or sdist found for {package_name} {version}")
            return None

        return _download_and_extract_patterns(wheel_url, package_name)

    except (urllib.error.URLError, json.JSONDecodeError, OSError, KeyError) as e:
        logger.debug(f"Failed to fetch {package_name} from PyPI: {e}")
        return None


def _download_and_extract_patterns(url: str, package_name: str) -> Optional[list[dict]]:
    """Download archive and extract patterns.json.

    For wheels (.whl), opens as zip directly.
    Returns parsed list of pattern dicts.
    """
    from evolution.kb_security import PatternValidationError, validate_pattern

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

            # Size limit: 10MB
            if len(data) > 10 * 1024 * 1024:
                logger.debug(f"Package {package_name} too large ({len(data)} bytes)")
                return None

        # Open as zip (wheels are zip files)
        buf = io.BytesIO(data)
        try:
            with zipfile.ZipFile(buf) as zf:
                # Find patterns.json inside the wheel
                patterns_path = None
                for name in zf.namelist():
                    if name.endswith("patterns.json"):
                        patterns_path = name
                        break

                if not patterns_path:
                    logger.debug(f"No patterns.json found in {package_name}")
                    return None

                raw = json.loads(zf.read(patterns_path).decode("utf-8"))
        except zipfile.BadZipFile:
            logger.debug(f"Bad zip file for {package_name}")
            return None

        # raw can be a list of patterns or a dict with "patterns" key
        if isinstance(raw, dict):
            patterns = raw.get("patterns", [])
        elif isinstance(raw, list):
            patterns = raw
        else:
            return None

        # Validate each pattern
        validated = []
        for p in patterns:
            try:
                v = validate_pattern(p, require_external_scope=True)
                validated.append(v)
            except PatternValidationError as e:
                logger.debug(f"Pattern validation failed in {package_name}: {e}")

        return validated

    except (urllib.error.URLError, OSError) as e:
        logger.debug(f"Failed to download {url}: {e}")
        return None


def _filter_by_families(patterns: list[dict], families: set[str]) -> list[dict]:
    """Keep patterns where at least one source is in detected families."""
    if not families:
        return []
    # Expand aliases so "version_control" also matches "git" and vice versa
    _SOURCE_ALIASES = {"git": "version_control", "version_control": "git"}
    expanded = set(families)
    for f in list(expanded):
        if f in _SOURCE_ALIASES:
            expanded.add(_SOURCE_ALIASES[f])
    return [
        p for p in patterns
        if any(s in expanded for s in p.get("sources", []))
    ]


# ─────────────────── User Source Management ───────────────────


def add_pattern_source(package_name: str) -> bool:
    """Add a package to user pattern sources.

    Returns True if added, False if already present.
    """
    sources = _load_user_sources()
    if package_name in sources:
        return False
    sources.append(package_name)
    _save_user_sources(sources)
    return True


def remove_pattern_source(package_name: str) -> bool:
    """Remove a package from user pattern sources.

    Returns True if removed, False if not found.
    """
    sources = _load_user_sources()
    if package_name not in sources:
        return False
    sources.remove(package_name)
    _save_user_sources(sources)
    return True


def _load_user_sources() -> list[str]:
    """Load user pattern sources list."""
    if not USER_SOURCES_PATH.exists():
        return []
    try:
        data = json.loads(USER_SOURCES_PATH.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_user_sources(sources: list[str]):
    """Save user pattern sources list."""
    try:
        USER_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_SOURCES_PATH.write_text(json.dumps(sorted(set(sources)), indent=2))
    except OSError:
        pass


# ─────────────────── Blocklist Management ───────────────────


def block_pattern_package(name: str, reason: str = "") -> bool:
    """Add a package to user blocklist.

    Returns True if blocked, False if already blocked.
    """
    entries = _load_user_blocklist_entries()
    for e in entries:
        if isinstance(e, dict) and e.get("name") == name:
            return False
        if isinstance(e, str) and e == name:
            return False

    entry = {"name": name, "reason": reason, "blocked_at": int(time.time())}
    entries.append(entry)
    _save_user_blocklist(entries)

    # Also remove from cache
    cache = _load_cache()
    cache.pop(name, None)
    _save_cache(cache)

    return True


def unblock_pattern_package(name: str) -> bool:
    """Remove a package from user blocklist.

    Returns True if unblocked, False if not found.
    """
    entries = _load_user_blocklist_entries()
    new_entries = []
    found = False
    for e in entries:
        if isinstance(e, dict) and e.get("name") == name:
            found = True
        elif isinstance(e, str) and e == name:
            found = True
        else:
            new_entries.append(e)

    if not found:
        return False
    _save_user_blocklist(new_entries)
    return True


def _load_user_blocklist_entries() -> list:
    """Load raw user blocklist entries (strings or dicts)."""
    if not USER_BLOCKLIST_PATH.exists():
        return []
    try:
        data = json.loads(USER_BLOCKLIST_PATH.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_user_blocklist(entries: list):
    """Save user blocklist entries."""
    try:
        USER_BLOCKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_BLOCKLIST_PATH.write_text(json.dumps(entries, indent=2))
    except OSError:
        pass


# ─────────────────── Package Info ───────────────────


def list_pattern_packages() -> list[dict]:
    """List all known pattern packages with their cache status.

    Returns list of dicts with: name, source (bundled/user), cached_version,
    families, pattern_count.
    """
    bundled = set()
    bundled_path = Path(__file__).parent / "data" / "pattern_index.json"
    if bundled_path.exists():
        try:
            data = json.loads(bundled_path.read_text())
            if isinstance(data, list):
                bundled = set(data)
        except (json.JSONDecodeError, OSError):
            pass

    user_sources = set(_load_user_sources())
    blocklist = _load_blocklist()
    cache = _load_cache()

    result = []
    for pkg in sorted(bundled | user_sources):
        entry = cache.get(pkg, {})
        result.append({
            "name": pkg,
            "source": "bundled" if pkg in bundled else "user",
            "blocked": pkg in blocklist,
            "cached_version": entry.get("version"),
            "families": entry.get("families", []),
            "pattern_count": len(entry.get("patterns", [])),
            "last_fetched": entry.get("last_fetched"),
        })

    return result
