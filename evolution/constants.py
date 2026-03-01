"""
Shared constants for the Evolution Engine pipeline.

Centralises family-level mappings that are used across multiple phases
and the report generator so they stay in sync.
"""

# Phase 2 signal file names, keyed by family.
# Each phase engine iterates this dict to discover which signal files to load;
# missing files on disk are silently skipped.
SIGNAL_FILES = {
    "git": "git_signals.json",
    "ci": "ci_signals.json",
    "testing": "testing_signals.json",
    "coverage": "coverage_signals.json",
    "dependency": "dependency_signals.json",
    "schema": "schema_signals.json",
    "deployment": "deployment_signals.json",
    "config": "config_signals.json",
    "security": "security_signals.json",
    "error_tracking": "error_tracking_signals.json",
}

# Human-readable display names for signal families.
# The dict includes forward-looking families that don't have signal files
# yet (e.g. monitoring, incidents) so the report renderer never falls
# through to a raw key.
FAMILY_LABELS = {
    "git": "Version Control",
    "version_control": "Version Control",
    "ci": "CI / Build",
    "testing": "Testing",
    "coverage": "Code Coverage",
    "dependency": "Dependencies",
    "schema": "API / Schema",
    "deployment": "Deployment",
    "config": "Configuration",
    "security": "Security",
    "error_tracking": "Error Tracking",
    "monitoring": "Monitoring",
    "quality_gate": "Quality Gate",
    "security_scan": "Security Scan",
    "incidents": "Incidents",
    "work_items": "Work Items",
    "feature_flags": "Feature Flags",
}

# Human-readable display names for individual metrics.
# Used by Phase 5 advisory text and the HTML report generator.
METRIC_LABELS = {
    "files_touched": "Files Changed",
    "dispersion": "Change Dispersion",
    "change_locality": "Change Locality",
    "cochange_novelty_ratio": "Co-change Novelty",
    "run_duration": "Build Duration",
    "run_failed": "Build Failure",
    "total_tests": "Test Count",
    "skip_rate": "Skip Rate",
    "suite_duration": "Suite Duration",
    "line_rate": "Line Coverage",
    "branch_rate": "Branch Coverage",
    "dependency_count": "Total Dependencies",
    "max_depth": "Dependency Depth",
    "endpoint_count": "API Endpoints",
    "type_count": "API Types",
    "field_count": "API Fields",
    "schema_churn": "Schema Churn",
    "release_cadence_hours": "Release Cadence",
    "is_prerelease": "Pre-release",
    "asset_count": "Release Assets",
    "resource_count": "Resources",
    "resource_type_count": "Resource Types",
    "config_churn": "Config Churn",
    "vulnerability_count": "Vulnerabilities",
    "critical_count": "Critical Vulnerabilities",
    "fixable_ratio": "Fixable Ratio",
    "event_count": "Error Occurrences",
    "user_count": "Affected Users",
    "is_unhandled": "Unhandled Exception",
}
