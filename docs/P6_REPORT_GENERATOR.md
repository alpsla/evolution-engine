# Phase 6 — HTML/PDF Report Generator

> **Implementation Guide for Sonnet 4.5**
>
> This document specifies the design and implementation of the **HTML/PDF Report Generator** — a Jinja2-based rendering system that transforms Phase 5 advisory JSON into professional, print-ready reports for consulting engagements.

---

## 1. Purpose

The Report Generator exists to:

1. Transform Phase 5 advisory JSON into professional HTML reports
2. Enable print-to-PDF functionality (print-friendly CSS, no JavaScript)
3. Provide consulting-ready deliverables with clear visual hierarchy
4. Support both screen viewing and printed distribution

### Success Criterion

> **A consultant can run one command and generate a professional PDF report ready to deliver to a client within 30 seconds.**

---

## 2. Report Structure

### 2.1 Full Page Layout

The report MUST include these sections in order:

```
┌─────────────────────────────────────┐
│ 1. COVER PAGE                       │
│    - Project name                   │
│    - Advisory ID                    │
│    - Report period                  │
│    - Generation timestamp           │
│    - Evolution Engine logo/branding │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 2. EXECUTIVE SUMMARY                │
│    - Significant changes count      │
│    - Families affected              │
│    - Pattern matches found          │
│    - New observations count         │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 3. CHANGES DETECTED                 │
│    - Each change in a card layout   │
│    - Family icon + Metric name      │
│    - "Normal vs Now" comparison     │
│    - Horizontal bar chart           │
│    - Deviation magnitude            │
│    - Phase 3 explanation text       │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 4. PATTERN RECOGNITION (conditional)│
│    - Only if pattern_matches exists │
│    - Pattern name                   │
│    - Confidence level               │
│    - Historical context (seen N x)  │
│    - Typical duration               │
│    - Semantic description           │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 5. EVIDENCE DETAILS                 │
│    - Commits table                  │
│    - Files affected table           │
│    - Tests impacted table (if any)  │
│    - Dependencies changed (if any)  │
│    - Timeline (chronological)       │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 6. INVESTIGATION PROMPT             │
│    - Pre-formatted AI prompt        │
│    - Copyable text block            │
│    - Instructions for use           │
└─────────────────────────────────────┘
```

### 2.2 Page Break Strategy

Use CSS page breaks to ensure clean printing:

```css
.page-break-before { page-break-before: always; }
.page-break-after { page-break-after: always; }
.page-break-avoid { page-break-inside: avoid; }
```

Recommended breaks:
- After cover page
- Before "Pattern Recognition" (if present)
- Before "Evidence Details"
- Before "Investigation Prompt"

---

## 3. CSS Styling Guidelines

### 3.1 Design Principles

1. **Professional** — serif headers, sans-serif body, ample whitespace
2. **Print-friendly** — dark text on white, no backgrounds that waste ink
3. **No JavaScript** — pure CSS, works in any browser/PDF renderer
4. **Accessible** — high contrast, readable font sizes (minimum 11pt)
5. **Consistent** — reusable component classes

### 3.2 Color Palette

```css
:root {
  /* Primary */
  --color-primary: #1e40af;        /* Deep blue for headers */
  --color-primary-light: #3b82f6;  /* Lighter blue for accents */
  
  /* Neutrals */
  --color-text: #1f2937;           /* Dark gray for body text */
  --color-text-muted: #6b7280;     /* Muted gray for metadata */
  --color-border: #e5e7eb;         /* Light gray for borders */
  --color-bg: #ffffff;             /* White background */
  --color-bg-subtle: #f9fafb;      /* Very light gray for cards */
  
  /* Semantic */
  --color-success: #059669;        /* Green for positive */
  --color-warning: #d97706;        /* Orange for caution */
  --color-danger: #dc2626;         /* Red for critical */
  
  /* Chart colors */
  --color-normal: #94a3b8;         /* Gray for baseline bar */
  --color-current: #3b82f6;        /* Blue for current value bar */
}
```

### 3.3 Typography

```css
/* Fonts */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Merriweather:wght@700&display=swap');

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 11pt;
  line-height: 1.6;
  color: var(--color-text);
}

h1, h2, h3 {
  font-family: 'Merriweather', Georgia, serif;
  font-weight: 700;
  color: var(--color-primary);
}

h1 { font-size: 28pt; margin-bottom: 0.5em; }
h2 { font-size: 18pt; margin-top: 1.5em; margin-bottom: 0.75em; }
h3 { font-size: 14pt; margin-top: 1em; margin-bottom: 0.5em; }

code, pre {
  font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
  font-size: 10pt;
}
```

