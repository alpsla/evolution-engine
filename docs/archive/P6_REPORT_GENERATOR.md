# Task: P6 — Report Generator (HTML/PDF)

> **For:** Sonnet 4.5 (or equivalent)
> **Effort:** 2–3 days
> **Blocks:** Consulting engagements
> **Priority:** 6
> **Dependencies:** Can start now — sample `advisory.json` exists at:
>   `.calibration/runs/fastapi/phase5/advisory.json`

---

## Goal

Build an HTML/PDF report generator that transforms Phase 5 `advisory.json` into
a professional, branded document suitable for consulting client delivery.

**Current state:** Phase 5 produces `summary.txt` (plain text with Unicode bars)
and `chat.txt` (compact text). These work but aren't client-presentable.

**Target state:** A polished HTML report with proper charts, tables, and branding
that can be opened in a browser or exported to PDF.

---

## Prerequisites

```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine
source .venv/bin/activate
pip install jinja2 weasyprint   # For HTML templating and PDF export
```

**Read these files first:**
- `.calibration/runs/fastapi/phase5/advisory.json` — Sample advisory (real data)
- `.calibration/runs/fastapi/phase5/evidence.json` — Sample evidence package
- `.calibration/runs/fastapi/phase5/summary.txt` — Current text output (reference for layout)
- `.calibration/runs/fastapi/phase5/investigation_prompt.txt` — Investigation prompt
- `evolution/phase5_engine.py` — Phase 5 engine (understand the data shapes)

---

## Advisory JSON Structure

```json
{
  "advisory_id": "a8058373be6fb6c1",
  "scope": "fastapi",
  "generated_at": "2026-02-08T12:34:03.522469Z",
  "period": {
    "from": "2026-02-08T...",
    "to": "2026-02-08T..."
  },
  "summary": {
    "significant_changes": 4,
    "families_affected": ["git"],
    "known_patterns_matched": 0,
    "new_observations": 4
  },
  "changes": [
    {
      "family": "git",
      "metric": "files_touched",
      "normal": { "mean": 1.2, "stddev": 0.57 },
      "current": 440,
      "deviation_stddev": 775.7,
      "description": "..."
    }
  ],
  "pattern_matches": [
    {
      "knowledge_id": "...",
      "pattern_type": "co_occurrence",
      "confidence": "approved",
      "seen_count": 15,
      "sources": ["git", "dependency"],
      "metrics": ["files_touched", "dependency_count"],
      "description": "..."
    }
  ],
  "evidence": {
    "commits": [...],
    "files_affected": [...],
    "tests_impacted": [...],
    "dependencies_changed": [...],
    "timeline": [...]
  }
}
```

---

## Report Layout

### Page 1: Cover + Executive Summary

```
┌─────────────────────────────────────────┐
│                                         │
│         EVOLUTION ENGINE                │
│         Advisory Report                 │
│                                         │
│  Repository: fastapi                    │
│  Period: 2026-02-01 to 2026-02-08       │
│  Generated: 2026-02-08                  │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ EXECUTIVE SUMMARY              │    │
│  │                                 │    │
│  │ 4 significant changes detected  │    │
│  │ across Version Control.         │    │
│  │                                 │    │
│  │ 0 known patterns matched.      │    │
│  │ 4 new observations.            │    │
│  └─────────────────────────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

### Page 2+: Changes (Normal vs Now)

For each change, show:

```
┌─────────────────────────────────────────┐
│  1. Version Control / Files Changed     │
│                                         │
│  Normal:  1.2 ± 0.57                    │
│  Current: 440                           │
│  Deviation: 775.7x stddev above normal  │
│                                         │
│  ┌──────────────────────────────┐       │
│  │ Normal  ██                   │       │
│  │ Current ████████████████████ │ 366x  │
│  └──────────────────────────────┘       │
│                                         │
│  "The number of files changed in this   │
│   commit was 440, compared to a normal  │
│   of 1.2 ± 0.57..."                    │
│                                         │
└─────────────────────────────────────────┘
```

**Bar chart implementation:**
- Use inline SVG or pure CSS bars (no JavaScript dependencies)
- Normal bar = fixed width (e.g., 200px)
- Current bar = proportional to `current / normal.mean`, capped at container width
- Color: blue for normal, orange/red for deviation above, green for deviation below

### Page 3: Pattern Matches (if any)

```
┌─────────────────────────────────────────┐
│  PATTERN RECOGNITION                    │
│                                         │
│  These changes match known patterns     │
│  from the Knowledge Base:               │
│                                         │
│  Pattern: "Dependency growth correlates │
│  with test duration increase"           │
│  Seen: 15 times | Confidence: Approved  │
│  Sources: Git + Dependencies            │
│                                         │
└─────────────────────────────────────────┘
```

### Page 4: Evidence

```
┌─────────────────────────────────────────┐
│  EVIDENCE                               │
│                                         │
│  Commits (20)                           │
│  ┌────────────────────────────────────┐ │
│  │ SHA      │ Message │ Files │ Date  │ │
│  │ 22c34a39 │ Update  │  1    │ 02-08 │ │
│  │ ...      │ ...     │  ...  │ ...   │ │
│  └────────────────────────────────────┘ │
│                                         │
│  Files Affected (50)                    │
│  - docs/en/docs/release-notes.md       │
│  - fastapi/__init__.py                 │
│  - ...                                 │
│                                         │
│  Timeline                               │
│  02-08 12:23 [git] Files Changed: 19   │
│  02-08 12:23 [git] Dispersion: 1.585   │
│  ...                                   │
│                                         │
└─────────────────────────────────────────┘
```

### Page 5: Investigation Prompt (Appendix)

Include the full investigation prompt text as an appendix,
clearly labeled "Copy this prompt to your AI assistant for investigation."

---

## Implementation

### File Structure

```
evolution/
├── report/
│   ├── __init__.py
│   ├── generator.py         # Main report generator class
│   └── templates/
│       ├── report.html       # Jinja2 HTML template
│       └── styles.css        # CSS styling (embedded or linked)
```

### `generator.py`

```python
class ReportGenerator:
    """Generate HTML/PDF reports from Phase 5 advisory data."""

    def __init__(self, advisory_path: str, evidence_path: str = None):
        """
        Args:
            advisory_path: Path to advisory.json
            evidence_path: Path to evidence.json (optional, auto-detected)
        """

    def generate_html(self, output_path: str) -> str:
        """Generate HTML report, return the output path."""

    def generate_pdf(self, output_path: str) -> str:
        """Generate PDF report via weasyprint, return the output path."""
