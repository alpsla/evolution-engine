"""
Pattern Scaffold — Generate pip-installable pattern package structure.

Creates a complete package skeleton that can be built and uploaded to PyPI.
The primary consumption path is auto-fetch (no pip install needed), but
the package also includes entry points for local development.

Usage:
    from evolution.pattern_scaffold import scaffold_pattern_pack

    result = scaffold_pattern_pack("web-security", description="Web security patterns")
    print(result["path"])

CLI:
    evo patterns new my-patterns
"""

import json
import os
from pathlib import Path


def scaffold_pattern_pack(
    name: str,
    description: str = "",
    output_dir: str = ".",
) -> dict:
    """Generate pip-installable pattern package.

    Creates:
        evo-patterns-<name>/
          pyproject.toml
          evo_patterns_<name>/
            __init__.py
            patterns.json
          tests/
            test_patterns.py
          README.md

    Args:
        name: Short name (e.g. "web-security"). Will be prefixed with "evo-patterns-".
        description: Package description.
        output_dir: Parent directory for the generated package.

    Returns:
        Dict with: path, package_name, module_name, files_created.
    """
    # Normalize name
    clean_name = name.lower().replace(" ", "-").replace("_", "-")
    if clean_name.startswith("evo-patterns-"):
        clean_name = clean_name[len("evo-patterns-"):]

    package_name = f"evo-patterns-{clean_name}"
    module_name = package_name.replace("-", "_")
    description = description or f"Evolution Engine pattern pack: {clean_name}"

    # Create directory structure
    base_dir = Path(output_dir) / package_name
    module_dir = base_dir / module_name
    tests_dir = base_dir / "tests"

    base_dir.mkdir(parents=True, exist_ok=True)
    module_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    files_created = []

    # pyproject.toml
    pyproject_content = f"""\
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "0.1.0"
description = "{description}"
readme = "README.md"
license = {{text = "MIT"}}
requires-python = ">=3.9"
authors = [{{name = "Your Name", email = "you@example.com"}}]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
]

[project.urls]
Homepage = "https://github.com/yourname/{package_name}"

[project.entry-points."evo.patterns"]
{package_name} = "{module_name}:register"

[tool.setuptools.package-data]
{module_name} = ["patterns.json"]
"""
    (base_dir / "pyproject.toml").write_text(pyproject_content)
    files_created.append("pyproject.toml")

    # __init__.py
    init_content = f"""\
\"\"\"
{package_name} — Evolution Engine pattern pack.

{description}
\"\"\"

import json
from pathlib import Path


def register():
    \"\"\"Entry point for local development. Loads patterns from patterns.json.\"\"\"
    patterns_path = Path(__file__).parent / "patterns.json"
    if not patterns_path.exists():
        return []
    return json.loads(patterns_path.read_text())
"""
    (module_dir / "__init__.py").write_text(init_content)
    files_created.append(f"{module_name}/__init__.py")

    # patterns.json (empty template)
    patterns_template = [
        {
            "fingerprint": "0000000000000000",
            "pattern_type": "co_occurrence",
            "discovery_method": "statistical",
            "sources": ["ci", "git"],
            "metrics": ["ci_presence", "dispersion"],
            "description_statistical": "Example: When CI events occur, git dispersion increases.",
            "correlation_strength": 0.5,
            "occurrence_count": 10,
            "confidence_tier": "statistical",
            "scope": "community",
        }
    ]
    (module_dir / "patterns.json").write_text(
        json.dumps(patterns_template, indent=2) + "\n"
    )
    files_created.append(f"{module_name}/patterns.json")

    # tests/test_patterns.py
    test_content = f"""\
\"\"\"Tests for {package_name}.\"\"\"

import json
from pathlib import Path


def test_patterns_json_valid():
    \"\"\"Verify patterns.json is valid JSON with expected structure.\"\"\"
    patterns_path = Path(__file__).parent.parent / "{module_name}" / "patterns.json"
    assert patterns_path.exists(), "patterns.json must exist"

    patterns = json.loads(patterns_path.read_text())
    assert isinstance(patterns, list), "patterns.json must be a list"
    assert len(patterns) > 0, "Must have at least one pattern"

    for p in patterns:
        assert "fingerprint" in p, "Pattern must have fingerprint"
        assert "sources" in p, "Pattern must have sources"
        assert "metrics" in p, "Pattern must have metrics"
        assert "pattern_type" in p, "Pattern must have pattern_type"
        assert "discovery_method" in p, "Pattern must have discovery_method"
        assert p.get("scope") in ("community", "universal"), "Scope must be community or universal"


def test_register():
    \"\"\"Verify register() entry point loads patterns.\"\"\"
    from {module_name} import register

    patterns = register()
    assert isinstance(patterns, list)
    assert len(patterns) > 0
"""
    (tests_dir / "test_patterns.py").write_text(test_content)
    files_created.append("tests/test_patterns.py")

    # README.md
    readme_content = f"""\
# {package_name}

{description}

## Installation

This package is consumed automatically by Evolution Engine's pattern auto-fetch.
No manual installation required.

For local development:

```bash
pip install -e .
```

## Patterns

Edit `{module_name}/patterns.json` to add your patterns.

Each pattern must have:
- `fingerprint`: Unique hex identifier
- `sources`: List of event families (e.g., ["ci", "git"])
- `metrics`: List of metrics involved
- `pattern_type`: One of "co_occurrence", "temporal_sequence", "threshold_breach"
- `discovery_method`: One of "statistical", "semantic", "hybrid"
- `scope`: Must be "community" for published packages
- `correlation_strength`: Numeric effect size

## Validation

```bash
evo patterns validate .
```

## Publishing

```bash
evo patterns publish .
```
"""
    (base_dir / "README.md").write_text(readme_content)
    files_created.append("README.md")

    return {
        "path": str(base_dir),
        "package_name": package_name,
        "module_name": module_name,
        "files_created": files_created,
    }