### 3.4 Component Styles

#### Change Card

```css
.change-card {
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-primary-light);
  padding: 1.5em;
  margin-bottom: 1.5em;
  background: var(--color-bg-subtle);
  page-break-inside: avoid;
}

.change-card-header {
  display: flex;
  align-items: center;
  margin-bottom: 1em;
}

.family-icon {
  font-size: 24pt;
  margin-right: 0.5em;
}

.metric-name {
  font-size: 14pt;
  font-weight: 600;
  color: var(--color-primary);
}
```

#### Bar Chart

```css
.bar-chart {
  margin: 1em 0;
}

.bar-chart-row {
  display: flex;
  align-items: center;
  margin-bottom: 0.5em;
}

.bar-label {
  width: 100px;
  font-size: 10pt;
  color: var(--color-text-muted);
  text-align: right;
  padding-right: 1em;
}

.bar-container {
  flex: 1;
  height: 24px;
  background: var(--color-border);
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.bar-fill {
  height: 100%;
  background: var(--color-current);
  transition: width 0.3s ease;
}

.bar-fill.normal {
  background: var(--color-normal);
}

.bar-value {
  margin-left: 1em;
  font-weight: 600;
  white-space: nowrap;
}
```

#### Evidence Table

```css
.evidence-table {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
  font-size: 10pt;
}

.evidence-table thead {
  background: var(--color-bg-subtle);
  border-bottom: 2px solid var(--color-border);
}

.evidence-table th {
  text-align: left;
  padding: 0.75em 1em;
  font-weight: 600;
  color: var(--color-primary);
}

.evidence-table td {
  padding: 0.75em 1em;
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}

.evidence-table tr:last-child td {
  border-bottom: none;
}

.evidence-table code {
  background: var(--color-bg-subtle);
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-size: 9pt;
}
```

### 3.5 Print-Specific Styles

```css
@media print {
  body {
    font-size: 10pt;
  }
  
  a {
    color: var(--color-text);
    text-decoration: none;
  }
  
  a[href]:after {
    content: " (" attr(href) ")";
    font-size: 9pt;
    color: var(--color-text-muted);
  }
  
  .no-print {
    display: none;
  }
  
  .page-break-before {
    page-break-before: always;
  }
  
  .page-break-after {
    page-break-after: always;
  }
  
  .page-break-avoid {
    page-break-inside: avoid;
  }
}
```

---

## 4. Jinja2 Template Variables

### 4.1 Data Structure

The template receives a single context object:

```python
{
  "advisory": {
    "advisory_id": str,
    "scope": str,
    "generated_at": str,  # ISO-8601
    "period": {
      "from": str,  # ISO-8601
      "to": str     # ISO-8601
    },
    "summary": {
      "significant_changes": int,
      "families_affected": list[str],
      "known_patterns_matched": int,
      "new_observations": int
    },
    "changes": list[{
      "family": str,
      "metric": str,
      "normal": {
        "mean": float,
        "stddev": float
      },
      "current": float,
      "deviation_stddev": float,
      "description": str
    }],
    "pattern_matches": list[{
      "knowledge_id": str,
      "pattern_name": str,
      "confidence": str,
      "seen_count": int,
      "typical_duration": str,
      "description": str
    }],
    "evidence": {
      "evidence_id": str,
      "advisory_ref": str,
      "commits": list[{
        "sha": str,
        "message": str,
        "author": dict,
        "timestamp": str,
        "files_changed": list[str]
      }],
      "files_affected": list[{
        "path": str,
        "change_type": str,
        "first_seen_in": str
      }],
      "tests_impacted": list[dict],
      "dependencies_changed": list[dict],
      "timeline": list[{
        "timestamp": str,
        "family": str,
        "event": str
      }]
    }
  },
  "metadata": {
    "generated_at": str,      # Report generation time
    "generator_version": str,  # "Evolution Engine v1.0"
    "report_type": str         # "Advisory Report"
  }
}
```

### 4.2 Helper Filters

Define these Jinja2 filters:

```python
def format_date(iso_string: str) -> str:
    """Convert ISO-8601 to 'Feb 8, 2026 at 10:23 AM'"""
    pass

def format_metric(value: float, metric: str) -> str:
    """Format metric value with appropriate units/precision"""
    # Examples:
    # - files_touched: "440 files"
    # - dispersion: "2.58"
    # - failure_rate: "11.3%"
    pass

def family_icon(family: str) -> str:
    """Return emoji/icon for family"""
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
    """Return human-readable family name"""
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
    """Return human-readable metric name"""
    labels = {
        "files_touched": "Files Changed",
        "dispersion": "Change Dispersion",
        "change_locality": "Change Locality",
        "cochange_novelty_ratio": "Co-change Novelty",
        # ... (see phase5_engine.py METRIC_LABELS)
    }
    return labels.get(metric, metric.replace("_", " ").title())

def calc_bar_width(value: float, max_value: float) -> int:
    """Calculate bar width as percentage (0-100)"""
    if max_value == 0:
        return 0
    return min(int((value / max_value) * 100), 100)

def deviation_class(deviation: float) -> str:
    """Return CSS class based on deviation magnitude"""
    abs_dev = abs(deviation)
    if abs_dev >= 5.0:
        return "deviation-high"
    elif abs_dev >= 2.0:
        return "deviation-medium"
    else:
        return "deviation-low"
```

### 4.3 Template Structure