```

### Template Variables (passed to Jinja2)

```python
context = {
    "advisory": advisory_dict,           # Full advisory JSON
    "evidence": evidence_dict,           # Full evidence JSON
    "scope": advisory["scope"],
    "generated_at": advisory["generated_at"],
    "period_from": advisory["period"]["from"][:10],
    "period_to": advisory["period"]["to"][:10],
    "summary": advisory["summary"],
    "changes": advisory["changes"],       # List of change dicts
    "pattern_matches": advisory.get("pattern_matches", []),
    "commits": evidence.get("commits", [])[:20],
    "files": evidence.get("files_affected", [])[:50],
    "tests": evidence.get("tests_impacted", []),
    "deps": evidence.get("dependencies_changed", []),
    "timeline": evidence.get("timeline", [])[:30],
    "investigation_prompt": investigation_prompt_text,

    # Helper values
    "family_labels": {
        "git": "Version Control", "ci": "CI / Build",
        "testing": "Testing", "dependency": "Dependencies",
        "schema": "API / Schema", "deployment": "Deployment",
        "config": "Configuration", "security": "Security",
    },
    "metric_labels": {
        "files_touched": "Files Changed",
        "dispersion": "Change Dispersion",
        "change_locality": "Change Locality",
        "cochange_novelty_ratio": "Co-change Novelty",
        # ... (see METRIC_LABELS in phase5_engine.py for full list)
    },
}
```

### CSS Styling Guidelines

- **Clean, professional look** — not flashy, suitable for enterprise clients
- **Colors:** Dark blue (#1a365d) for headers, light gray (#f7fafc) for backgrounds
- **Font:** System fonts (sans-serif stack), no external font dependencies
- **Bar charts:** Pure CSS with `width` percentage and `background-color`
- **Print-friendly:** Works well when printed or exported to PDF
- **Responsive:** Not needed (fixed-width report, ~800px)
- **No JavaScript** — pure HTML + CSS for maximum compatibility

### Bar Chart CSS Example

```css
.bar-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 8px 0;
}

.bar {
  height: 24px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  padding-left: 8px;
  font-size: 12px;
  color: white;
}

.bar-normal {
  background-color: #4299e1;
  width: 200px;
}

.bar-current {
  background-color: #ed8936;
  /* Width set dynamically via style attribute */
}

.bar-current.below {
  background-color: #48bb78;
}
```

---

## CLI Integration

Add a CLI command to the report generator:

```bash
# Generate HTML report
python -m evolution.report.generator \
  --advisory .calibration/runs/fastapi/phase5/advisory.json \
  --output report.html

# Generate PDF (requires weasyprint)
python -m evolution.report.generator \
  --advisory .calibration/runs/fastapi/phase5/advisory.json \
  --output report.pdf \
  --format pdf
```

Add `if __name__ == "__main__"` block to `generator.py` for CLI usage.

---

## Testing

### Test with Sample Data

```bash
cd /Users/Shared/OpenClaw-Workspace/repos/evolution-engine

# Generate HTML from existing fastapi advisory
python -m evolution.report.generator \
  --advisory .calibration/runs/fastapi/phase5/advisory.json \
  --output .calibration/reports/fastapi_report.html

# Open in browser to verify
open .calibration/reports/fastapi_report.html
```

### Validation Criteria

1. **Report renders correctly** in Safari/Chrome
2. **All sections present:** Cover, Changes, Patterns, Evidence, Investigation Prompt
3. **Bar charts are proportional** — current vs normal visually correct
4. **Tables are readable** — commits, files, timeline
5. **Print/PDF looks good** — test with Cmd+P in browser
6. **No external dependencies** — no CDN links, no JavaScript, all CSS inline or embedded
7. **Works with empty pattern_matches** — current data has no patterns yet

---

## Files to Create

| File | Description |
|------|-------------|
| `evolution/report/__init__.py` | Package init |
| `evolution/report/generator.py` | Main generator class + CLI |
| `evolution/report/templates/report.html` | Jinja2 HTML template |

---

## What NOT to Do

- Do NOT build a web server or dashboard — this is a static report generator
- Do NOT add JavaScript — pure HTML + CSS only
- Do NOT use external CSS frameworks (Bootstrap, Tailwind) — keep it self-contained
- Do NOT use CDN links — everything must work offline
- Do NOT modify Phase 5 engine — read its output files only
- Do NOT add logo images — use text/CSS for branding (images can be added later)

---

## Success Criteria

- [ ] `evolution.report.generator` module exists and is importable
- [ ] HTML report generates from `advisory.json` without errors
- [ ] Report has all 5 sections (Cover, Changes, Patterns, Evidence, Prompt)
- [ ] Bar charts show "normal vs now" proportionally
- [ ] Evidence tables show commits, files, timeline
- [ ] Report looks professional and client-presentable
- [ ] PDF export works via weasyprint (or browser print fallback)
- [ ] CLI command works: `python -m evolution.report.generator --advisory ... --output ...`
