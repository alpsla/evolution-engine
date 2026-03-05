"""
Report i18n — lightweight translation helper for HTML report generation.

Loads JSON translation files from this package directory and provides
a _t(key) lookup function used by report_generator.py.
"""

import json
import locale
import os
from pathlib import Path

SUPPORTED_LANGS = ("en", "de", "es")
_translations: dict = {}
_current_lang: str = "en"


def _detect_lang() -> str:
    """Detect language from env, config, or system locale."""
    # 1. Explicit EVO_LANG env var
    env_lang = os.environ.get("EVO_LANG", "").lower()
    if env_lang in SUPPORTED_LANGS:
        return env_lang

    # 2. User config (~/.evo/config.toml)
    try:
        from evolution.config import get_config
        cfg_lang = get_config("lang", "").lower()
        if cfg_lang in SUPPORTED_LANGS:
            return cfg_lang
    except Exception:
        pass

    # 3. System locale
    try:
        sys_locale = locale.getlocale()[0] or ""
        prefix = sys_locale.split("_")[0].lower()
        if prefix in SUPPORTED_LANGS:
            return prefix
    except Exception:
        pass

    return "en"


def load_translations(lang: str = None) -> dict:
    """Load translation dict for the given language (or auto-detect)."""
    global _translations, _current_lang

    if lang is None:
        lang = _detect_lang()
    if lang not in SUPPORTED_LANGS:
        lang = "en"

    _current_lang = lang
    json_path = Path(__file__).parent / f"{lang}.json"
    if not json_path.exists():
        # Fallback to English
        json_path = Path(__file__).parent / "en.json"
        _current_lang = "en"

    _translations = json.loads(json_path.read_text())
    return _translations


def t(key: str, **kwargs) -> str:
    """Look up a translation key (dot-separated) with optional formatting.

    Example: t("cover.title") → "Evolution Advisory"
             t("exec.based_on", n=20) → "Based on 20 prior commits"
    """
    if not _translations:
        load_translations()

    parts = key.split(".")
    val = _translations
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p)
        else:
            return key  # key not found, return as-is

    if val is None:
        return key

    if kwargs and isinstance(val, str):
        try:
            return val.format(**kwargs)
        except (KeyError, IndexError):
            return val

    return val if isinstance(val, str) else key


def get_lang() -> str:
    """Return the currently active language code."""
    return _current_lang