```jinja2
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Evolution Advisory — {{ advisory.scope }}</title>
  <style>
    /* Inline CSS here (all styles from §3) */
  </style>
</head>
<body>
  <!-- 1. Cover Page -->
  <div class="cover-page page-break-after">
    <h1>Evolution Advisory</h1>
    <div class="cover-metadata">
      <p><strong>Project:</strong> {{ advisory.scope }}</p>
      <p><strong>Period:</strong> {{ advisory.period.from | format_date }} to {{ advisory.period.to | format_date }}</p>
      <p><strong>Advisory ID:</strong> <code>{{ advisory.advisory_id }}</code></p>
      <p><strong>Generated:</strong> {{ metadata.generated_at | format_date }}</p>
    </div>
  </div>

  <!-- 2. Executive Summary -->
  <section class="executive-summary">
    <h2>Executive Summary</h2>
    <div class="summary-cards">
      <div class="summary-card">
        <div class="summary-value">{{ advisory.summary.significant_changes }}</div>
        <div class="summary-label">Significant Changes</div>
      </div>
      <div class="summary-card">
        <div class="summary-value">{{ advisory.summary.families_affected | length }}</div>
        <div class="summary-label">Families Affected</div>
      </div>
      <div class="summary-card">
        <div class="summary-value">{{ advisory.summary.known_patterns_matched }}</div>
        <div class="summary-label">Patterns Matched</div>
      </div>
    </div>
    <p class="summary-families">
      Affected families: 
      {% for family in advisory.summary.families_affected %}
        {{ family | family_icon }} {{ family | family_label }}{% if not loop.last %}, {% endif %}
      {% endfor %}
    </p>
  </section>

  <!-- 3. Changes Detected -->
  <section class="changes-detected page-break-before">
    <h2>Changes Detected</h2>
    {% for change in advisory.changes %}
    <div class="change-card {{ change.deviation_stddev | deviation_class }}">
      <div class="change-card-header">
        <span class="family-icon">{{ change.family | family_icon }}</span>
        <div>
          <div class="metric-name">{{ change.metric | metric_label }}</div>
          <div class="family-label">{{ change.family | family_label }}</div>
        </div>
      </div>
      
      <div class="bar-chart">
        {% set max_val = [change.normal.mean, change.current] | max %}
        <div class="bar-chart-row">
          <div class="bar-label">Normal:</div>
          <div class="bar-container">
            <div class="bar-fill normal" style="width: {{ calc_bar_width(change.normal.mean, max_val) }}%"></div>
          </div>
          <div class="bar-value">{{ change.normal.mean | format_metric(change.metric) }}</div>
        </div>
        <div class="bar-chart-row">
          <div class="bar-label">Now:</div>
          <div class="bar-container">
            <div class="bar-fill" style="width: {{ calc_bar_width(change.current, max_val) }}%"></div>
          </div>
          <div class="bar-value">{{ change.current | format_metric(change.metric) }}</div>
        </div>
      </div>
      
      <div class="deviation-badge">
        {{ change.deviation_stddev | abs | round(1) }}x stddev {{ 'above' if change.deviation_stddev > 0 else 'below' }} normal
      </div>
      
      <p class="explanation">{{ change.description }}</p>
    </div>
    {% endfor %}
  </section>

  <!-- 4. Pattern Recognition (conditional) -->
  {% if advisory.pattern_matches %}
  <section class="pattern-recognition page-break-before">
    <h2>🔍 Pattern Recognition</h2>
    {% for pattern in advisory.pattern_matches %}
    <div class="pattern-card">
      <h3>{{ pattern.pattern_name }}</h3>
      <div class="pattern-meta">
        <span class="badge">{{ pattern.confidence | title }}</span>
        <span>Seen {{ pattern.seen_count }} times</span>
        <span>Typically lasts: {{ pattern.typical_duration }}</span>
      </div>
      <p>{{ pattern.description }}</p>
    </div>
    {% endfor %}
  </section>
  {% endif %}

  <!-- 5. Evidence Details -->
  <section class="evidence-details page-break-before">
    <h2>Evidence Details</h2>
    
    <!-- Commits -->
    <h3>Commits Involved</h3>
    <table class="evidence-table">
      <thead>
        <tr>
          <th>SHA</th>
          <th>Message</th>
          <th>Author</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {% for commit in advisory.evidence.commits %}
        <tr>
          <td><code>{{ commit.sha[:8] }}</code></td>
          <td>{{ commit.message | truncate(60) }}</td>
          <td>{{ commit.author.name }}</td>
          <td>{{ commit.timestamp | format_date }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    
    <!-- Files Affected -->
    <h3>Files Affected</h3>
    <table class="evidence-table">
      <thead>
        <tr>
          <th>Path</th>
          <th>Change Type</th>
          <th>First Seen In</th>
        </tr>
      </thead>
      <tbody>
        {% for file in advisory.evidence.files_affected %}
        <tr>
          <td><code>{{ file.path }}</code></td>
          <td>{{ file.change_type | title }}</td>
          <td><code>{{ file.first_seen_in[:8] }}</code></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    
    <!-- Timeline -->
    <h3>Timeline</h3>
    <div class="timeline">
      {% for event in advisory.evidence.timeline %}
      <div class="timeline-event">
        <div class="timeline-time">{{ event.timestamp | format_date }}</div>
        <div class="timeline-badge">{{ event.family | family_icon }}</div>
        <div class="timeline-content">
          <strong>{{ event.family | family_label }}:</strong> {{ event.event }}
        </div>
      </div>
      {% endfor %}
    </div>
  </section>

  <!-- 6. Investigation Prompt -->
  <section class="investigation-prompt page-break-before">
    <h2>Investigation Prompt</h2>
    <p>Copy this prompt to your AI assistant (Claude, ChatGPT, etc.) for detailed investigation:</p>
    <pre class="prompt-block"><code>Here is a structural analysis of {{ advisory.scope }} from {{ advisory.period.from | format_date }} to {{ advisory.period.to | format_date }}.

CHANGES DETECTED:
{% for change in advisory.changes %}
- {{ change.family | family_label }}: {{ change.metric | metric_label }} changed from {{ change.normal.mean | format_metric(change.metric) }} to {{ change.current | format_metric(change.metric) }} ({{ change.deviation_stddev | abs | round(1) }}x stddev {{ 'above' if change.deviation_stddev > 0 else 'below' }})
{% endfor %}

EVIDENCE:
- {{ advisory.evidence.commits | length }} commits involved
- {{ advisory.evidence.files_affected | length }} files affected

Based on this evidence:
1. What is the most likely root cause of the observed changes?
2. Which specific files should be reviewed first?
3. Are there structural risks introduced by these changes?</code></pre>
  </section>
</body>
</html>
```

---

## 5. CLI Integration

### 5.1 Command Signature

```bash
python -m evolution.report.generator --advisory PATH --output PATH [OPTIONS]
```

### 5.2 Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--advisory` | Yes | Path to Phase 5 `advisory.json` file |
| `--output` | Yes | Output path for HTML report (e.g., `report.html`) |
| `--template` | No | Custom Jinja2 template path (default: built-in) |
| `--open` | No | Open report in browser after generation |

### 5.3 Example Usage

```bash
# Basic usage
python -m evolution.report.generator \
  --advisory .calibration/runs/fastapi/phase5/advisory.json \
  --output reports/fastapi_advisory.html

# With auto-open
python -m evolution.report.generator \
  --advisory .calibration/runs/fastapi/phase5/advisory.json \
  --output reports/fastapi_advisory.html \
  --open
```

