"""
Jinja2 custom filters for report generation.
"""

from datetime import datetime
from typing import Any


def format_date(iso_string: str) -> str:
    """Convert ISO-8601 timestamp to human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%b %d, %Y at %I:%M %p')
    except (ValueError, AttributeError):
        return iso_string


def format_metric(value: float, metric: str) -> str:
    """Format metric value with appropriate units and precision."""
    # Rate metrics (as percentages)
    if 'rate' in metric or 'ratio' in metric:
        return f"{value * 100:.1f}%"
    
    # Count metrics (integers)
    if 'count' in metric or 'touched' in metric or metric == 'files_touched':
        return f"{int(value)}"
    
    # Duration metrics
    if 'duration' in metric:
        if value < 60:
            return f"{value:.1f}s"
        elif value < 3600:
            return f"{value / 60:.1f}min"
        else:
            return f"{value / 3600:.1f}h"
    
    # Decimal metrics
    return f"{value:.2f}"


def family_icon(family: str) -> str:
    """Return emoji icon for source family."""
    icons = {
        "git": "📝",
        "ci": "🔧",
        "testing": "🧪",
        "dependency": "📦",
        "schema": "📊",
        "deployment": "🚀",
        "config": "⚙️",
        "security": "🔒"
    }
    return icons.get(family, "📋")


def family_label(family: str) -> str:
    """Return human-readable family name."""
    labels = {
        "git": "Version Control",
        "ci": "CI / Build",
        "testing": "Testing",
        "dependency": "Dependencies",
        "schema": "API / Schema",
        "deployment": "Deployment",
        "config": "Configuration",
        "security": "Security"
    }
    return labels.get(family, family.title())


def metric_label(metric: str) -> str:
    """Return human-readable metric name."""
    labels = {
        "files_touched": "Files Changed",
        "dispersion": "Change Dispersion",
        "change_locality": "Change Locality",
        "cochange_novelty_ratio": "Co-change Novelty",
        "run_duration": "Build Duration",
        "job_count": "Job Count",
        "failure_rate": "Failure Rate",
        "total_tests": "Test Count",
        "skip_rate": "Skip Rate",
        "suite_duration": "Suite Duration",
        "dependency_count": "Total Dependencies",
        "direct_count": "Direct Dependencies",
        "max_depth": "Dependency Depth",
        "endpoint_count": "API Endpoints",
        "type_count": "API Types",
        "field_count": "API Fields",
        "schema_churn": "Schema Churn",
        "deploy_duration": "Deploy Duration",
        "is_rollback": "Rollback",
        "resource_count": "Resources",
        "resource_type_count": "Resource Types",
        "config_churn": "Config Churn",
        "vulnerability_count": "Vulnerabilities",
        "critical_count": "Critical Vulnerabilities",
        "fixable_ratio": "Fixable Ratio",
    }
    return labels.get(metric, metric.replace("_", " ").title())


def calc_bar_width(value: float, max_value: float) -> int:
    """Calculate bar width as percentage (0-100)."""
    if max_value == 0:
        return 0
    width = int((value / max_value) * 100)
    return min(max(width, 0), 100)


def deviation_class(deviation: float) -> str:
    """Return CSS class based on deviation magnitude."""
    abs_dev = abs(deviation)
    if abs_dev >= 5.0:
        return "deviation-high"
    elif abs_dev >= 2.0:
        return "deviation-medium"
    else:
        return "deviation-low"


def short_sha(sha: str) -> str:
    """Truncate git SHA to 8 characters."""
    return sha[:8] if sha else ""


def format_timestamp(iso_string: str) -> str:
    """Format timestamp for timeline (shorter format)."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%b %d, %H:%M')
    except (ValueError, AttributeError):
        return iso_string
