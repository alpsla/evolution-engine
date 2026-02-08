"""
Core report generation logic.
"""

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .filters import (
    calc_bar_width,
    deviation_class,
    family_icon,
    family_label,
    format_date,
    format_metric,
    format_timestamp,
    metric_label,
    short_sha,
)


class ReportGenerator:
    """Generates HTML reports from Phase 5 advisory JSON."""

    def __init__(self, template_dir: Path | None = None):
        """
        Initialize generator with template directory.

        Args:
            template_dir: Path to Jinja2 templates (default: built-in templates)
        """
        if template_dir is None:
            template_dir = Path(__file__).parent / "templates"

        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(['html', 'xml'])
        )

        # Register custom filters
        self.env.filters['format_date'] = format_date
        self.env.filters['format_metric'] = format_metric
        self.env.filters['family_icon'] = family_icon
        self.env.filters['family_label'] = family_label
        self.env.filters['metric_label'] = metric_label
        self.env.filters['calc_bar_width'] = calc_bar_width
        self.env.filters['deviation_class'] = deviation_class
        self.env.filters['short_sha'] = short_sha
        self.env.filters['format_timestamp'] = format_timestamp

    def generate(
        self,
        advisory_path: Path,
        output_path: Path,
        template_name: str = "default.html"
    ) -> None:
        """
        Generate HTML report from advisory JSON.

        Args:
            advisory_path: Path to Phase 5 advisory.json
            output_path: Path for output HTML file
            template_name: Template filename (default: default.html)
        """
        # Load advisory JSON
        with open(advisory_path, 'r', encoding='utf-8') as f:
            advisory = json.load(f)

        # Prepare context
        context = {
            "advisory": advisory,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator_version": "Evolution Engine v1.0",
                "report_type": "Advisory Report"
            }
        }

        # Render template
        template = self.env.get_template(template_name)
        html = template.render(context)

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"✅ Report generated: {output_path}")