### 5.4 Implementation Structure

```
evolution/
├── report/
│   ├── __init__.py
│   ├── __main__.py           # CLI entry point
│   ├── generator.py          # Core rendering logic
│   ├── filters.py            # Jinja2 custom filters
│   └── templates/
│       ├── default.html      # Main template
│       └── components/       # Reusable template fragments
│           ├── cover.html
│           ├── summary.html
│           ├── changes.html
│           ├── patterns.html
│           ├── evidence.html
│           └── prompt.html
```

### 5.5 Generator Module Spec

```python
# evolution/report/generator.py

from pathlib import Path
import json
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .filters import (
    format_date,
    format_metric,
    family_icon,
    family_label,
    metric_label,
    calc_bar_width,
    deviation_class,
)

class ReportGenerator:
    """Generates HTML reports from Phase 5 advisory JSON."""
    
    def __init__(self, template_dir: Path | None = None):
        """Initialize generator with template directory."""
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
    
    def generate(
        self,
        advisory_path: Path,
        output_path: Path,
        template_name: str = "default.html"
    ) -> None:
        """Generate HTML report from advisory JSON."""
        # Load advisory JSON
        with open(advisory_path, 'r') as f:
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
```

---

## 6. Testing with Sample Data

### 6.1 Sample Data Location

```
.calibration/runs/fastapi/phase5/advisory.json
```

### 6.2 Validation Checklist

When testing the generator with sample data, verify:

- [ ] Cover page displays project name, period, advisory ID
- [ ] Executive summary shows correct counts
- [ ] All 4 changes render with bar charts
- [ ] Bar widths are proportional to values
- [ ] Deviation badges show correct magnitude
- [ ] Evidence tables populate correctly (20 commits, 50 files)
- [ ] Timeline events are chronologically ordered
- [ ] Investigation prompt is copyable and complete
- [ ] Print preview shows proper page breaks
- [ ] No JavaScript errors in browser console
- [ ] PDF export (Print → Save as PDF) renders cleanly

### 6.3 Test Command

```bash
# Generate report from fastapi calibration data
python -m evolution.report.generator \
  --advisory .calibration/runs/fastapi/phase5/advisory.json \
  --output .calibration/reports/fastapi_advisory.html \
  --open

# Then: File → Print → Save as PDF
```

---

## 7. Design Constraints

### 7.1 MUST NOT Include

- Interactive JavaScript (charts, filters, sorting)
- External dependencies loaded at runtime (CDNs)
- Dynamic data fetching
- User authentication
- Analytics/tracking scripts

### 7.2 MUST Include

- All CSS inlined in `<style>` tag
- Self-contained HTML (no external resources except Google Fonts)
- Print-friendly page breaks
- High-contrast, readable typography
- Professional visual hierarchy

### 7.3 Accessibility Requirements

- Semantic HTML5 elements (`<section>`, `<table>`, `<code>`)
- ARIA labels where appropriate
- Sufficient color contrast (WCAG AA minimum)
- Readable without CSS (graceful degradation)

---

## 8. Future Enhancements (Out of Scope)

These are NOT required for initial implementation:

- Interactive charts (D3.js, Chart.js)
- Multi-report comparison view
- Email delivery integration
- Custom branding upload
- Report scheduling
- Historical trend graphs

Phase 6 focuses on **static, print-ready reports**. Interactivity is a future enhancement.

---

## 9. Definition of Done

Phase 6 implementation is complete when:

- [ ] CLI command works: `python -m evolution.report.generator --advisory ... --output ...`
- [ ] HTML template renders all 6 sections correctly
- [ ] CSS is professional and print-friendly
- [ ] All Jinja2 filters are implemented and tested
- [ ] Works with `.calibration/runs/fastapi/phase5/advisory.json`
- [ ] Print-to-PDF produces clean, readable output
- [ ] No JavaScript in generated HTML
- [ ] Code is documented with docstrings
- [ ] README includes usage examples

---

## 10. Summary

The Report Generator transforms Phase 5 advisory JSON into professional HTML/PDF reports suitable for client delivery. It uses Jinja2 templates, inline CSS, and custom filters to create self-contained, print-ready documents with clear visual hierarchy and actionable evidence.

**Key principle:** Clarity over cleverness. A consultant should be able to print the PDF and hand it to a client with confidence.
