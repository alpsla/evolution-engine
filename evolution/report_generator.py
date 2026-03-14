"""
HTML Report Generator — Produces standalone HTML reports from Phase 5 advisory data.

Usage:
    from evolution.report_generator import generate_report
    html = generate_report(advisory_path)
    Path("report.html").write_text(html)

Or via CLI:
    evo report [path]
    evo report . --output report.html
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from evolution.constants import FAMILY_LABELS, METRIC_LABELS
from evolution.i18n import t, load_translations, get_lang
from evolution.phase5_engine import dedup_and_limit_patterns
from evolution.friendly import (
    risk_level, relative_change, metric_insight, friendly_pattern,
    pattern_risk_assessment, _severity_rank, escalate_compound_patterns,
)


def _family_label(key):
    """Get translated family label, falling back to constants."""
    val = t(f"families.{key}")
    if val != f"families.{key}":
        return val
    return FAMILY_LABELS.get(key, key)


def _metric_label(key):
    """Get translated metric label, falling back to constants."""
    val = t(f"metrics.{key}")
    if val != f"metrics.{key}":
        return val
    return METRIC_LABELS.get(key, key)


def _load_adapter_catalog() -> list:
    """Load the adapter catalog from bundled data."""
    catalog_path = Path(__file__).parent / "data" / "adapter_catalog.json"
    if catalog_path.exists():
        return json.loads(catalog_path.read_text())
    return []


def _load_universal_patterns_count() -> int:
    """Load the count of universal patterns from bundled data."""
    patterns_path = Path(__file__).parent / "data" / "universal_patterns.json"
    if patterns_path.exists():
        data = json.loads(patterns_path.read_text())
        return len(data.get("patterns", []))
    return 0


def _detect_remote_url(repo_dir: Path) -> str:
    """Try to detect the remote URL from git config.

    Returns a base URL like 'https://github.com/owner/repo' or empty string.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=str(repo_dir), timeout=5,
        )
        if result.returncode != 0:
            return ""
        url = result.stdout.strip()
        # SSH: git@github.com:owner/repo.git → https://github.com/owner/repo
        m = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)
        if m:
            return f"https://{m.group(1)}/{m.group(2)}"
        # HTTPS: https://github.com/owner/repo.git → https://github.com/owner/repo
        m = re.match(r"(https?://[^/]+/.+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
        return ""
    except Exception:
        return ""


def _commit_url(remote_url: str, sha: str) -> str:
    """Build a commit URL that works for both GitHub and GitLab.

    GitLab uses /-/commit/{sha}, GitHub and most others use /commit/{sha}.
    """
    if "gitlab" in remote_url.lower():
        return f"{remote_url}/-/commit/{sha}"
    return f"{remote_url}/commit/{sha}"


FAMILY_COLORS = {
    "git": "#3b82f6",
    "version_control": "#3b82f6",
    "ci": "#f59e0b",
    "testing": "#10b981",
    "coverage": "#059669",
    "dependency": "#8b5cf6",
    "schema": "#ec4899",
    "deployment": "#06b6d4",
    "config": "#6366f1",
    "security": "#ef4444",
    "error_tracking": "#dc2626",
    "monitoring": "#7c3aed",
    "quality_gate": "#0891b2",
    "security_scan": "#e11d48",
    "incidents": "#ea580c",
    "work_items": "#4f46e5",
    "feature_flags": "#65a30d",
}

FAMILY_ICONS = {
    "git": "\U0001f4dd",
    "version_control": "\U0001f4dd",
    "ci": "\u2699\ufe0f",
    "testing": "\U0001f9ea",
    "dependency": "\U0001f4e6",
    "schema": "\U0001f4cb",
    "deployment": "\U0001f680",
    "config": "\U0001f527",
    "security": "\U0001f512",
    "coverage": "\U0001f4ca",
    "error_tracking": "\U0001f6a8",
    "monitoring": "\U0001f4c8",
    "quality_gate": "\u2705",
    "security_scan": "\U0001f6e1\ufe0f",
    "incidents": "\U0001f6a8",
    "work_items": "\U0001f4cb",
    "feature_flags": "\U0001f6a9",
}

# Human-readable adapter display names for the "What EE Can See" section.
ADAPTER_DISPLAY = {
    "git": "Git",
    "pip": "pip",
    "npm": "npm",
    "pnpm": "pnpm",
    "go": "Go Modules",
    "cargo": "Cargo",
    "bundler": "Bundler",
    "composer": "Composer",
    "gradle": "Gradle",
    "maven": "Maven",
    "swift": "Swift PM",
    "cmake": "CMake",
    "github_actions_local": "GitHub Actions",
    "github_actions": "GitHub Actions",
    "gitlab_pipelines": "GitLab CI/CD",
    "circleci": "CircleCI",
    "github_releases": "GitHub Releases",
    "gitlab_releases": "GitLab Releases",
    "github_security": "GitHub Security",
    "pytest_cov": "pytest",
    "jest_cov": "Jest",
    "coverage_xml": "Cobertura XML",
    "sentry": "Sentry",
}


def _best_adapter_display(connected: list, family: str) -> str:
    """Pick the best adapter display name for a family.

    Prefers the highest-tier adapter (Tier 2 > Tier 1) since that's
    the one providing the most valuable data.
    """
    candidates = [c for c in connected if c.get("family") == family]
    if not candidates:
        return ""
    best = max(candidates, key=lambda c: c.get("tier", 1))
    adapter = best.get("adapter", "")
    return ADAPTER_DISPLAY.get(adapter, adapter)


def _load_diagnostics(evo_dir: Path) -> dict:
    """Load adapter diagnostics from .evo/diagnostics.json.

    Returns an empty dict if the file doesn't exist (backward compat).
    """
    if evo_dir is None:
        return {}
    diag_path = evo_dir / "diagnostics.json"
    if not diag_path.exists():
        return {}
    try:
        return json.loads(diag_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _detect_sources(repo_dir: Path) -> dict:
    """Detect connected and available data sources for the report.

    Returns a dict with 'connected' (list of AdapterConfig-like dicts)
    and 'detected' (list of DetectedService-like dicts), or empty on error.
    """
    try:
        from evolution.prescan import SourcePrescan
        from evolution.registry import AdapterRegistry

        # Load .env so tokens like GITHUB_TOKEN are available
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        registry = AdapterRegistry(repo_dir)
        prescan = SourcePrescan(repo_dir)

        connected = registry.detect()
        detected = prescan.scan()

        connected_family_set = set(c.family for c in connected)
        unconnected = [s for s in detected if s.family not in connected_family_set]

        return {
            "connected": [
                {"family": c.family, "adapter": c.adapter_name, "tier": c.tier,
                 "source_file": c.source_file}
                for c in connected
            ],
            "detected": [
                {"service": s.service, "display_name": s.display_name,
                 "family": s.family, "adapter": s.adapter,
                 "detection_layers": s.detection_layers, "evidence": s.evidence}
                for s in unconnected
            ],
            "connected_families": sorted(connected_family_set),
        }
    except Exception:
        return {"connected": [], "detected": [], "connected_families": []}


def generate_report(
    evo_dir: str | Path,
    title: str = None,
    calibration_result: dict = None,
    verification: dict = None,
    lang: str = None,
) -> str:
    """Generate a standalone HTML report from Phase 5 output.

    Args:
        evo_dir: Path to the .evo directory (or calibration run dir).
        title: Optional title override.
        calibration_result: Optional calibration_result.json dict for extra stats.
        verification: Optional diff result from history comparison (--verify).
        lang: Optional language code (e.g. "de", "es"). Auto-detected if None.

    Returns:
        Complete HTML string.
    """
    load_translations(lang)
    evo_dir = Path(evo_dir)
    advisory_path = evo_dir / "phase5" / "advisory.json"
    evidence_path = evo_dir / "phase5" / "evidence.json"

    if not advisory_path.exists():
        raise FileNotFoundError(f"No advisory found at {advisory_path}")

    advisory = json.loads(advisory_path.read_text())
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}

    scope = advisory.get("scope", "Unknown Repository")
    title = title or f"{t('cover.title')} \u2014 {scope}"

    # Auto-load verification data if not passed explicitly
    if verification is None:
        verify_path = evo_dir / "phase5" / "verification.json"
        if verify_path.exists():
            try:
                verification = json.loads(verify_path.read_text())
            except (json.JSONDecodeError, ValueError):
                pass

    # Try to detect git remote for commit links
    repo_dir = evo_dir.parent
    remote_url = _detect_remote_url(repo_dir)

    # Detect sources for the "What EE Can See" section
    sources_info = _detect_sources(repo_dir)

    # Load adapter diagnostics (why Tier 2 families have 0 signals)
    diagnostics = _load_diagnostics(evo_dir)

    # Detect Pro license — check live license OR infer from advisory
    # (if Tier 2 families like ci/deployment/security have data, analysis was Pro)
    _TIER2_FAMILIES = {"ci", "deployment", "security", "error_tracking"}
    try:
        from evolution.license import is_pro as _is_pro
        user_is_pro = _is_pro(str(repo_dir))
    except Exception:
        user_is_pro = False
    if not user_is_pro:
        # Infer from advisory: if Tier 2 families produced changes, was Pro
        advisory_families = set(advisory.get("summary", {}).get("families_affected", []))
        if advisory_families & _TIER2_FAMILIES:
            user_is_pro = True

    return _render_html(advisory, evidence, title, calibration_result, remote_url,
                        verification, sources_info, evo_dir, diagnostics,
                        is_pro=user_is_pro)


def _render_html(advisory, evidence, title, cal=None, remote_url="",
                  verification=None, sources_info=None, evo_dir=None,
                  diagnostics=None, is_pro=False):
    scope = advisory.get("scope", "Unknown")
    summary = advisory.get("summary", {})
    changes = advisory.get("changes", [])
    pattern_matches = advisory.get("pattern_matches", [])
    candidate_patterns = advisory.get("candidate_patterns", [])
    commits = evidence.get("commits", [])
    files_affected = evidence.get("files_affected", [])
    timeline = evidence.get("timeline", [])
    deps_changed = evidence.get("dependencies_changed", [])

    period = advisory.get("period", {})
    period_from = _format_date(period.get("from", ""))
    period_to = _format_date(period.get("to", ""))
    generated = _format_date(advisory.get("generated_at", ""))
    advisory_id = advisory.get("advisory_id", "")
    families_affected = summary.get("families_affected", [])

    # Confidence: use commits count from evidence
    n_commits = len(commits)

    # Total patterns matched = community + repo-specific from advisory
    total_patterns = len(pattern_matches) + len(candidate_patterns)

    cover = _build_cover_page(scope, period_from, period_to, advisory_id, generated)
    exec_summary = _build_executive_summary(summary, families_affected, cal, n_commits, total_patterns)
    sources_html = _build_sources_section(sources_info, families_affected, evo_dir, diagnostics, is_pro=is_pro) if sources_info else ""
    verify_html = _build_verification_banner(verification) if verification else ""
    findings_html = _build_key_findings(changes, pattern_matches, candidate_patterns, families_affected)
    # Accepted deviations — from the advisory summary (filtered by Phase 5)
    accepted_metrics = summary.get("accepted_metrics", [])
    # Format: "family/metric" → "family:metric" for key matching
    accepted_keys = set(m.replace("/", ":") for m in accepted_metrics)
    # Build commit lookup for per-finding evidence
    commits_by_sha = {}
    for cm in commits:
        sha = cm.get("sha", "")
        if sha:
            commits_by_sha[sha] = cm
    # Filter out patterns whose metrics are all accepted
    accepted_metric_names = set(m.split("/")[-1] for m in accepted_metrics)
    def _pattern_not_accepted(p):
        metrics = p.get("metrics") or []
        return not metrics or not all(m in accepted_metric_names for m in metrics)
    filtered_matches = [p for p in pattern_matches if _pattern_not_accepted(p)]
    filtered_candidates = [p for p in candidate_patterns if _pattern_not_accepted(p)]
    n_accepted_patterns = (len(pattern_matches) - len(filtered_matches)
                           + len(candidate_patterns) - len(filtered_candidates))

    # Dedup, escalate, and match patterns to changes
    deduped_matches = dedup_and_limit_patterns(filtered_matches, limit=len(filtered_matches)) if filtered_matches else []
    deduped_candidates = dedup_and_limit_patterns(filtered_candidates, limit=len(filtered_candidates)) if filtered_candidates else []
    deduped_all = list(deduped_matches) + list(deduped_candidates)
    escalate_compound_patterns(deduped_all)

    matched_patterns, unmatched_patterns = _match_patterns_to_changes(changes, deduped_all)

    changes_html = _build_changes_section(changes, remote_url, commits_by_sha, commits,
                                           deps_changed, accepted_keys, accepted_metrics,
                                           matched_patterns=matched_patterns)

    # Additional insights: unmatched patterns only
    unmatched_match_ids = set(id(p) for p in deduped_matches)
    patterns_html = _build_pattern_section(
        [p for p in unmatched_patterns if id(p) in unmatched_match_ids],
        [p for p in unmatched_patterns if id(p) not in unmatched_match_ids],
        accepted_pattern_count=n_accepted_patterns,
        accepted_metric_labels=[
            _metric_label(m) for m in sorted(accepted_metric_names)
        ],
        section_title=t("patterns.additional_insights_title") if matched_patterns else None,
    )
    all_patterns = list(pattern_matches) + list(candidate_patterns)
    invest_html = _build_investigation_section(
        scope, period_from, period_to, changes, commits, files_affected, timeline,
        all_patterns,
    )
    adapters_html = _build_adapters_section(families_affected, sources_info, is_pro=is_pro)
    return (
        f'<!DOCTYPE html>\n<html lang="{get_lang()}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>{_esc(title)}</title>\n'
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">\n'
        f'<style>\n{_CSS}\n</style>\n'
        f'{_JS}\n'
        '</head>\n<body>\n'
        f'{cover}\n'
        f'{exec_summary}\n'
        f'{sources_html}\n'
        f'{verify_html}\n'
        f'{findings_html}\n'
        f'{changes_html}\n'
        f'{patterns_html}\n'
        f'{invest_html}\n'
        f'{adapters_html}\n'
        '<footer>\n'
        f'  <p>{t("footer.generated_by")}</p>\n'
        f'  <p style="margin-top: 0.5em;">{t("footer.advisory_line", id=_esc(advisory_id), date=generated)}</p>\n'
        f'  <p style="margin-top: 0.5em;">{t("footer.ai_disclaimer")}</p>\n'
        '</footer>\n'
        '</body>\n</html>'
    )


# ─── Section Builders ───


def _build_cover_page(scope, period_from, period_to, advisory_id, generated):
    return (
        '<div class="cover-page page-break-after">\n'
        '  <svg class="logo" viewBox="0 0 48 56" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
        '    <path d="M24 0C24 0 0 6 0 14V32C0 44 10 54 24 56C38 54 48 44 48 32V14C48 6 24 0 24 0Z" fill="#0A4D4A"/>\n'
        '    <path d="M24 4C24 4 4 9 4 16V31C4 41 12 49 24 51C36 49 44 41 44 31V16C44 9 24 4 24 4Z" fill="none" stroke="#2CA58D" stroke-width="2"/>\n'
        '    <path d="M15 20L10 28L15 36" stroke="#F8F9FA" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '    <path d="M18 28L22 32L30 22" stroke="#2CA58D" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '    <path d="M33 20L38 28L33 36" stroke="#F8F9FA" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>\n'
        '  </svg>\n'
        '  <div class="cover-brand">CodeQual</div>\n'
        f'  <h1>{t("cover.title")}</h1>\n'
        '  <div class="cover-metadata">\n'
        f'    <p><strong>{t("cover.project")}</strong> {_esc(scope)}</p>\n'
        f'    <p><strong>{t("cover.period")}</strong> {period_from} {t("cover.period_to")} {period_to}</p>\n'
        f'    <p><strong>{t("cover.advisory_id")}</strong> <code>{_esc(advisory_id)}</code></p>\n'
        f'    <p><strong>{t("cover.generated")}</strong> {generated}</p>\n'
        '  </div>\n'
        '</div>'
    )


def _build_executive_summary(summary, families_affected, cal=None, n_commits=0, total_patterns=0):
    sig = summary.get("significant_changes", 0)
    n_fam = len(families_affected)
    new_obs = summary.get("new_observations", 0)

    cards = [
        _summary_card(str(sig), t("exec.significant_changes")),
        _summary_card(str(n_fam), t("exec.areas_affected")),
        _summary_card(str(total_patterns), t("exec.patterns_matched")),
        _summary_card(str(new_obs), t("exec.new_observations")),
    ]
    if cal:
        events = cal.get("events", 0)
        signals = cal.get("signals", 0)
        if events:
            cards.append(_summary_card(f"{events:,}", t("exec.events_analyzed")))
        if signals:
            cards.append(_summary_card(f"{signals:,}", t("exec.signals_computed")))

    family_items = " ".join(
        FAMILY_ICONS.get(f, "") + " " + _family_label(f)
        for f in families_affected
    )
    families_html = ""
    if families_affected:
        families_html = (
            '<p class="summary-families">'
            f'<strong>{t("exec.affected_areas")}</strong> {family_items}'
            '</p>'
        )

    confidence_html = ""
    if n_commits > 0:
        confidence_html = (
            '<p class="confidence-note">'
            f'{t("exec.based_on", n=f"{n_commits:,}", s="s" if n_commits != 1 else "")}'
            '</p>'
        )

    return (
        '<section class="executive-summary">\n'
        f'  <h2>{t("exec.title")}</h2>\n'
        '  <div class="summary-cards">\n'
        '    ' + '\n    '.join(cards) + '\n'
        '  </div>\n'
        f'  {families_html}\n'
        f'  {confidence_html}\n'
        '</section>'
    )


def _summary_card(value, label):
    return (
        f'<div class="summary-card">'
        f'<div class="summary-value">{value}</div>'
        f'<div class="summary-label">{label}</div>'
        f'</div>'
    )


def _build_verification_banner(verification):
    """Build a before/after comparison banner from --verify data."""
    resolved = verification.get("resolved", [])
    persisting = verification.get("persisting", [])
    new_changes = verification.get("new", [])

    total_before = len(resolved) + len(persisting)
    n_resolved = len(resolved)
    n_improving = sum(1 for p in persisting if p.get("improved"))
    n_not_improving = sum(1 for p in persisting if not p.get("improved"))
    n_new = len(new_changes)

    # Overall status
    if n_resolved == total_before and n_new == 0 and total_before > 0:
        status_class = "verify-all-clear"
        status_icon = "\u2705"
        status_text = t("verify.all_resolved")
    elif n_resolved > 0 or n_improving > 0:
        status_class = "verify-improving"
        status_icon = "\U0001f4c8"
        status_text = t("verify.progress")
    else:
        status_class = "verify-no-change"
        status_icon = "\u2194\ufe0f"
        status_text = t("verify.no_change")

    # Build signal rows
    rows = []
    for r in resolved:
        metric = _metric_label(r.get("metric", ""))
        family = _family_label(r.get("family", ""))
        rows.append(
            f'<tr class="verify-resolved"><td>{_esc(family)}</td><td>{_esc(metric)}</td>'
            f'<td colspan="2">{t("verify.resolved")}</td><td>\u2705</td></tr>'
        )
    has_transient = False
    has_persistent = False
    has_stabilized = False
    for p in persisting:
        metric = _metric_label(p.get("metric", ""))
        family = _family_label(p.get("family", ""))
        was = p.get("was_deviation", 0)
        now = p.get("now_deviation", 0)
        improved = p.get("improved", False)
        trend_icon = "\U0001f4c9" if improved else "\u2796"
        trend_label = t("verify.improving") if improved else t("verify.not_improving")
        trend_class = "verify-trend-good" if improved else "verify-trend-flat"
        # Detect historical triggers: deviation unchanged means the most deviant
        # commit is an older one that wasn't affected by the recent fix
        if not improved and abs(was) > 0 and abs(was - now) < 0.1:
            latest_dev = p.get("latest_deviation")
            if latest_dev is not None and abs(latest_dev) >= 1.5:
                # Still actively deviating in latest measurement
                trend_label = t("verify.still_deviating")
                trend_class = "verify-trend-warn"
                has_persistent = True
            else:
                # Low latest deviation — but did the value actually return?
                latest_val = p.get("latest_value")
                if _value_near_baseline(latest_val, p.get("normal", {})):
                    trend_label = t("verify.returned_normal")
                    has_transient = True
                else:
                    trend_label = t("verify.stabilized")
                    trend_class = "verify-trend-stabilized"
                    has_stabilized = True
        # Show actual observed values instead of raw σ numbers
        before_val = _fmt_value(p.get("was_value"))
        after_val = _fmt_value(p.get("current"))
        normal = p.get("normal", {})
        baseline = _fmt_value(normal.get("median", normal.get("mean")))
        rows.append(
            f'<tr><td>{_esc(family)}</td><td>{_esc(metric)}</td>'
            f'<td>{_esc(before_val)}</td>'
            f'<td>{_esc(after_val)}<span class="verify-baseline"> / {_esc(baseline)}</span></td>'
            f'<td class="{trend_class}">{trend_icon} {trend_label}</td></tr>'
        )
    for n in new_changes:
        metric = _metric_label(n.get("metric", ""))
        family = _family_label(n.get("family", ""))
        rows.append(
            f'<tr class="verify-new"><td>{_esc(family)}</td><td>{_esc(metric)}</td>'
            f'<td colspan="2">{t("verify.new")}</td><td>\u26a0\ufe0f</td></tr>'
        )

    rows_html = "\n".join(rows)

    # Summary chips
    chips = []
    if n_resolved:
        chips.append(f'<span class="verify-chip verify-chip-resolved">\u2705 {t("verify.chip_resolved", n=n_resolved)}</span>')
    if n_improving:
        chips.append(f'<span class="verify-chip verify-chip-improving">\U0001f4c8 {t("verify.chip_improving", n=n_improving)}</span>')
    if n_not_improving:
        chips.append(f'<span class="verify-chip verify-chip-flat">\u2796 {t("verify.chip_not_improving", n=n_not_improving)}</span>')
    if n_new:
        chips.append(f'<span class="verify-chip verify-chip-new">\u26a0\ufe0f {t("verify.chip_new", n=n_new)}</span>')

    # Guidance notes for historical triggers
    historical_note = ""
    if has_transient:
        historical_note += (
            '  <div class="verify-note">\n'
            f'    <strong>{t("verify.transient_title")}</strong> {t("verify.transient_text")}\n'
            '  </div>\n'
        )
    if has_stabilized:
        historical_note += (
            '  <div class="verify-note-stabilized">\n'
            f'    <strong>{t("verify.stabilized_title")}</strong> {t("verify.stabilized_text")}\n'
            '  </div>\n'
        )
    if has_persistent:
        historical_note += (
            '  <div class="verify-note-warn">\n'
            f'    <strong>{t("verify.active_title")}</strong> {t("verify.active_text")}\n'
            '  </div>\n'
        )

    return (
        f'<section class="verification-banner {status_class}">\n'
        f'  <div class="verify-header">\n'
        f'    <span class="verify-icon">{status_icon}</span>\n'
        f'    <div>\n'
        f'      <div class="verify-title">{t("verify.title", status=status_text)}</div>\n'
        f'      <div class="verify-subtitle">{t("verify.subtitle")}</div>\n'
        f'    </div>\n'
        f'  </div>\n'
        f'  <div class="verify-chips">{"".join(chips)}</div>\n'
        f'  <table class="verify-table">\n'
        f'    <thead><tr><th>{t("verify.th_area")}</th><th>{t("verify.th_signal")}</th><th>{t("verify.th_before")}</th><th>{t("verify.th_after_normal")}</th><th>{t("verify.th_trend")}</th></tr></thead>\n'
        f'    <tbody>{rows_html}</tbody>\n'
        f'  </table>\n'
        f'{historical_note}'
        f'</section>'
    )


def _match_patterns_to_changes(changes, all_patterns):
    """Match patterns to changes by family+metric overlap.

    A pattern is relevant to a change if the pattern's families contain the
    change's family AND the pattern's metrics contain the change's metric.

    Returns:
        matched: dict mapping change index -> list of matched patterns
        unmatched: list of patterns that didn't match any change
    """
    matched = {}
    matched_ids = set()
    for i, change in enumerate(changes):
        c_family = change.get("family", "")
        c_metric = change.get("metric", "")
        for p in all_patterns:
            p_families = set(p.get("families") or p.get("sources") or [])
            p_metrics = set(p.get("metrics") or [])
            if c_family in p_families and c_metric in p_metrics:
                matched.setdefault(i, []).append(p)
                matched_ids.add(id(p))
    unmatched = [p for p in all_patterns if id(p) not in matched_ids]
    return matched, unmatched


def _build_key_findings(changes, pattern_matches, candidate_patterns, families_affected):
    """Build a concise narrative summary of all findings."""
    if not changes and not pattern_matches and not candidate_patterns:
        return (
            '<section class="key-findings">\n'
            f'  <h2>{t("findings.title")}</h2>\n'
            f'  <p class="empty">{t("findings.empty")}</p>\n'
            '</section>'
        )

    bullets = []

    # Summarize changes by family
    if changes:
        family_changes = {}
        for c in changes:
            fam = _family_label(c.get("family", ""))
            family_changes.setdefault(fam, []).append(c)
        for fam, items in family_changes.items():
            high = [c for c in items if abs(c.get("deviation_stddev", 0)) >= 4.0]
            med = [c for c in items if 2.0 <= abs(c.get("deviation_stddev", 0)) < 4.0]
            if high:
                metrics = ", ".join(
                    _metric_label(c.get("metric", ""))
                    for c in high
                )
                bullets.append(
                    t("findings.significant", fam=f'<strong>{_esc(fam)}</strong>', metrics=_esc(metrics))
                )
            elif med:
                metrics = ", ".join(
                    _metric_label(c.get("metric", ""))
                    for c in med
                )
                bullets.append(
                    t("findings.moderate", fam=f'<strong>{_esc(fam)}</strong>', metrics=_esc(metrics))
                )
            else:
                metrics = ", ".join(
                    _metric_label(c.get("metric", ""))
                    for c in items
                )
                bullets.append(
                    t("findings.minor", fam=f'<strong>{_esc(fam)}</strong>', metrics=_esc(metrics))
                )

    # Summarize patterns
    n_known = len(pattern_matches) if pattern_matches else 0
    n_new = len(candidate_patterns) if candidate_patterns else 0
    if n_known or n_new:
        parts = []
        if n_known:
            parts.append(t("findings.known_patterns", n=n_known, s="s" if n_known != 1 else ""))
        if n_new:
            parts.append(t("findings.new_patterns", n=n_new, s="s" if n_new != 1 else ""))
        bullets.append(". ".join(parts) + ".")

    items_html = "\n".join(f'    <li>{b}</li>' for b in bullets)
    return (
        '<section class="key-findings">\n'
        f'  <h2>{t("findings.title")}</h2>\n'
        '  <ul class="findings-list">\n'
        f'{items_html}\n'
        '  </ul>\n'
        '</section>'
    )


def _build_changes_section(changes, remote_url="", commits_by_sha=None,
                           all_commits=None, deps_changed=None,
                           accepted_keys=None, accepted_metrics=None,
                           matched_patterns=None):
    accepted_keys = accepted_keys or set()
    accepted_metrics = accepted_metrics or []

    # Build accepted banner if there are accepted deviations
    accepted_banner = ""
    if accepted_metrics:
        n_accepted = len(accepted_metrics)
        items = []
        for m in accepted_metrics:
            parts = m.split("/", 1)
            if len(parts) == 2:
                fam_label = _family_label(parts[0])
                met_label = _metric_label(parts[1])
                items.append(f'{fam_label} / {met_label}')
            else:
                items.append(m)
        items_html = ", ".join(items)
        accepted_banner = (
            '  <div class="accepted-summary">\n'
            f'    <span class="accepted-summary-icon">\u2713</span>\n'
            f'    <div>\n'
            f'      <strong>{t("changes.accepted_not_shown", n=n_accepted, s="s" if n_accepted != 1 else "")}</strong>'
            f' {items_html}\n'
            f'      <div class="accepted-summary-hint">'
            f'{t("changes.accepted_hint")}</div>\n'
            f'    </div>\n'
            '  </div>\n'
        )

    if not changes:
        return (
            '<section class="changes-detected page-break-before">\n'
            f'  <h2>{t("changes.title")}</h2>\n'
            f'{accepted_banner}'
            f'  <p class="empty">{t("changes.empty")}</p>\n'
            '</section>'
        )

    n = len(changes)
    cards = "\n".join(
        _build_change_card(c, idx, remote_url, commits_by_sha or {},
                           all_commits or [], deps_changed or [], accepted_keys,
                           matched_patterns=(matched_patterns or {}).get(idx, []))
        for idx, c in enumerate(changes)
    )

    filter_buttons = (
        '  <div class="severity-filters no-print">\n'
        f'    <button class="btn btn-filter active" onclick="filterChanges(\'all\', this)">{t("changes.filter_all")}</button>\n'
        f'    <button class="btn btn-filter" onclick="filterChanges(\'deviation-high\', this)">{t("changes.filter_critical")}</button>\n'
        f'    <button class="btn btn-filter" onclick="filterChanges(\'deviation-medium\', this)">{t("changes.filter_medium")}</button>\n'
        f'    <button class="btn btn-filter" onclick="filterChanges(\'deviation-low\', this)">{t("changes.filter_low")}</button>\n'
        '  </div>\n'
    )

    resolved_span = '<span id="resolvedCount">0</span>'
    progress_label = t("changes.resolved_of", resolved=resolved_span, total=n)
    progress_bar = (
        '  <div class="progress-tracker no-print" id="progressTracker">\n'
        f'    {progress_label}\n'
        '    <div class="progress-bar"><div class="progress-fill" id="progressFill" '
        f'style="width: 0%;" data-total="{n}"></div></div>\n'
        '  </div>\n'
    )

    return (
        '<section class="changes-detected page-break-before">\n'
        f'  <h2>{t("changes.title")}</h2>\n'
        f'{accepted_banner}'
        '  <p style="color: var(--color-text-muted); margin-bottom: 1.5em;">\n'
        f'    {t("changes.detected", n=n, s="s" if n != 1 else "")}\n'
        '  </p>\n'
        f'{progress_bar}'
        f'{filter_buttons}'
        f'  {cards}\n'
        '</section>'
    )


def _build_change_card(c, index=0, remote_url="", commits_by_sha=None,
                       all_commits=None, deps_changed=None,
                       accepted_keys=None, matched_patterns=None):
    family = c.get("family", "")
    metric_key = c.get("metric", "")
    metric_name = _metric_label(metric_key)
    family_label = _family_label(family)
    icon = FAMILY_ICONS.get(family, "")
    current = c.get("current", 0)
    normal = c.get("normal", {})
    median = normal.get("median", normal.get("mean", 0))
    dev = c.get("deviation_stddev", 0)
    dev_class = _deviation_class(dev)
    is_accepted = f"{family}:{metric_key}" in (accepted_keys or set())
    direction = "above" if dev >= 0 else "below"
    abs_dev = abs(dev)

    anchor_id = f"change-{_esc(family)}-{_esc(metric_key)}"

    normal_w, current_w = _bar_widths(current, median)

    insight_dir = "up" if dev >= 0 else "down"
    friendly = c.get("description_friendly")
    insight = metric_insight(metric_key, insight_dir)
    explanation = f"<strong>{t('card.what_this_means')}</strong> "
    if friendly:
        explanation += _esc(friendly)
    elif insight:
        explanation += insight
    else:
        explanation += t("card.was_compared", metric=_esc(metric_name), value=_fmt_num(current), median=_fmt_num(median))

    mad = normal.get("mad", normal.get("stddev", 0))

    # Only show technical details when there's meaningful statistical data
    tech_html = ""
    if mad and mad > 0:
        tech = t("card.technical_text",
                  metric=metric_key.replace('_', ' '),
                  value=_fmt_num(current),
                  median=f"{_fmt_num(median)} &plusmn; {_fmt_num(mad)}")
        tech_html = (
            '  <details class="technical-detail">\n'
            f'    <summary>{t("card.show_technical")}</summary>\n'
            f'    <p>{tech}</p>\n'
            '  </details>\n'
        )

    # Action buttons: Accept + Fix with AI
    accept_idx = index + 1  # 1-based for CLI
    accept_cmd = f'evo accept . {accept_idx} --reason &quot;Expected behavior&quot;'
    accept_thisrun = f'evo accept . {accept_idx} --scope this-run --reason &quot;Expected behavior&quot;'

    # Build drift prompt for Fix with AI — scoped to this finding's commit
    full_trigger = c.get("trigger_commit", "")
    commit_sha = full_trigger[:8]
    commit_msg = _esc(c.get("commit_message", "").split("\n")[0])
    drift_prompt = (
        f"Development pattern shift detected in {_esc(family_label)}.\\n\\n"
        f"SIGNAL: {_esc(metric_name)} is {abs_dev:.1f}x {direction} the typical baseline "
        f"(observed: {_fmt_num(current)}, typical: {_fmt_num(median)}).\\n"
    )
    if commit_sha:
        drift_prompt += f"TRIGGER COMMIT: {commit_sha} — {commit_msg}\\n"

    # Add per-finding file evidence from the trigger commit
    trigger_files = c.get("trigger_files", [])
    if not trigger_files:
        # Fallback: look up from evidence commits
        commit_data = (commits_by_sha or {}).get(full_trigger, {})
        trigger_files = commit_data.get("files_changed", [])
    if trigger_files:
        drift_prompt += f"\\nFILES CHANGED IN TRIGGER ({len(trigger_files)}):\\n"
        for fp in trigger_files[:15]:
            drift_prompt += f"  - {_esc(fp)}\\n"
        if len(trigger_files) > 15:
            drift_prompt += f"  ... and {len(trigger_files) - 15} more\\n"

    # Add recent commits from evidence (excluding trigger) for broader context
    evidence_commits = all_commits or []
    other_commits = [cm for cm in evidence_commits if cm.get("sha", "") != full_trigger]
    if other_commits:
        drift_prompt += f"\\nRECENT COMMITS ({len(other_commits)} total, showing top 5):\\n"
        for cm in other_commits[:5]:
            cm_sha = cm.get("sha", "")[:8]
            cm_msg = _esc(cm.get("message", "").split("\\n")[0][:60])
            cm_files = len(cm.get("files_changed", []))
            drift_prompt += f"  {cm_sha} — {cm_msg} ({cm_files} files)\\n"
        if len(other_commits) > 5:
            drift_prompt += f"  ... and {len(other_commits) - 5} more commits\\n"

    # Add dependency changes if this finding is in the dependency family
    evidence_deps = deps_changed or []
    if evidence_deps and family in ("dependency", "dep"):
        drift_prompt += f"\\nDEPENDENCIES CHANGED ({len(evidence_deps)}):\\n"
        for dep in evidence_deps[:10]:
            dep_name = _esc(dep.get("name", dep.get("package", "")))
            dep_from = dep.get("from", dep.get("old_version", ""))
            dep_to = dep.get("to", dep.get("new_version", ""))
            if dep_from and dep_to:
                drift_prompt += f"  - {dep_name}: {dep_from} -> {dep_to}\\n"
            else:
                drift_prompt += f"  - {dep_name}\\n"
        if len(evidence_deps) > 10:
            drift_prompt += f"  ... and {len(evidence_deps) - 10} more\\n"

    # Add matched pattern context to the prompt
    if matched_patterns:
        drift_prompt += "\\nCORRELATED PATTERNS:\\n"
        for p in matched_patterns:
            p_desc = p.get("description_semantic") or friendly_pattern(p)
            p_risk = pattern_risk_assessment(p)
            drift_prompt += f"  [{p_risk['severity'].upper()}] {_esc(p_desc)}\\n"
            drift_prompt += f"    → {_esc(p_risk['recommendation'])}\\n"
            for extra in p.get("_merged_recommendations") or []:
                drift_prompt += f"    → {_esc(extra)}\\n"

    if commit_sha:
        drift_prompt += (
            "\\nINVESTIGATE:\\n"
            "1. Was this change intentional or did the AI drift from goals?\\n"
            f"2. Review commit {commit_sha} — what specifically caused the deviation?\\n"
            "3. Suggest a course correction (not a bug fix — a realignment).\\n\\n"
            "AFTER FIX:\\n"
            "Run `evo analyze . --verify` to re-analyze and compare against this run.\\n"
            "If the change was intentional, no fix needed — accept it in the report."
        )
    else:
        drift_prompt += (
            "\\nINVESTIGATE:\\n"
            "1. Was this change intentional or did the AI drift from goals?\\n"
            "2. Identify which recent commit introduced this shift.\\n"
            "3. Suggest a course correction (not a bug fix — a realignment).\\n\\n"
            "AFTER FIX:\\n"
            "Run `evo analyze . --verify` to re-analyze and compare against this run.\\n"
            "If the change was intentional, no fix needed — accept it in the report."
        )

    if is_accepted:
        action_buttons = (
            f'  <div class="change-actions no-print" id="actions-{index}">\n'
            f'    <div class="accept-group">\n'
            f'      <button class="btn btn-action btn-accept accepted" disabled>{t("card.accepted")}</button>\n'
            f'    </div>\n'
            f'    <button class="btn btn-action btn-fix" onclick="toggleFixPrompt({index})">{t("card.fix_with_ai")}</button>\n'
            f'  </div>\n'
        )
    else:
        action_buttons = (
            f'  <div class="change-actions no-print" id="actions-{index}">\n'
            f'    <div class="accept-group">\n'
            f'      <button class="btn btn-action btn-accept" onclick="toggleAcceptMenu({index})">{t("card.accept_expected")}</button>\n'
            f'      <div class="accept-menu" id="accept-menu-{index}">\n'
            f'        <button onclick="acceptFinding({index}, \'permanent\', \'{accept_cmd}\')">{t("card.accept_permanent")}<span class="accept-hint">{t("card.hint_permanent")}</span></button>\n'
            f'        <button onclick="acceptFinding({index}, \'this-run\', \'{accept_thisrun}\')">{t("card.accept_thisrun")}<span class="accept-hint">{t("card.hint_thisrun")}</span></button>\n'
            f'      </div>\n'
            f'    </div>\n'
            f'    <button class="btn btn-action btn-fix" onclick="toggleFixPrompt({index})">{t("card.fix_with_ai")}</button>\n'
            f'  </div>\n'
        )

    fix_prompt_html = (
        f'  <div class="fix-prompt-panel no-print" id="fix-prompt-{index}">\n'
        f'    <div class="fix-prompt-header">\n'
        f'      <strong>{t("card.drift_prompt_title")}</strong>\n'
        f'      <button class="btn btn-copy-sm" onclick="copyFixPrompt({index})">{t("card.copy")}</button>\n'
        f'    </div>\n'
        f'    <pre class="fix-prompt-text" id="fix-prompt-text-{index}">{drift_prompt}</pre>\n'
        f'    <div class="fix-prompt-guide">\n'
        f'      <strong>{t("card.use_with")}</strong>\n'
        f'      <span>{t("card.cursor_hint")}</span>\n'
        f'      <span>{t("card.claude_hint")}</span>\n'
        f'      <span>{t("card.copilot_hint")}</span>\n'
        f'    </div>\n'
        f'    <div class="fix-next-steps">\n'
        f'      <strong>{t("card.after_investigation")}</strong>\n'
        f'      <ol>\n'
        f'        <li>{t("card.after_step1")}</li>\n'
        f'        <li>{t("card.after_step2")}</li>\n'
        f'        <li>{t("card.after_step3")}</li>\n'
        f'      </ol>\n'
        f'    </div>\n'
        f'  </div>\n'
    )

    # Commit attribution line with optional link
    commit_html = ""
    full_sha = c.get("trigger_commit", "")
    if full_sha:
        sha_display = full_sha[:8]
        msg_display = _esc(c.get("commit_message", "").split("\n")[0][:60])
        if remote_url:
            commit_link = _commit_url(remote_url, _esc(full_sha))
            sha_html = f'<a href="{commit_link}" target="_blank" class="commit-link"><code>{sha_display}</code></a>'
        else:
            sha_html = f'<code>{sha_display}</code>'
        commit_html = (
            f'  <div class="commit-attribution">'
            f'{t("card.trigger")} {sha_html} {msg_display}'
            f'</div>\n'
        )

    # Trend subtitle for historical triggers
    trend_html = ""
    if full_sha and not c.get("is_latest_event", True):
        latest_dev = c.get("latest_deviation")
        if latest_dev is not None:
            if abs(latest_dev) >= 1.5:
                trend_html = f'  <div class="trend-subtitle trend-elevated">{t("card.still_elevated", dev=f"{abs(latest_dev):.1f}")}</div>\n'
            else:
                trend_html = f'  <div class="trend-subtitle trend-returning">{t("card.returned_baseline")}</div>\n'

    accepted_class = " change-card-accepted" if is_accepted else ""
    accepted_badge = (
        '    <div class="accepted-badge">\u2713 Accepted</div>\n'
        if is_accepted else ""
    )

    # Inline patterns: supporting evidence for this change
    INLINE_VISIBLE_LIMIT = 3
    inline_patterns_html = ""
    if matched_patterns:
        # Sort by severity (most critical first), using the change's actual direction
        sorted_patterns = sorted(
            matched_patterns,
            key=lambda p: _severity_rank(pattern_risk_assessment(p, change_direction=insight_dir)["severity"]),
            reverse=True,
        )
        visible = sorted_patterns[:INLINE_VISIBLE_LIMIT]
        hidden = sorted_patterns[INLINE_VISIBLE_LIMIT:]
        pattern_items = "\n".join(_build_inline_pattern(p, change_direction=insight_dir) for p in visible)
        overflow_html = ""
        if hidden:
            hidden_items = "\n".join(_build_inline_pattern(p, change_direction=insight_dir) for p in hidden)
            overflow_html = (
                f'    <details class="inline-patterns-overflow">\n'
                f'      <summary>{t("patterns.show_more", n=len(hidden), heading=t("patterns.supporting_evidence").lower())}</summary>\n'
                f'      {hidden_items}\n'
                f'    </details>\n'
            )
        inline_patterns_html = (
            '  <div class="inline-patterns">\n'
            f'    <div class="inline-patterns-header">{t("patterns.supporting_evidence")}</div>\n'
            f'    {pattern_items}\n'
            f'{overflow_html}'
            '  </div>\n'
        )

    return (
        f'<div class="change-card {dev_class}{accepted_class}" id="{anchor_id}">\n'
        '  <div class="change-card-header">\n'
        f'    <span class="family-icon">{icon}</span>\n'
        f'    <div>\n'
        f'      <div class="metric-name">{_esc(metric_name)}</div>\n'
        f'      <div class="family-label">{_esc(family_label)}</div>\n'
        f'    </div>\n'
        f'{accepted_badge}'
        '  </div>\n'
        f'  <div class="user-friendly-summary">{explanation}</div>\n'
        '  <div class="bar-chart">\n'
        '    <div class="bar-chart-row">\n'
        f'      <div class="bar-label">{t("card.typical")}</div>\n'
        f'      <div class="bar-container"><div class="bar-fill normal" style="width: {normal_w}%"></div></div>\n'
        f'      <div class="bar-value">{_fmt_num(median)}</div>\n'
        '    </div>\n'
        '    <div class="bar-chart-row">\n'
        f'      <div class="bar-label">{t("card.this_time")}</div>\n'
        f'      <div class="bar-container"><div class="bar-fill" style="width: {current_w}%"></div></div>\n'
        f'      <div class="bar-value">{_fmt_num(current)}</div>\n'
        '    </div>\n'
        '  </div>\n'
        f'  <div class="deviation-badge">{t("card.above_range", dev=f"{abs_dev:.1f}") if dev >= 0 else t("card.below_range", dev=f"{abs_dev:.1f}")}</div>\n'
        f'{commit_html}'
        f'{trend_html}'
        f'{inline_patterns_html}'
        f'{action_buttons}'
        f'{fix_prompt_html}'
        f'{tech_html}'
        '</div>'
    )


def _build_inline_pattern(p, change_direction=None):
    """Build a compact inline pattern for embedding within a change card."""
    risk = pattern_risk_assessment(p, change_direction=change_direction)
    severity = risk["severity"]
    sev_display = risk["severity_display"]
    recommendation = risk["recommendation"]
    impact = risk["impact"]

    # Include merged recommendations/impacts from subset elimination (deduplicated)
    extra_recs = [r for r in (p.get("_merged_recommendations") or []) if r not in recommendation]
    extra_impacts = [i for i in (p.get("_merged_impacts") or []) if i not in impact]
    if extra_impacts:
        impact += " " + " ".join(extra_impacts)
    if extra_recs:
        recommendation += " " + " ".join(extra_recs)

    desc = p.get("description_semantic") or friendly_pattern(p)

    return (
        f'<div class="inline-pattern severity-border-{severity}">\n'
        f'  <span class="severity-badge severity-{severity}">'
        f'{sev_display["icon"]} {_esc(sev_display["label"])}</span>\n'
        + (f'  <p class="inline-pattern-desc">{_esc(desc)}</p>\n' if desc else '')
        + f'  <div class="pattern-impact"><strong>{t("patterns.what_this_means")}</strong> {_esc(impact)}</div>\n'
        f'  <div class="pattern-recommendation"><strong>{t("patterns.recommendation")}</strong> {_esc(recommendation)}</div>\n'
        f'</div>'
    )


def _build_pattern_card(p, badge_label):
    """Build a single pattern card with severity badge, impact, and recommendation."""
    sources = ", ".join(_family_label(s) for s in p.get("sources", []))
    metrics = ", ".join(_metric_label(m) for m in p.get("metrics", []))
    desc = p.get("description_semantic") or friendly_pattern(p)
    risk = pattern_risk_assessment(p)
    severity = risk["severity"]
    sev_display = risk["severity_display"]
    impact = risk["impact"]
    recommendation = risk["recommendation"]

    badge_style = ' style="background: var(--color-warning);"' if badge_label == t("patterns.emerging_pattern") else ""

    # Include merged recommendations/impacts from subsumed subset patterns (deduplicated)
    extra_impacts = [i for i in (p.get("_merged_impacts") or []) if i not in impact]
    extra_recs = [r for r in (p.get("_merged_recommendations") or []) if r not in recommendation]
    full_impact = impact
    if extra_impacts:
        full_impact += " " + " ".join(extra_impacts)
    full_recommendation = recommendation
    if extra_recs:
        full_recommendation += " " + " ".join(extra_recs)

    return (
        f'<div class="pattern-card severity-border-{severity}">\n'
        f'  <span class="badge"{badge_style}>{badge_label}</span>\n'
        f'  <span class="severity-badge severity-{severity}">'
        f'{sev_display["icon"]} {_esc(sev_display["label"])}</span>\n'
        f'  <h3 style="margin-top: 0.5em;">{_esc(sources)}</h3>\n'
        f'  <div class="pattern-meta">{_esc(metrics)}</div>\n'
        + (f'  <p>{_esc(desc)}</p>\n' if desc else '')
        + f'  <div class="pattern-impact"><strong>{t("patterns.what_this_means")}</strong> {_esc(full_impact)}</div>\n'
        f'  <div class="pattern-recommendation"><strong>{t("patterns.recommendation")}</strong> {_esc(full_recommendation)}</div>\n'
        '</div>'
    )


def _build_grouped_pattern_card(patterns, badge_label):
    """Build a single card for multiple patterns sharing the same severity + impact.

    Combines sources and metrics from all patterns, shows each pattern's description
    as a bullet point, but uses the shared impact/recommendation only once.
    """
    risk = pattern_risk_assessment(patterns[0])
    severity = risk["severity"]
    sev_display = risk["severity_display"]
    impact = risk["impact"]
    recommendation = risk["recommendation"]

    badge_style = ' style="background: var(--color-warning);"' if badge_label == t("patterns.emerging_pattern") else ""

    # Collect unique sources, metrics, and merged recommendations across all patterns
    all_sources = []
    all_metrics = []
    descriptions = []
    all_impacts = {impact}
    all_recs = {recommendation}
    for p in patterns:
        for s in p.get("sources", []):
            label = _family_label(s)
            if label not in all_sources:
                all_sources.append(label)
        for m in p.get("metrics", []):
            label = _metric_label(m)
            if label not in all_metrics:
                all_metrics.append(label)
        desc = p.get("description_semantic") or friendly_pattern(p)
        if desc:
            descriptions.append(desc)
        # Collect merged recommendations/impacts from subset elimination
        for extra in p.get("_merged_impacts") or []:
            all_impacts.add(extra)
        for extra in p.get("_merged_recommendations") or []:
            all_recs.add(extra)

    sources_str = ", ".join(all_sources)
    metrics_str = ", ".join(all_metrics)
    full_impact = " ".join(all_impacts)
    full_recommendation = " ".join(all_recs)

    # Show each pattern's description as a bullet
    desc_html = ""
    if descriptions:
        items = "\n".join(f'    <li>{_esc(d)}</li>' for d in descriptions)
        desc_html = f'  <ul class="grouped-pattern-list">\n{items}\n  </ul>\n'

    return (
        f'<div class="pattern-card severity-border-{severity}">\n'
        f'  <span class="badge"{badge_style}>{badge_label}</span>\n'
        f'  <span class="severity-badge severity-{severity}">'
        f'{sev_display["icon"]} {_esc(sev_display["label"])}</span>\n'
        f'  <span class="pattern-group-count">{t("patterns.similar_severity", n=len(patterns))}</span>\n'
        f'  <h3 style="margin-top: 0.5em;">{_esc(sources_str)}</h3>\n'
        f'  <div class="pattern-meta">{_esc(metrics_str)}</div>\n'
        f'{desc_html}'
        f'  <div class="pattern-impact"><strong>{t("patterns.what_this_means")}</strong> {_esc(full_impact)}</div>\n'
        f'  <div class="pattern-recommendation"><strong>{t("patterns.recommendation")}</strong> {_esc(full_recommendation)}</div>\n'
        '</div>'
    )


def _grouped_cards(patterns, badge_label):
    """Group patterns by (severity, impact) and render cards.

    Patterns with identical severity+impact text are combined into a single card
    to avoid duplicate 'What this means' content.
    """
    if not patterns:
        return []

    # Group by (severity, impact) tuple
    groups = {}
    for p in patterns:
        risk = pattern_risk_assessment(p)
        key = (risk["severity"], risk["impact"])
        groups.setdefault(key, []).append(p)

    cards = []
    # Iterate groups in the order of the first pattern in each group
    # (patterns are already sorted by severity)
    seen_keys = []
    for p in patterns:
        risk = pattern_risk_assessment(p)
        key = (risk["severity"], risk["impact"])
        if key in seen_keys:
            continue
        seen_keys.append(key)
        group = groups[key]
        if len(group) == 1:
            cards.append(_build_pattern_card(group[0], badge_label))
        else:
            cards.append(_build_grouped_pattern_card(group, badge_label))

    return cards


def _build_pattern_section(matches, candidates, accepted_pattern_count=0,
                           accepted_metric_labels=None, section_title=None):
    if not matches and not candidates and not accepted_pattern_count:
        return ""

    PATTERN_VISIBLE_LIMIT = 3

    # Patterns are already deduped and escalated upstream — just use as-is
    deduped_all = list(matches or []) + list(candidates or [])

    # Severity counts from deduped patterns (matches what user sees in cards)
    severity_counts = {}
    highest_severity = "info"
    for p in deduped_all:
        sev = pattern_risk_assessment(p)["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        if _severity_rank(sev) > _severity_rank(highest_severity):
            highest_severity = sev

    # Sort all patterns by severity (most critical first), unified list
    matches_set = set(id(p) for p in (matches or []))
    all_sorted = sorted(
        deduped_all,
        key=lambda p: _severity_rank(pattern_risk_assessment(p)["severity"]),
        reverse=True,
    )

    # Group all patterns together so _grouped_cards can merge identical impacts
    known = [p for p in all_sorted if id(p) in matches_set]
    new = [p for p in all_sorted if id(p) not in matches_set]
    all_cards = _grouped_cards(known, t("patterns.known_pattern")) + _grouped_cards(new, t("patterns.new_pattern"))

    cards_html = _collapsible_pattern_cards(all_cards, "patterns", PATTERN_VISIBLE_LIMIT)

    # Build overall risk banner
    banner_html = _build_pattern_risk_banner(highest_severity, severity_counts, len(deduped_all))

    # User guidance
    guidance = (
        '<div class="pattern-guidance">\n'
        f'  <p><strong>{t("patterns.what_are_patterns")}</strong> {t("patterns.what_are_patterns_text")}</p>\n'
        f'  <p><strong>{t("patterns.what_should_you_do")}</strong> '
        + t("patterns.what_should_you_do_text",
             action_required=f'<span class="severity-badge severity-critical">\u26a0\ufe0f {t("severity.action_required")}</span>',
             needs_attention=f'<span class="severity-badge severity-concern">\U0001f50d {t("severity.needs_attention")}</span>',
             worth_monitoring=f'<span class="severity-badge severity-watch">\U0001f441\ufe0f {t("severity.worth_monitoring")}</span>',
             healthy_pattern=f'<span class="severity-badge severity-positive">\u2705 {t("severity.healthy")}</span>',
             informational=f'<span class="severity-badge severity-info">\u2139\ufe0f {t("severity.informational")}</span>',
        ) + '</p>\n'
        '</div>\n'
    )

    # Build dedup note explaining which metrics were merged
    # Uses the same canonical mapping as dedup_and_limit_patterns
    _METRIC_CANONICAL = {"change_locality": "dispersion"}
    dedup_note = ""
    all_raw = list(matches or []) + list(candidates or [])
    # Collect raw metrics that were canonicalized into another metric
    merged_pairs = []
    for p in all_raw:
        for m in (p.get("metrics") or []):
            canon = _METRIC_CANONICAL.get(m)
            if canon:
                alias_label = _metric_label(m)
                canon_label = _metric_label(canon)
                pair = (alias_label, canon_label)
                if pair not in merged_pairs:
                    merged_pairs.append(pair)
    if merged_pairs:
        merges = ", ".join(
            t("patterns.dedup_note", a=a, b=b)
            for a, b in merged_pairs
        )
        dedup_note = (
            f'<p class="patterns-dedup-note">'
            f'{merges} &mdash; {t("patterns.dedup_shown")}'
            f'</p>\n'
        )

    # Note for patterns hidden because their metrics were accepted
    accepted_note = ""
    if accepted_pattern_count and accepted_metric_labels:
        labels = ", ".join(accepted_metric_labels)
        accepted_note = (
            f'<p class="patterns-dedup-note">'
            f'{t("patterns.accepted_hidden", n=accepted_pattern_count, s="s" if accepted_pattern_count != 1 else "", ms="s" if len(accepted_metric_labels) != 1 else "", labels=_esc(labels))}'
            f'</p>\n'
        )

    title_text = section_title or t("patterns.title")
    return (
        '<section class="patterns page-break-before">\n'
        f'  <h2>{title_text}</h2>\n'
        f'  {dedup_note}'
        f'  {accepted_note}'
        f'  {banner_html}\n'
        f'  {guidance}\n'
        f'  {cards_html}\n'
        '</section>'
    )


_OVERALL_RISK_CLASSES = {
    "critical": "risk-banner-critical",
    "concern": "risk-banner-concern",
    "watch": "risk-banner-watch",
    "info": "risk-banner-info",
    "positive": "risk-banner-positive",
}

_OVERALL_RISK_KEYS = {
    "critical": ("risk_banner.critical_title", "risk_banner.critical_text"),
    "concern": ("risk_banner.concern_title", "risk_banner.concern_text"),
    "watch": ("risk_banner.watch_title", "risk_banner.watch_text"),
    "info": ("risk_banner.info_title", "risk_banner.info_text"),
    "positive": ("risk_banner.positive_title", "risk_banner.positive_text"),
}


def _build_pattern_risk_banner(highest_severity, severity_counts, total):
    """Build the overall risk assessment banner for the patterns section."""
    css_class = _OVERALL_RISK_CLASSES.get(highest_severity, _OVERALL_RISK_CLASSES["info"])
    title_key, text_key = _OVERALL_RISK_KEYS.get(highest_severity, _OVERALL_RISK_KEYS["info"])

    # Build severity breakdown chips
    chips = []
    for sev in ("critical", "concern", "watch", "info", "positive"):
        count = severity_counts.get(sev, 0)
        if count > 0:
            from evolution.friendly import _SEVERITY_DISPLAY
            display = _SEVERITY_DISPLAY[sev]
            chips.append(
                f'<span class="severity-chip severity-{sev}">'
                f'{display["icon"]} {count} {display["label"]}'
                f'</span>'
            )

    chips_html = " ".join(chips)

    return (
        f'<div class="risk-banner {css_class}">\n'
        f'  <div class="risk-banner-title">{t(title_key)}</div>\n'
        f'  <p>{t(text_key)}</p>\n'
        f'  <div class="risk-banner-chips">{chips_html}</div>\n'
        f'</div>'
    )


def _collapsible_pattern_cards(cards, heading, limit):
    """Wrap pattern cards in a collapsible <details> when there are more than *limit*."""
    if not cards:
        return ""
    if len(cards) <= limit:
        return '\n'.join(cards)
    visible = '\n'.join(cards[:limit])
    hidden = '\n'.join(cards[limit:])
    extra = len(cards) - limit
    return (
        f'{visible}\n'
        f'<details class="pattern-overflow">\n'
        f'  <summary class="toggle-btn">{t("patterns.show_more", n=extra, heading=heading)}</summary>\n'
        f'  {hidden}\n'
        f'</details>'
    )


def _build_investigation_section(scope, period_from, period_to, changes,
                                  commits, files, timeline, patterns=None):
    if not changes:
        return ""

    preview = _build_prompt(
        scope, period_from, period_to, changes, commits, files, timeline,
        patterns=patterns, full=False,
    )
    full = _build_prompt(
        scope, period_from, period_to, changes, commits, files, timeline,
        patterns=patterns, full=True,
    )

    return (
        '<section class="investigation-section page-break-before">\n'
        '  <div class="next-steps-header">\n'
        f'    <h2 style="margin: 0;">{t("investigation.title")}</h2>\n'
        '  </div>\n'
        '  <div class="next-steps-flow">\n'
        '    <div class="step-card">\n'
        '      <div class="step-number">1</div>\n'
        '      <div class="step-content">\n'
        f'        <div class="step-title">{t("investigation.step1_title")}</div>\n'
        f'        <p>{t("investigation.step1_text")}</p>\n'
        '      </div>\n'
        '    </div>\n'
        '    <div class="step-card">\n'
        '      <div class="step-number">2</div>\n'
        '      <div class="step-content">\n'
        f'        <div class="step-title">{t("investigation.step2_title")}</div>\n'
        f'        <p>{t("investigation.step2_text")}</p>\n'
        '      </div>\n'
        '    </div>\n'
        '    <div class="step-card">\n'
        '      <div class="step-number">3</div>\n'
        '      <div class="step-content">\n'
        f'        <div class="step-title">{t("investigation.step3_title")}</div>\n'
        f'        <p>{t("investigation.step3_text")}</p>\n'
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
        f'  <h3 style="margin-top: 1.5em;">{t("investigation.prompt_title")}</h3>\n'
        f'  <div class="prompt-preview">{_esc(preview)}</div>\n'
        '  <div class="action-buttons no-print">\n'
        f'    <button class="btn btn-primary" onclick="copyPrompt()" id="copyBtn">{t("investigation.copy_prompt")}</button>\n'
        f'    <button class="btn btn-secondary" onclick="savePromptToFile()">{t("investigation.save_prompt")}</button>\n'
        f'    <button class="toggle-btn" onclick="togglePrompt()" id="togglePromptBtn">{t("investigation.show_full")}</button>\n'
        '  </div>\n'
        f'  <pre class="prompt-full" id="fullPrompt">{_esc(full)}</pre>\n'
        '</section>'
    )


def _integrations_link():
    return f'<a href="https://codequal.dev/docs/integrations" class="source-doc-link">{t("sources.setup_guide")}</a>'


def _get_source_hints():
    """Build source hints dict with translated strings (must be called after load_translations)."""
    link = _integrations_link()
    return {
        "ci": {
            "github": (
                'Config found but no run data. Set your token to get build duration '
                '&amp; failure metrics.'
                '<div class="source-hint-cmd">'
                '<code>export GITHUB_TOKEN=$(gh auth token)</code>'
                f' {link}'
                '</div>'
            ),
            "gitlab": (
                'Config found but no run data. Set your token to get pipeline metrics.'
                '<div class="source-hint-cmd">'
                '<code>export GITLAB_TOKEN=glpat-...</code>'
                f' {link}'
                '</div>'
            ),
            "default": (
                'CI config found but no run data. Set the appropriate token to unlock '
                f'build duration &amp; failure metrics. {link}'
            ),
        },
        "deployment": (
            'Set <code>GITHUB_TOKEN</code> or <code>GITLAB_TOKEN</code> to unlock '
            f'release cadence and deployment metrics. {link}'
        ),
        "security": (
            'Set <code>GITHUB_TOKEN</code> (with <code>security_events</code> scope) '
            f'to get security advisory data. {link}'
        ),
        "testing": (
            'Generate test results: '
            '<code>pytest --junitxml=junit.xml</code> or equivalent, then re-run analysis. '
            f'{link}'
        ),
        "coverage": (
            'Generate coverage reports: '
            '<code>pytest --cov --cov-report=xml</code> or equivalent, then re-run analysis. '
            f'{link}'
        ),
        "error_tracking": (
            'Set <code>SENTRY_AUTH_TOKEN</code> to pull error tracking data from Sentry. '
            f'{link}'
        ),
    }


def _count_signals(evo_dir: Path, family: str) -> int:
    """Count Phase 2 signals for a given family."""
    if evo_dir is None:
        return 0
    # Normalize: "version_control" → "git" for file paths
    file_family = "git" if family == "version_control" else family
    signals_path = evo_dir / "phase2" / f"{file_family}_signals.json"
    if not signals_path.exists():
        return 0
    try:
        data = json.loads(signals_path.read_text())
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def _get_ci_hint(connected: list) -> str:
    """Determine the appropriate CI hint based on detected adapter sources."""
    hints = _get_source_hints()
    for c in connected:
        if c.get("family") == "ci":
            source = c.get("source_file") or ""
            if "gitlab" in source.lower():
                return hints["ci"]["gitlab"]
            if "github" in source.lower():
                return hints["ci"]["github"]
    return hints["ci"]["default"]


def _build_sources_section(sources_info: dict, families_affected: list,
                            evo_dir: Path = None, diagnostics: dict = None,
                            is_pro: bool = False) -> str:
    """Build the 'What EE Can See' section showing all connected families."""
    if not sources_info:
        return ""

    connected = sources_info.get("connected", [])
    detected = sources_info.get("detected", [])
    connected_families = sources_info.get("connected_families", [])

    if not connected and not detected:
        return ""

    # Build a set of families that have findings
    findings_set = set(families_affected)
    # Normalize: "git" ↔ "version_control"
    if "git" in findings_set:
        findings_set.add("version_control")
    if "version_control" in findings_set:
        findings_set.add("git")

    # Group connected adapters by family (deduplicate)
    connected_by_family = {}
    for c in connected:
        fam = c["family"]
        if fam not in connected_by_family:
            connected_by_family[fam] = c

    _source_hints = _get_source_hints()
    cards = []

    # 1. Connected families with findings → green "Active" badge
    # 2. Connected families without findings → blue "No Deviations" badge
    for fam, adapter_info in connected_by_family.items():
        icon = FAMILY_ICONS.get(fam, "")
        label = _family_label(fam)
        color = FAMILY_COLORS.get(fam, "#64748b")
        adapter_display = _best_adapter_display(connected, fam)
        has_findings = fam in findings_set

        # Check adapter tier — Tier 2+ means a token is present
        has_api_adapter = any(
            c.get("tier", 1) >= 2 and c.get("family") == fam
            for c in connected
        )

        if has_findings:
            badge = f'<div class="source-status source-status-active">{t("sources.active")}</div>'
            detail = ""
        else:
            # Check if we have signals (analyzed but no deviations)
            n_signals = _count_signals(evo_dir, fam)
            if n_signals > 0:
                badge = f'<div class="source-status source-status-quiet">{t("sources.connected_no_deviations")}</div>'
                detail = (
                    f'<div class="source-detail">'
                    f'{t("sources.signals_analyzed", n=f"{n_signals:,}", s="s" if n_signals != 1 else "")}'
                    f'</div>'
                )
            elif has_api_adapter:
                # Token is set (Tier 2) but no signal data — check diagnostics
                diag = (diagnostics or {}).get(fam)
                if diag and diag.get("status") == "platform_mismatch":
                    badge = f'<div class="source-status source-status-warn">{t("sources.platform_mismatch")}</div>'
                    detail = (
                        f'<div class="source-detail">'
                        f'{_esc(diag["message"])} '
                        f'{_integrations_link()}'
                        f'</div>'
                    )
                elif diag and diag.get("status") == "no_license":
                    if is_pro:
                        badge = f'<div class="source-status source-status-quiet">{t("sources.connected")}</div>'
                        detail = (
                            '<div class="source-detail">'
                            f'{t("sources.token_set")} '
                            f'{_integrations_link()}'
                            '</div>'
                        )
                    else:
                        badge = f'<div class="source-status source-status-pro">{t("sources.pro")}</div>'
                        detail = (
                            '<div class="source-detail">'
                            f'{t("sources.pro_available")} '
                            f'<a href="https://codequal.dev/#pricing" class="source-doc-link">{t("sources.see_plans")}</a>'
                            '</div>'
                        )
                elif diag and diag.get("status") == "api_error":
                    badge = f'<div class="source-status source-status-warn">{t("sources.api_error")}</div>'
                    detail = (
                        f'<div class="source-detail">'
                        f'{_esc(diag["message"])} '
                        f'{_integrations_link()}'
                        f'</div>'
                    )
                elif diag and diag.get("status") == "no_data":
                    badge = f'<div class="source-status source-status-quiet">{t("sources.connected_no_data")}</div>'
                    detail = (
                        f'<div class="source-detail">'
                        f'{_esc(diag["message"])} '
                        f'{_integrations_link()}'
                        f'</div>'
                    )
                elif diag and diag.get("status") == "active":
                    # Adapter ran successfully but produced no signals
                    badge = f'<div class="source-status source-status-quiet">{t("sources.connected_no_data")}</div>'
                    _active_hints = {
                        "ci": t("sources.ci_no_runs"),
                        "deployment": t("sources.deployment_no_releases"),
                        "security": t("sources.security_clean"),
                        "error_tracking": t("sources.error_no_events"),
                        "testing": t("sources.testing_no_files"),
                        "coverage": t("sources.coverage_no_files"),
                    }
                    hint = _active_hints.get(fam, t("sources.connected_no_data_default"))
                    detail = (
                        f'<div class="source-detail">'
                        f'{hint} '
                        f'{_integrations_link()}'
                        f'</div>'
                    )
                else:
                    # Fallback: no diagnostics file
                    if is_pro:
                        badge = f'<div class="source-status source-status-quiet">{t("sources.connected")}</div>'
                        detail = (
                            '<div class="source-detail">'
                            f'{t("sources.token_set")} '
                            f'{_integrations_link()}'
                            '</div>'
                        )
                    else:
                        badge = f'<div class="source-status source-status-pro">{t("sources.pro")}</div>'
                        detail = (
                            '<div class="source-detail">'
                            f'{t("sources.pro_available")} '
                            f'<a href="https://codequal.dev/#pricing" class="source-doc-link">{t("sources.see_plans")}</a>'
                            '</div>'
                        )
            else:
                # Tier 1 only (config file found, no token) — show actionable hint
                badge = f'<div class="source-status source-status-hint">{t("sources.config_detected")}</div>'
                if fam == "ci":
                    hint_text = _get_ci_hint(connected)
                elif isinstance(_source_hints.get(fam), str):
                    hint_text = _source_hints[fam]
                else:
                    hint_text = "Connected but no data yet. Re-run analysis after setup."
                detail = f'<div class="source-detail">{hint_text}</div>'

        adapter_html = (
            f'<div class="source-adapter">{t("sources.via")} {_esc(adapter_display)}</div>'
            if adapter_display else ""
        )
        cards.append(
            f'<div class="source-card">'
            f'<div class="source-card-header">'
            f'<span class="source-icon" style="color: {color}">{icon}</span>'
            f'<div>'
            f'<div class="source-name">{_esc(label)}</div>'
            f'{adapter_html}'
            f'{badge}'
            f'</div>'
            f'</div>'
            f'{detail}'
            f'</div>'
        )

    # 3. Detected but not connected → gray "Not Connected" badge with hints
    for d in detected:
        fam = d["family"]
        icon = FAMILY_ICONS.get(fam, "")
        label = _family_label(fam)
        color = FAMILY_COLORS.get(fam, "#64748b")
        display_name = d.get("display_name", label)

        badge = f'<div class="source-status source-status-disconnected">{t("sources.not_connected")}</div>'

        if fam == "ci":
            hint_text = _get_ci_hint(connected)
        elif isinstance(_source_hints.get(fam), str):
            hint_text = _source_hints[fam]
        else:
            evidence_str = "; ".join(d.get("evidence", [])[:2])
            hint_text = (
                f'Detected: {_esc(evidence_str)}. '
                f'Install <code>{_esc(d.get("adapter", ""))}</code> or check '
                f'<code>docs/guides/INTEGRATIONS.md</code> for setup.'
            )

        detail = f'<div class="source-detail">{hint_text}</div>'

        cards.append(
            f'<div class="source-card source-card-disconnected">'
            f'<div class="source-card-header">'
            f'<span class="source-icon" style="color: {color}; opacity: 0.5">{icon}</span>'
            f'<div>'
            f'<div class="source-name">{_esc(display_name)}</div>'
            f'{badge}'
            f'</div>'
            f'</div>'
            f'{detail}'
            f'</div>'
        )

    cards_html = "\n    ".join(cards)

    n_connected = len(connected_by_family)
    n_detected = len(detected)
    subtitle = t("sources.subtitle_connected", n=n_connected)
    if n_detected > 0:
        subtitle += t("sources.subtitle_available", n=n_detected)

    return (
        '<section class="sources-section">\n'
        f'  <h2>{t("sources.title")}</h2>\n'
        f'  <p class="sources-subtitle">{subtitle}</p>\n'
        '  <div class="sources-grid">\n'
        f'    {cards_html}\n'
        '  </div>\n'
        '</section>'
    )


def _build_adapters_section(active_families: list, sources_info: dict = None, is_pro: bool = False) -> str:
    """Build the 'Expand Your Coverage' section with adapter cards.

    Shows available adapters the user could enable and general setup guidance.
    Skips the "Currently Active" subsection since the Sources section handles that.
    """
    catalog = _load_adapter_catalog()
    universal_count = _load_universal_patterns_count()
    if not catalog:
        return ""

    active_set = set(active_families)
    # Normalize: "git" → "version_control"
    if "git" in active_set:
        active_set.add("version_control")

    # Also exclude families already shown in the sources section
    sources_families = set()
    if sources_info:
        for c in sources_info.get("connected", []):
            sources_families.add(c["family"])
        for d in sources_info.get("detected", []):
            sources_families.add(d["family"])
    # Normalize sources families
    if "git" in sources_families:
        sources_families.add("version_control")
    if "version_control" in sources_families:
        sources_families.add("git")
    shown_set = active_set | sources_families

    available_adapters = [a for a in catalog if a["status"] == "available"
                          and a.get("family") not in shown_set]
    planned_adapters = [a for a in catalog if a["status"] == "planned"]

    # Available adapter cards (can be enabled)
    available_cards = []
    for a in available_adapters:
        icon = FAMILY_ICONS.get(a["family"], "")
        label = _family_label(a["family"])
        color = FAMILY_COLORS.get(a["family"], "#64748b")
        token = a.get("token")
        is_pro_adapter = a.get("tier", 1) >= 2
        hint = ""
        if token:
            hint = (
                f'<div class="adapter-hint">Set <code>{_esc(token)}</code> '
                f'{_integrations_link()}</div>'
            )
        elif a["tier"] == 1:
            hint = f'<div class="adapter-hint">{t("sources.auto_detected")} {_integrations_link()}</div>'
        pro_badge = (
            '<div class="adapter-status-badge pro">Pro</div>'
            if is_pro_adapter and not is_pro else ""
        )
        available_cards.append(
            f'<div class="adapter-card adapter-available">'
            f'<div class="adapter-icon" style="color: {color}">{icon}</div>'
            f'<div class="adapter-name">{_esc(a["name"])}</div>'
            f'<div class="adapter-family">{_esc(label)}</div>'
            f'{pro_badge}'
            f'<div class="adapter-desc">{_esc(a["description"])}</div>'
            f'{hint}'
            f'</div>'
        )

    # Planned adapter summary
    planned_families = sorted(set(
        _family_label(a["family"]) for a in planned_adapters
    ))

    # If nothing to show, skip this section
    if not available_cards and not planned_families:
        return ""

    # Build the section
    parts = []
    parts.append('<section class="adapters-section page-break-before">')
    parts.append(f'  <h2>{t("adapters.title")}</h2>')

    # Universal patterns stat
    parts.append(
        '  <div class="adapters-intro">'
        f'    <p>{t("adapters.intro", n=universal_count)}</p>'
        '  </div>'
    )

    # Available adapters
    if available_cards:
        parts.append(f'  <h3>{t("adapters.available_title")}</h3>')
        parts.append(
            f'  <p class="adapters-subtitle">{t("adapters.available_subtitle")}</p>'
        )
        parts.append('  <div class="adapter-grid">')
        parts.extend(f'    {c}' for c in available_cards)
        parts.append('  </div>')

        # General setup guidance
        parts.append('  <div class="adapter-setup-guide">')
        parts.append(f'    <h4>{t("adapters.how_to_title")}</h4>')
        parts.append('    <ol>')
        parts.append(f'      <li>{t("adapters.step1")}</li>')
        parts.append(f'      <li>{t("adapters.step2")}</li>')
        parts.append(f'      <li>{t("adapters.step3")}</li>')
        parts.append(f'      <li>{t("adapters.step4")}</li>')
        parts.append('    </ol>')
        parts.append('  </div>')

    # Planned adapters teaser
    if planned_families:
        parts.append(
            '  <div class="adapters-planned">'
            f'    <strong>{t("adapters.coming_soon")}</strong> {", ".join(_esc(f) for f in planned_families)}'
            '  </div>'
        )

    parts.append('</section>')
    return '\n'.join(parts)


# ─── Prompt Builder ───


_BUILD_ARTIFACT_EXTS = {".map", ".d.ts", ".d.ts.map", ".js.map", ".css.map"}


def _is_build_artifact(path: str) -> bool:
    """Return True for generated/build artifact file paths."""
    for ext in _BUILD_ARTIFACT_EXTS:
        if path.endswith(ext):
            return True
    return False


def _build_prompt(scope, period_from, period_to, changes, commits, files,
                  timeline, patterns=None, full=False):
    lines = [
        f"Development drift analysis for {scope} ({period_from} to {period_to}).",
        "",
        "DEVIATIONS FROM BASELINE:",
        "",
    ]

    for c in changes:
        family = FAMILY_LABELS.get(c.get("family", ""), c.get("family", ""))
        metric = METRIC_LABELS.get(c.get("metric", ""), c.get("metric", ""))
        current = c.get("current", 0)
        normal = c.get("normal", {})
        median = normal.get("median", normal.get("mean", 0))
        dev = c.get("deviation_stddev", 0)
        d = "above" if dev >= 0 else "below"
        line = f"- {family} / {metric}: {_fmt_num(current)} (typical: {_fmt_num(median)}, {abs(dev):.1f}x {d})"
        if not full:
            line = f"- {family}: {metric} — {_fmt_num(median)} -> {_fmt_num(current)}"
        lines.append(line)

    if not full:
        lines.append("")
        lines.append(t("investigation.show_full_hint"))
        return "\n".join(lines)

    # Pattern risk context — only actionable patterns (skip healthy/informational)
    if patterns:
        actionable = [
            p for p in patterns
            if _severity_rank(pattern_risk_assessment(p)["severity"]) >= 2  # watch+
        ]
        if actionable:
            sorted_pats = sorted(
                actionable,
                key=lambda p: _severity_rank(pattern_risk_assessment(p)["severity"]),
                reverse=True,
            )
            lines.extend(["", "RISK PATTERNS (actionable only):", ""])

            # Group by (severity, impact), deduplicate descriptions within each group
            groups = {}
            group_order = []
            for p in sorted_pats:
                risk = pattern_risk_assessment(p)
                key = (risk["severity"], risk["impact"])
                if key not in groups:
                    groups[key] = []
                    group_order.append(key)
                groups[key].append(p)

            for key in group_order:
                group = groups[key]
                risk = pattern_risk_assessment(group[0])
                sev_label = risk["severity_display"]["label"]
                # Deduplicate descriptions within group
                seen_descs = []
                for p in group:
                    desc = p.get("description_semantic") or friendly_pattern(p)
                    if desc and desc not in seen_descs:
                        seen_descs.append(desc)
                if len(seen_descs) == 1:
                    lines.append(f"- [{sev_label}] {seen_descs[0]}")
                    if len(group) > 1:
                        lines.append(f"  ({len(group)} independent confirmations)")
                else:
                    lines.append(f"- [{sev_label}] {len(seen_descs)} patterns:")
                    for d in seen_descs:
                        lines.append(f"    * {d}")
                lines.append(f"  Impact: {risk['impact']}")
                lines.append(f"  Action: {risk['recommendation']}")
                lines.append("")

    # Evidence — commits
    if commits:
        lines.extend(["", f"COMMITS ({len(commits)}):", ""])
        for c in commits[:10]:
            sha = c.get("sha", "")[:8]
            msg = c.get("message", "").split("\n")[0][:80]
            n_files = len(c.get("files_changed", []))
            lines.append(f"  {sha} — {msg} ({n_files} files)")
        if len(commits) > 10:
            lines.append(f"  ... and {len(commits) - 10} more")
        lines.append("")

    # Evidence — source files only (skip build artifacts)
    if files:
        source_files = [f for f in files if not _is_build_artifact(f.get("path", ""))]
        if source_files:
            lines.append(f"SOURCE FILES CHANGED ({len(source_files)}):")
            lines.append("")
            for f in source_files[:20]:
                path = f.get("path", "")
                ct = f.get("change_type", "")
                lines.append(f"  - {path} ({ct})")
            if len(source_files) > 20:
                lines.append(f"  ... and {len(source_files) - 20} more")
            lines.append("")

    lines.extend([
        "TASKS:",
        "",
        "1. ROOT CAUSE: For each deviation, identify the commit(s) that caused it.",
        "   Focus on [Action Required] and [Needs Attention] items first.",
        "",
        "2. FIXES: Provide concrete fixes with file paths and code changes.",
        "   Goal: bring metrics back toward baseline without disrupting velocity.",
        "",
        "3. PRIORITY: Rank fixes by urgency (immediate vs. next sprint).",
        "",
        "4. AFTER FIXING: Run `evo analyze . --verify` to confirm deviations decreased.",
        "   If a change was intentional, accept it: `evo accept . <N>`.",
        "",
        "5. FINDING SUMMARIES: At the end, include a section like this:",
        "   ## Finding Summaries",
        "   - [family/metric]: One plain-English sentence for a non-technical reader.",
        "   (This lets the user run `evo enrich . --from response.txt` to store friendly descriptions.)",
    ])

    return "\n".join(lines)


# ─── Helpers ───


def _fmt_value(v) -> str:
    """Format a metric value for human-readable display."""
    if v is None:
        return "\u2014"
    if isinstance(v, (int, float)) and float(v) == int(v) and abs(v) < 1e9:
        return f"{int(v):,}"
    if isinstance(v, float):
        if abs(v) >= 100:
            return f"{v:,.0f}"
        return f"{v:.2f}"
    return str(v)


def _value_near_baseline(latest_value, normal_dict: dict,
                         threshold: float = 1.5) -> bool:
    """Check if the latest observed value is close to the global baseline."""
    if latest_value is None or not normal_dict:
        return True  # fallback: assume returned
    median = normal_dict.get("median")
    if median is None:
        return True
    mad = normal_dict.get("mad", 0)
    if mad and mad > 0:
        modified_z = abs(0.6745 * (latest_value - median) / mad)
        return modified_z < threshold
    stddev = normal_dict.get("stddev", 0)
    if stddev and stddev > 0:
        z = abs((latest_value - median) / stddev)
        return z < threshold
    return latest_value == median


def _esc(text: str) -> str:
    """HTML-escape a string (attribute-safe)."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _fmt_num(n) -> str:
    """Format a number for display."""
    if isinstance(n, int):
        return f"{n:,}"
    if isinstance(n, float):
        if abs(n) >= 100:
            return f"{n:,.1f}"
        if abs(n) >= 1:
            return f"{n:.2f}"
        return f"{n:.4f}"
    return str(n)


def _format_date(iso_str: str) -> str:
    """Format ISO date to readable form."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except (ValueError, TypeError):
        return iso_str[:16] if len(iso_str) > 16 else iso_str


def _bar_widths(current, median):
    """Calculate percentage widths for the bar chart (normal_w, current_w)."""
    try:
        abs_c = abs(float(current))
    except (TypeError, ValueError):
        abs_c = 0
    try:
        abs_m = abs(float(median))
    except (TypeError, ValueError):
        abs_m = 0
    mx = max(abs_c, abs_m, 0.001)
    return round(abs_m / mx * 100), round(abs_c / mx * 100)


def _deviation_class(dev):
    """CSS class for a deviation value."""
    a = abs(dev)
    if a >= 4.0:
        return "deviation-high"
    if a >= 2.0:
        return "deviation-medium"
    return "deviation-low"


# ─── CSS ───

_CSS = """:root {
  --color-primary: #0A4D4A;
  --color-primary-light: #0F6B67;
  --color-secondary: #2CA58D;
  --color-accent: #FF6B6B;
  --color-text: #1f2937;
  --color-text-muted: #64748B;
  --color-border: #E2E8F0;
  --color-bg: #FFFFFF;
  --color-bg-subtle: #F8FAFC;
  --color-success: #2CA58D;
  --color-warning: #F59E0B;
  --color-danger: #EF4444;
  --color-info: #06B6D4;
  --color-normal: #94a3b8;
  --color-current: #2CA58D;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 11pt; line-height: 1.6; color: var(--color-text);
  background: var(--color-bg); max-width: 1200px; margin: 0 auto; padding: 2em;
}
h1, h2, h3 { font-weight: 700; color: var(--color-primary); }
h1 { font-size: 28pt; margin-bottom: 0.5em; }
h2 { font-size: 18pt; margin-top: 1.5em; margin-bottom: 0.75em;
  border-bottom: 2px solid var(--color-border); padding-bottom: 0.5em; }
h3 { font-size: 14pt; margin-top: 1em; margin-bottom: 0.5em; }
code, pre { font-family: 'SF Mono', 'Monaco', 'Courier New', monospace; font-size: 10pt; }
code { background: var(--color-bg-subtle); padding: 0.2em 0.4em; border-radius: 4px; }
pre { background: var(--color-bg-subtle); padding: 1em; border-radius: 8px;
  overflow-x: auto; border: 1px solid var(--color-border); }
.logo { width: 48px; height: 56px; margin-bottom: 1em; }
.cover-page { min-height: 80vh; display: flex; flex-direction: column;
  justify-content: center; align-items: center; text-align: center; }
.cover-page h1 { font-size: 42pt; margin-bottom: 0.5em; }
.cover-brand { font-size: 18pt; color: var(--color-secondary); font-weight: 600;
  margin-bottom: 2em; }
.cover-metadata { font-size: 12pt; color: var(--color-text-muted); line-height: 2; }
.cover-metadata p { margin: 0.5em 0; }
.cover-metadata strong { color: var(--color-text); margin-right: 0.5em; }
.executive-summary { margin-top: 2em; }
.summary-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5em; margin: 1.5em 0; }
.summary-card { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  border-radius: 8px; padding: 1.5em; text-align: center; }
.summary-value { font-size: 32pt; font-weight: 700; color: var(--color-primary);
  margin-bottom: 0.25em; }
.summary-label { font-size: 11pt; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; }
.summary-families { margin-top: 1em; padding: 1em; background: var(--color-bg-subtle);
  border-radius: 8px; border-left: 4px solid var(--color-secondary); }
.key-findings { margin-top: 1.5em; }
.findings-list { list-style: none; padding: 0; }
.findings-list li { padding: 0.75em 1em; margin-bottom: 0.5em; background: var(--color-bg-subtle);
  border-left: 3px solid var(--color-secondary); border-radius: 0 6px 6px 0; line-height: 1.5; }
.findings-list li strong { color: var(--color-primary); }
.change-card { border: 1px solid var(--color-border); border-left: 4px solid var(--color-secondary);
  padding: 1.5em; margin-bottom: 1.5em; background: var(--color-bg-subtle);
  border-radius: 8px; page-break-inside: avoid; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.change-card-accepted { opacity: 0.6; border-left-color: var(--color-success) !important; }
.accepted-badge { margin-left: auto; padding: 0.2em 0.75em; border-radius: 12px;
  background: #d1fae5; color: #065f46; font-size: 9pt; font-weight: 600;
  white-space: nowrap; }
.accepted-summary { display: flex; gap: 0.75em; align-items: flex-start; padding: 1em 1.25em;
  background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 3px solid #16a34a;
  border-radius: 0 8px 8px 0; margin-bottom: 1.5em; font-size: 10pt; }
.accepted-summary-icon { color: #16a34a; font-size: 14pt; font-weight: 700; line-height: 1; }
.accepted-summary-hint { font-size: 9pt; color: var(--color-text-muted); margin-top: 0.3em; }
.change-card.deviation-high { border-left-color: var(--color-danger); }
.change-card.deviation-medium { border-left-color: var(--color-warning); }
.change-card.deviation-low { border-left-color: var(--color-success); }
.change-card-header { display: flex; align-items: center; margin-bottom: 1em; }
.family-icon { font-size: 24pt; margin-right: 0.5em; }
.metric-name { font-size: 14pt; font-weight: 600; color: var(--color-primary); }
.family-label { font-size: 10pt; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; }
.user-friendly-summary { background: #fff; padding: 1em; border-radius: 6px;
  margin-bottom: 1em; border: 1px solid var(--color-border); }
.user-friendly-summary strong { color: var(--color-primary); }
.bar-chart { margin: 1em 0; }
.bar-chart-row { display: flex; align-items: center; margin-bottom: 0.5em; }
.bar-label { width: 100px; font-size: 10pt; color: var(--color-text-muted);
  text-align: right; padding-right: 1em; }
.bar-container { flex: 1; height: 24px; background: var(--color-border);
  border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--color-current); border-radius: 4px 0 0 4px; }
.bar-fill.normal { background: var(--color-normal); }
.bar-value { margin-left: 1em; font-weight: 600; white-space: nowrap; min-width: 80px; }
.deviation-badge { display: inline-block; background: var(--color-secondary); color: white;
  padding: 0.25em 0.75em; border-radius: 4px; font-size: 9pt; font-weight: 600;
  margin-top: 0.5em; }
.technical-detail { margin-top: 0.5em; padding-top: 0.5em;
  border-top: 1px dashed var(--color-border); font-size: 9pt;
  color: var(--color-text-muted); font-style: italic; }
.technical-detail summary { cursor: pointer; color: var(--color-secondary); font-weight: 500; }
.technical-detail summary:hover { text-decoration: underline; }
.pattern-card { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  border-radius: 8px; padding: 1.5em; margin-bottom: 1.5em; }
.inline-patterns { margin-top: 1em; border-top: 1px dashed var(--color-border); padding-top: 0.75em; }
.inline-patterns-header { font-weight: 600; font-size: 9pt; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5em; }
.inline-pattern { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  border-radius: 6px; padding: 0.75em 1em; margin-bottom: 0.5em; }
.inline-pattern-desc { font-size: 10pt; margin: 0.5em 0; color: var(--color-text); }
.inline-pattern .pattern-recommendation { font-size: 9pt; margin-top: 0.5em; }
.inline-pattern .pattern-impact { font-size: 9pt; margin: 0.5em 0; padding: 0.75em; }
.inline-pattern .severity-badge { font-size: 8pt; }
.inline-patterns-overflow summary { font-size: 9pt; color: var(--color-text-muted);
  cursor: pointer; margin: 0.5em 0; }
.inline-patterns-overflow summary:hover { text-decoration: underline; }
.severity-badge { display: inline-block; padding: 0.25em 0.75em; border-radius: 4px;
  font-weight: 600; font-size: 9pt; margin-left: 0.5em; }
.severity-badge.severity-critical { background: #dc2626; color: white; }
.severity-badge.severity-concern { background: #ea580c; color: white; }
.severity-badge.severity-watch { background: #d97706; color: white; }
.severity-badge.severity-info { background: #0284c7; color: white; }
.severity-badge.severity-positive { background: #16a34a; color: white; }
.pattern-impact { background: #fff; padding: 1em; border-radius: 6px;
  margin: 0.75em 0; border: 1px solid var(--color-border); }
.pattern-recommendation { padding: 0.75em 1em; border-radius: 6px;
  background: var(--color-bg-subtle); border-left: 3px solid var(--color-secondary);
  font-size: 10pt; margin-top: 0.5em; }
.severity-border-critical { border-left: 4px solid #dc2626 !important; }
.severity-border-concern { border-left: 4px solid #ea580c !important; }
.severity-border-watch { border-left: 4px solid #d97706 !important; }
.severity-border-info { border-left: 4px solid #0284c7 !important; }
.severity-border-positive { border-left: 4px solid #16a34a !important; }
.risk-banner { padding: 1.5em; border-radius: 8px; margin-bottom: 1.5em; }
.risk-banner-title { font-size: 14pt; font-weight: 700; margin-bottom: 0.5em; }
.risk-banner p { margin-bottom: 0.75em; line-height: 1.6; }
.risk-banner-chips { display: flex; gap: 0.75em; flex-wrap: wrap; margin-top: 0.5em; }
.severity-chip { display: inline-flex; align-items: center; gap: 0.25em; padding: 0.3em 0.75em;
  border-radius: 4px; font-size: 9pt; font-weight: 600; background: rgba(255,255,255,0.7); }
.risk-banner-critical { background: #fef2f2; border: 2px solid #dc2626;
  border-left: 6px solid #dc2626; }
.risk-banner-critical .risk-banner-title { color: #991b1b; }
.risk-banner-concern { background: #fff7ed; border: 2px solid #ea580c;
  border-left: 6px solid #ea580c; }
.risk-banner-concern .risk-banner-title { color: #9a3412; }
.risk-banner-watch { background: #fffbeb; border: 2px solid #d97706;
  border-left: 6px solid #d97706; }
.risk-banner-watch .risk-banner-title { color: #92400e; }
.risk-banner-info { background: #f0f9ff; border: 2px solid #0284c7;
  border-left: 6px solid #0284c7; }
.risk-banner-info .risk-banner-title { color: #075985; }
.risk-banner-positive { background: #f0fdf4; border: 2px solid #16a34a;
  border-left: 6px solid #16a34a; }
.risk-banner-positive .risk-banner-title { color: #166534; }
.patterns-dedup-note { font-size: 9pt; color: var(--color-text-muted); margin-bottom: 0.75em; }
.pattern-guidance { background: var(--color-bg-subtle); padding: 1.25em 1.5em;
  border-radius: 8px; margin-bottom: 1.5em; border: 1px solid var(--color-border);
  font-size: 10pt; line-height: 1.7; }
.pattern-guidance p { margin-bottom: 0.75em; }
.pattern-guidance p:last-child { margin-bottom: 0; }
.pattern-guidance .severity-badge { font-size: 8pt; vertical-align: middle; }
.investigation-expectations { background: var(--color-bg-subtle); padding: 1.25em 1.5em;
  border-radius: 8px; margin-bottom: 1.5em; border: 1px solid var(--color-border); }
.investigation-expectations h4 { color: var(--color-primary); margin-bottom: 0.75em; }
.investigation-expectations ul { list-style: none; padding: 0; }
.investigation-expectations li { padding: 0.5em 0; padding-left: 1.5em; position: relative;
  line-height: 1.6; }
.investigation-expectations li:before { content: '\\2192'; position: absolute; left: 0;
  color: var(--color-secondary); font-weight: 700; }
.pattern-group-count { display: inline-block; padding: 0.2em 0.6em; border-radius: 4px;
  font-size: 9pt; font-weight: 600; color: var(--color-text-muted);
  background: var(--color-border); margin-left: 0.5em; }
.grouped-pattern-list { list-style: disc; padding-left: 1.5em; margin: 0.5em 0 1em 0;
  font-size: 10pt; line-height: 1.7; }
.grouped-pattern-list li { margin-bottom: 0.3em; }
.pattern-meta { display: flex; gap: 1em; margin: 0.5em 0 1em 0;
  font-size: 10pt; color: var(--color-text-muted); }
.badge { background: var(--color-primary); color: white; padding: 0.25em 0.75em;
  border-radius: 4px; font-weight: 600; text-transform: uppercase; font-size: 9pt; }
.investigation-section { background: #fff; border: 2px solid var(--color-secondary);
  border-radius: 8px; padding: 2em; margin: 2em 0; }
.next-steps-header { display: flex; align-items: center; gap: 0.5em; margin-bottom: 1em; }
.next-steps-flow { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1em;
  margin: 1em 0; }
.step-card { display: flex; gap: 0.75em; padding: 1em; background: var(--color-bg-subtle);
  border: 1px solid var(--color-border); border-radius: 8px; }
.step-number { width: 32px; height: 32px; min-width: 32px; border-radius: 50%;
  background: var(--color-secondary); color: white; display: flex; align-items: center;
  justify-content: center; font-weight: 700; font-size: 14pt; }
.step-title { font-weight: 700; color: var(--color-primary); margin-bottom: 0.3em; }
.step-content p { font-size: 9pt; color: var(--color-text-muted); line-height: 1.5; margin: 0; }
.step-content code { font-size: 8.5pt; }
@media (max-width: 768px) {
  .next-steps-flow { grid-template-columns: 1fr; }
}
.action-buttons { display: flex; gap: 1em; margin: 1em 0; flex-wrap: wrap; }
.btn { padding: 0.75em 1.5em; border-radius: 6px; font-weight: 600; font-size: 10pt;
  cursor: pointer; border: none; transition: all 250ms ease-out; }
.btn-primary { background: var(--color-accent); color: white; }
.btn-primary:hover { background: #FF5252; }
.btn-secondary { background: var(--color-secondary); color: white; }
.btn-secondary:hover { background: var(--color-primary-light); }
.prompt-preview { background: #f8f9fa; border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-secondary); padding: 1em; border-radius: 6px;
  margin: 1em 0; font-size: 9pt; line-height: 1.6; max-height: 200px;
  overflow-y: auto; white-space: pre-wrap; font-family: 'SF Mono', monospace; }
.prompt-full { display: none; background: #f8f9fa; border: 1px solid var(--color-border);
  padding: 1.5em; border-radius: 6px; margin: 1em 0; white-space: pre-wrap;
  font-size: 10pt; line-height: 1.6; font-family: 'SF Mono', monospace; }
.prompt-full.show { display: block; }
.toggle-btn { background: white; border: 1px solid var(--color-secondary);
  color: var(--color-secondary); padding: 0.5em 1em; border-radius: 6px;
  cursor: pointer; font-weight: 600; font-size: 10pt; }
.toggle-btn:hover { background: var(--color-bg-subtle); }
.toggle-btn.active { background: var(--color-secondary); color: white; }
.empty { color: var(--color-text-muted); font-style: italic; text-align: center; padding: 2rem; }
.more { font-size: 9pt; color: var(--color-text-muted); margin-top: 0.5em; font-style: italic; }
.evidence-overflow { display: none; }
.evidence-overflow.show { display: table-row-group; }
div.evidence-overflow { display: none; }
div.evidence-overflow.show { display: block; }
.pattern-overflow { margin-top: 0.5em; }
.pattern-overflow > summary { list-style: none; display: inline-block; margin-top: 0.5em; }
.pattern-overflow > summary::-webkit-details-marker { display: none; }
.severity-filters { display: flex; gap: 0.5em; margin-bottom: 1.5em; flex-wrap: wrap; }
.btn-filter { background: white; border: 1px solid var(--color-border); color: var(--color-text);
  padding: 0.5em 1em; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 10pt;
  transition: all 250ms ease-out; }
.btn-filter:hover { background: var(--color-bg-subtle); border-color: var(--color-secondary); }
.btn-filter.active { background: var(--color-secondary); color: white;
  border-color: var(--color-secondary); }
.change-actions { display: flex; gap: 0.5em; margin-top: 0.75em; align-items: flex-start; }
.btn-action { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  color: var(--color-primary); padding: 0.4em 1em; border-radius: 6px; cursor: pointer;
  font-weight: 600; font-size: 9pt; transition: all 250ms ease-out; }
.btn-action:hover { background: var(--color-secondary); color: white;
  border-color: var(--color-secondary); }
.accept-group { position: relative; }
.accept-menu { display: none; position: absolute; top: 100%; left: 0; margin-top: 4px;
  background: white; border: 1px solid var(--color-border); border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1); z-index: 10; min-width: 200px; }
.accept-menu.show { display: block; }
.accept-menu button { display: block; width: 100%; text-align: left; padding: 0.6em 1em;
  border: none; background: none; cursor: pointer; font-size: 9pt; color: var(--color-text); }
.accept-menu button:hover { background: var(--color-bg-subtle); }
.accept-menu button:first-child { border-radius: 6px 6px 0 0; }
.accept-menu button:last-child { border-radius: 0 0 6px 6px; }
.accept-hint { display: block; font-size: 8pt; color: var(--color-text-muted); font-weight: 400; }
.btn-accept.accepted { background: var(--color-success); color: white;
  border-color: var(--color-success); pointer-events: none; }
.btn-fix { color: var(--color-secondary); }
.fix-prompt-panel { display: none; margin-top: 0.75em; background: var(--color-bg-subtle);
  border: 1px solid var(--color-border); border-radius: 8px; padding: 1em; }
.fix-prompt-panel.show { display: block; }
.fix-prompt-header { display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 0.5em; }
.fix-prompt-text { background: white; border: 1px solid var(--color-border);
  border-radius: 6px; padding: 0.75em; font-size: 9pt; white-space: pre-wrap;
  word-break: break-word; max-height: 200px; overflow-y: auto; margin: 0; }
.btn-copy-sm { background: var(--color-secondary); color: white; border: none;
  padding: 0.3em 0.8em; border-radius: 4px; cursor: pointer; font-size: 8pt;
  font-weight: 600; }
.btn-copy-sm:hover { opacity: 0.85; }
.fix-prompt-guide { margin-top: 0.5em; font-size: 8pt; color: var(--color-text-muted);
  display: flex; gap: 1em; flex-wrap: wrap; }
.fix-prompt-guide span { background: white; padding: 0.2em 0.5em; border-radius: 4px;
  border: 1px solid var(--color-border); }
.fix-next-steps { margin-top: 0.75em; padding: 0.75em 1em; background: white;
  border: 1px solid var(--color-border); border-left: 3px solid var(--color-secondary);
  border-radius: 0 6px 6px 0; font-size: 9pt; }
.fix-next-steps strong { color: var(--color-primary); }
.fix-next-steps ol { margin: 0.4em 0 0 1.25em; line-height: 1.8; }
.fix-next-steps code { font-size: 8pt; }
.progress-tracker { display: flex; align-items: center; gap: 0.75em;
  margin-bottom: 1em; font-size: 10pt; font-weight: 600; color: var(--color-text-muted); }
.progress-bar { flex: 1; max-width: 200px; height: 6px; background: var(--color-border);
  border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-success); border-radius: 3px;
  transition: width 300ms ease-out; }
.commit-attribution { font-size: 9pt; color: var(--color-text-muted); margin-top: 0.5em; }
.commit-link { color: var(--color-secondary); text-decoration: none; }
.commit-link:hover { text-decoration: underline; }
.confidence-note { font-size: 9pt; color: var(--color-text-muted); margin-top: 0.5em;
  font-style: italic; }
.change-card.filter-hidden { display: none; }
.ide-link { font-size: 8pt; color: var(--color-secondary); text-decoration: none;
  margin-left: 0.5em; font-weight: 600; }
.ide-link:hover { text-decoration: underline; }
.verification-banner { padding: 1.5em; border-radius: 8px; margin: 1.5em 0; }
.verify-all-clear { background: #f0fdf4; border: 2px solid #16a34a; }
.verify-improving { background: #eff6ff; border: 2px solid #2563eb; }
.verify-no-change { background: #fefce8; border: 2px solid #ca8a04; }
.verify-header { display: flex; align-items: center; gap: 0.75em; margin-bottom: 1em; }
.verify-icon { font-size: 24pt; }
.verify-title { font-size: 14pt; font-weight: 700; color: var(--color-primary); }
.verify-subtitle { font-size: 10pt; color: var(--color-text-muted); }
.verify-chips { display: flex; gap: 0.5em; flex-wrap: wrap; margin-bottom: 1em; }
.verify-chip { display: inline-flex; align-items: center; gap: 0.25em; padding: 0.3em 0.75em;
  border-radius: 4px; font-size: 9pt; font-weight: 600; }
.verify-chip-resolved { background: #dcfce7; color: #166534; }
.verify-chip-improving { background: #dbeafe; color: #1e40af; }
.verify-chip-flat { background: #f5f5f4; color: #57534e; }
.verify-chip-new { background: #fef3c7; color: #92400e; }
.verify-table { width: 100%; border-collapse: collapse; font-size: 10pt; }
.verify-table th { text-align: left; padding: 0.5em 0.75em; font-weight: 600;
  color: var(--color-primary); border-bottom: 2px solid var(--color-border); }
.verify-table td { padding: 0.5em 0.75em; border-bottom: 1px solid var(--color-border); }
.verify-resolved td { color: #166534; }
.verify-trend-good { color: #2563eb; font-weight: 600; }
.verify-trend-flat { color: #78716c; }
.verify-note { margin-top: 1em; padding: 0.75em 1em; background: #f8fafc;
  border-left: 3px solid var(--color-info); font-size: 10pt; color: var(--color-text-muted);
  border-radius: 0 4px 4px 0; line-height: 1.5; }
.verify-trend-warn { color: #dc2626; font-weight: 600; }
.verify-trend-stabilized { color: #dc6803; font-weight: 600; }
.verify-note-stabilized { margin-top: 1em; padding: 0.75em 1em; background: #fffbeb;
  border-left: 3px solid #f59e0b; font-size: 10pt; color: #92400e;
  border-radius: 0 4px 4px 0; line-height: 1.5; }
.verify-note-warn { margin-top: 1em; padding: 0.75em 1em; background: #fef2f2;
  border-left: 3px solid #dc2626; font-size: 10pt; color: #991b1b;
  border-radius: 0 4px 4px 0; line-height: 1.5; }
.trend-subtitle { font-size: 9pt; margin-top: 0.25em; color: #78716c; }
.trend-returning { color: #166534; }
.trend-elevated { color: #dc6803; }
.verify-baseline { color: var(--color-text-muted); font-size: 9pt; }
.verify-new td { color: #92400e; }
.page-break-before { page-break-before: always; }
.page-break-after { page-break-after: always; }
footer { margin-top: 4em; padding-top: 2em; border-top: 1px solid var(--color-border);
  text-align: center; color: var(--color-text-muted); font-size: 9pt; }
footer strong { color: var(--color-secondary); }
/* ─── Sources Section ─── */
.sources-section { margin-top: 1.5em; }
.sources-subtitle { color: var(--color-text-muted); margin-bottom: 1em; }
.sources-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1em; margin: 1em 0 1.5em; }
.source-card { border: 1px solid var(--color-border); border-radius: 8px;
  padding: 1.2em; background: var(--color-bg); border-left: 3px solid var(--color-success);
  transition: box-shadow 0.2s; }
.source-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.source-card-disconnected { border-left-color: var(--color-border); background: var(--color-bg-subtle); }
.source-card-header { display: flex; align-items: flex-start; gap: 0.75em; }
.source-icon { font-size: 20pt; line-height: 1; }
.source-name { font-weight: 600; font-size: 11pt; color: var(--color-primary); }
.source-adapter { font-size: 8.5pt; color: var(--color-text-muted); margin-top: 1px; }
.source-status { display: inline-block; padding: 0.15em 0.6em; border-radius: 12px;
  font-size: 8pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;
  margin-top: 0.2em; }
.source-status-active { background: #d1fae5; color: #065f46; }
.source-status-quiet { background: #dbeafe; color: #1e40af; }
.source-status-hint { background: #fef3c7; color: #92400e; }
.source-status-warn { background: #fed7aa; color: #9a3412; }
.source-status-disconnected { background: #f1f5f9; color: #64748b; }
.source-status-pro { background: linear-gradient(135deg, #7c3aed, #a855f7); color: white; }
.source-detail { margin-top: 0.75em; font-size: 9pt; color: var(--color-text-muted);
  line-height: 1.5; }
.source-detail code { font-size: 8.5pt; background: #e0f2fe; color: #0369a1;
  padding: 0.15em 0.4em; border-radius: 3px; }
.source-hint-cmd { margin-top: 0.5em; }
.source-doc-link { color: var(--color-secondary); font-weight: 600; text-decoration: none;
  font-size: 9pt; }
.source-doc-link:hover { text-decoration: underline; }
/* ─── Adapters Section ─── */
.adapters-section { margin-top: 2em; }
.adapters-intro { padding: 1em 1.5em; background: var(--color-bg-subtle);
  border-left: 4px solid var(--color-secondary); border-radius: 0 8px 8px 0;
  margin-bottom: 1.5em; }
.adapters-intro p { margin: 0; }
.adapters-subtitle { color: var(--color-text-muted); margin-bottom: 1em; }
.adapter-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1em; margin: 1em 0 1.5em; }
.adapter-card { border: 1px solid var(--color-border); border-radius: 8px;
  padding: 1.2em; background: var(--color-bg); position: relative;
  transition: box-shadow 0.2s; }
.adapter-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.adapter-active { border-left: 3px solid var(--color-success); }
.adapter-available { border-left: 3px solid var(--color-info); }
.adapter-icon { font-size: 20pt; margin-bottom: 0.3em; }
.adapter-name { font-weight: 600; font-size: 11pt; color: var(--color-primary); }
.adapter-family { font-size: 9pt; color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5em; }
.adapter-desc { font-size: 9pt; color: var(--color-text-muted); line-height: 1.4;
  margin-bottom: 0.5em; }
.adapter-hint { font-size: 9pt; color: var(--color-info); }
.adapter-hint code { font-size: 8.5pt; background: #e0f2fe; color: #0369a1;
  padding: 0.15em 0.4em; border-radius: 3px; }
.adapter-status-badge { font-size: 8pt; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; padding: 0.2em 0.6em; border-radius: 12px;
  position: absolute; top: 1em; right: 1em; }
.adapter-status-badge.active { background: #d1fae5; color: #065f46; }
.adapter-status-badge.pro { background: linear-gradient(135deg, #7c3aed, #a855f7); color: white;
  position: static; display: inline-block; margin-top: 0.3em; }
.adapter-setup-guide { background: var(--color-bg-subtle); border: 1px solid var(--color-border);
  border-radius: 8px; padding: 1.5em; margin: 1.5em 0; }
.adapter-setup-guide h4 { margin-top: 0; margin-bottom: 0.75em;
  color: var(--color-primary); font-size: 12pt; }
.adapter-setup-guide ol { padding-left: 1.5em; }
.adapter-setup-guide li { margin-bottom: 0.75em; line-height: 1.5; }
.adapters-planned { padding: 1em 1.5em; background: var(--color-bg-subtle);
  border-radius: 8px; color: var(--color-text-muted); font-size: 10pt;
  margin-top: 1em; }
@media print {
  body { font-size: 10pt; padding: 0; }
  .btn, .toggle-btn, .action-buttons { display: none !important; }
  .prompt-full { display: block !important; }
  details.pattern-overflow > summary { display: none !important; }
  details.pattern-overflow > summary ~ * { display: block !important; }
  details[open] summary ~ * { display: block; }
  .no-print { display: none; }
  .cover-page { min-height: auto; padding: 4em 0; }
}"""

# ─── JS ───

_JS = """<script>
// Clipboard helper — works on file:// URLs where navigator.clipboard is blocked
function _copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  // Fallback for file:// protocol
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);
  return Promise.resolve();
}
function _flashBtn(btn, label, duration) {
  var orig = btn.textContent;
  btn.textContent = label;
  btn.style.background = 'var(--color-success)';
  btn.style.color = 'white';
  btn.style.borderColor = 'var(--color-success)';
  setTimeout(function() {
    btn.textContent = orig;
    btn.style.background = '';
    btn.style.color = '';
    btn.style.borderColor = '';
  }, duration || 2000);
}
function copyPrompt() {
  var el = document.getElementById('fullPrompt');
  if (!el) return;
  _copyText(el.textContent).then(function() {
    _flashBtn(document.getElementById('copyBtn'), 'Copied!');
  });
}
function savePromptToFile() {
  var el = document.getElementById('fullPrompt');
  if (!el) return;
  var blob = new Blob([el.textContent], { type: 'text/plain' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url; a.download = 'investigation_prompt.txt';
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}
function togglePrompt() {
  var f = document.getElementById('fullPrompt');
  var b = document.getElementById('togglePromptBtn');
  if (!f || !b) return;
  f.classList.toggle('show'); b.classList.toggle('active');
  b.textContent = f.classList.contains('show') ? 'Hide Full Prompt' : 'Show Full Prompt';
}
function toggleTableRows(id, btn) {
  var el = document.getElementById(id);
  if (!el || !btn) return;
  el.classList.toggle('show');
  btn.classList.toggle('active');
  if (el.classList.contains('show')) {
    btn.textContent = 'Collapse';
  } else {
    btn.textContent = btn.getAttribute('data-label') || 'Show all';
  }
}
function copyCommand(btn, cmd) {
  var text = cmd.replace(/&quot;/g, '"');
  _copyText(text).then(function() { _flashBtn(btn, 'Copied!'); });
}
function toggleAcceptMenu(idx) {
  var menu = document.getElementById('accept-menu-' + idx);
  if (!menu) return;
  document.querySelectorAll('.accept-menu.show').forEach(function(m) {
    if (m !== menu) m.classList.remove('show');
  });
  menu.classList.toggle('show');
}
function _markAccepted(idx) {
  var menu = document.getElementById('accept-menu-' + idx);
  if (menu) menu.classList.remove('show');
  var actions = document.getElementById('actions-' + idx);
  if (actions) {
    var btn = actions.querySelector('.btn-accept');
    if (btn) {
      btn.textContent = 'Accepted \u2713';
      btn.classList.add('accepted');
    }
  }
  updateProgress();
}
function _showToast(msg) {
  var existing = document.getElementById('report-toast');
  if (existing) existing.remove();
  var t = document.createElement('div');
  t.id = 'report-toast';
  t.style.cssText = 'position:fixed;bottom:2em;right:2em;background:#0A4D4A;color:white;padding:0.75em 1.5em;border-radius:8px;font-weight:500;z-index:1000;opacity:0;transition:opacity 0.3s;';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function() { t.style.opacity = '1'; }, 10);
  setTimeout(function() { t.style.opacity = '0'; setTimeout(function() { t.remove(); }, 300); }, 2500);
}
function acceptFinding(idx, scope, cmd) {
  var changeIndex = idx + 1;
  fetch('/api/accept', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({index: changeIndex, scope: scope, reason: 'Expected behavior'})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) { _markAccepted(idx); _showToast('Accepted'); })
  .catch(function() {
    var text = cmd.replace(/&quot;/g, '"');
    _copyText(text).then(function() {
      _markAccepted(idx);
      _showToast('Command copied \u2014 paste in terminal to accept');
    });
  });
}
function updateProgress() {
  var total = document.querySelectorAll('.btn-accept').length;
  var resolved = document.querySelectorAll('.btn-accept.accepted').length;
  var counter = document.getElementById('resolvedCount');
  var fill = document.getElementById('progressFill');
  if (counter) counter.textContent = resolved;
  if (fill) fill.style.width = (total > 0 ? (resolved / total * 100) : 0) + '%';
}
function toggleFixPrompt(idx) {
  var panel = document.getElementById('fix-prompt-' + idx);
  if (panel) panel.classList.toggle('show');
}
function copyFixPrompt(idx) {
  var el = document.getElementById('fix-prompt-text-' + idx);
  if (!el) return;
  var text = el.textContent.replace(/\\\\n/g, '\\n');
  _copyText(text).then(function() {
    var btn = el.parentElement.querySelector('.btn-copy-sm');
    if (btn) {
      btn.textContent = 'Copied!';
      setTimeout(function() { btn.textContent = 'Copy'; }, 2000);
    }
  });
}
function filterChanges(level, btn) {
  var cards = document.querySelectorAll('.change-card');
  var buttons = document.querySelectorAll('.btn-filter');
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].classList.remove('active');
  }
  btn.classList.add('active');
  for (var j = 0; j < cards.length; j++) {
    if (level === 'all') {
      cards[j].classList.remove('filter-hidden');
    } else {
      if (cards[j].classList.contains(level)) {
        cards[j].classList.remove('filter-hidden');
      } else {
        cards[j].classList.add('filter-hidden');
      }
    }
  }
}
document.addEventListener('DOMContentLoaded', function() {
  var btns = document.querySelectorAll('button[onclick^="toggleTableRows"]');
  for (var i = 0; i < btns.length; i++) {
    btns[i].setAttribute('data-label', btns[i].textContent);
  }
  // Close accept menus when clicking outside
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.accept-group')) {
      document.querySelectorAll('.accept-menu.show').forEach(function(m) {
        m.classList.remove('show');
      });
    }
  });
  // Mark already-accepted items on page load (server mode only, silent fail on file://)
  fetch('/api/accepted')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var accepted = data.accepted || [];
      var cards = document.querySelectorAll('.change-card');
      cards.forEach(function(card, idx) {
        var id = card.id || '';
        for (var i = 0; i < accepted.length; i++) {
          var key = accepted[i].key || '';
          var parts = key.split(':');
          if (parts.length === 2 && id === 'change-' + parts[0] + '-' + parts[1]) {
            _markAccepted(idx);
            break;
          }
        }
      });
    })
    .catch(function() { /* file:// mode — ignore */ });
});
</script>"""
