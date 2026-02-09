"""
Adapter Scaffold — Generate plugin adapter packages from templates.

Creates a complete pip-installable package structure:
  evo-adapter-<name>/
    pyproject.toml
    evo_<name>/
      __init__.py        (register function + adapter class)
    tests/
      test_adapter.py    (validation + basic tests)
    README.md

Usage:
    from evolution.adapter_scaffold import scaffold_adapter
    result = scaffold_adapter("jenkins", "ci")

CLI:
    evo adapter new jenkins --family ci
"""

import re
from pathlib import Path

import click


VALID_FAMILIES = {
    "ci", "testing", "dependency", "schema",
    "deployment", "config", "security",
}

FAMILY_EXAMPLES = {
    "ci": {
        "source_type": "my_ci",
        "ordering_mode": "temporal",
        "attestation_tier": "medium",
        "payload_example": """\
            payload = {
                "run_id": str(run["id"]),
                "status": run["status"],       # "success", "failed", "cancelled"
                "duration_seconds": run.get("duration", 0),
                "trigger": {
                    "commit_sha": run.get("commit_sha", ""),
                },
                "timing": {
                    "created_at": run.get("started_at", ""),
                    "finished_at": run.get("finished_at", ""),
                },
            }""",
    },
    "deployment": {
        "source_type": "my_deploy",
        "ordering_mode": "temporal",
        "attestation_tier": "medium",
        "payload_example": """\
            payload = {
                "release_tag": release["tag"],
                "is_prerelease": release.get("prerelease", False),
                "asset_count": len(release.get("assets", [])),
                "trigger": {
                    "commit_sha": release.get("target_commitish", ""),
                },
                "timing": {
                    "initiated_at": release.get("created_at", ""),
                    "completed_at": release.get("published_at", ""),
                },
            }""",
    },
    "dependency": {
        "source_type": "my_deps",
        "ordering_mode": "temporal",
        "attestation_tier": "medium",
        "payload_example": """\
            payload = {
                "ecosystem": "my_ecosystem",
                "manifest_file": "lockfile.lock",
                "trigger": {
                    "commit_sha": snapshot.get("commit_sha", ""),
                },
                "snapshot": {
                    "direct_count": len(deps),
                    "transitive_count": 0,
                    "total_count": len(deps),
                    "max_depth": 1,
                },
                "dependencies": deps,
            }""",
    },
    "testing": {
        "source_type": "my_tests",
        "ordering_mode": "temporal",
        "attestation_tier": "medium",
        "payload_example": """\
            payload = {
                "suite_name": result["suite"],
                "tests_run": result["total"],
                "tests_passed": result["passed"],
                "tests_failed": result["failed"],
                "duration_seconds": result.get("duration", 0),
                "trigger": {
                    "commit_sha": result.get("commit_sha", ""),
                },
            }""",
    },
    "schema": {
        "source_type": "my_schema",
        "ordering_mode": "temporal",
        "attestation_tier": "medium",
        "payload_example": """\
            payload = {
                "schema_file": schema["path"],
                "format": "openapi",
                "endpoints_count": len(schema.get("paths", {})),
                "trigger": {
                    "commit_sha": schema.get("commit_sha", ""),
                },
            }""",
    },
    "config": {
        "source_type": "my_config",
        "ordering_mode": "temporal",
        "attestation_tier": "weak",
        "payload_example": """\
            payload = {
                "config_file": config["path"],
                "format": "yaml",
                "resource_count": len(config.get("resources", [])),
                "trigger": {
                    "commit_sha": config.get("commit_sha", ""),
                },
            }""",
    },
    "security": {
        "source_type": "my_security",
        "ordering_mode": "temporal",
        "attestation_tier": "medium",
        "payload_example": """\
            payload = {
                "alert_id": alert["id"],
                "severity": alert["severity"],  # "critical", "high", "medium", "low"
                "package": alert.get("package", ""),
                "trigger": {
                    "commit_sha": alert.get("commit_sha", ""),
                },
            }""",
    },
}


def _sanitize_name(name: str) -> str:
    """Convert adapter name to valid Python identifier."""
    return re.sub(r'[^a-z0-9]', '_', name.lower().strip())


def _class_name(name: str) -> str:
    """Convert adapter name to CamelCase class name."""
    parts = re.split(r'[-_\s]+', name.strip())
    return ''.join(p.capitalize() for p in parts) + 'Adapter'


def scaffold_adapter(name: str, family: str, output_dir: str = ".") -> dict:
    """Generate a complete adapter plugin package.

    Args:
        name: Adapter name (e.g. "jenkins", "bitbucket-pipelines")
        family: Source family (e.g. "ci", "deployment")
        output_dir: Parent directory to create the package in

    Returns:
        Dict with package_dir, adapter_file, adapter_class_path
    """
    if family not in VALID_FAMILIES:
        raise ValueError(f"Unknown family '{family}'. Must be one of: {sorted(VALID_FAMILIES)}")

    safe_name = _sanitize_name(name)
    class_name = _class_name(name)
    pkg_name = f"evo-adapter-{name}"
    module_name = f"evo_{safe_name}"
    example = FAMILY_EXAMPLES.get(family, FAMILY_EXAMPLES["ci"])

    output_path = Path(output_dir).resolve()
    pkg_dir = output_path / pkg_name
    src_dir = pkg_dir / module_name

    # Create directories
    pkg_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(exist_ok=True)
    (pkg_dir / "tests").mkdir(exist_ok=True)

    # ── pyproject.toml ──
    (pkg_dir / "pyproject.toml").write_text(f"""\
[project]
name = "{pkg_name}"
version = "0.1.0"
description = "Evolution Engine adapter for {name}"
requires-python = ">=3.10"
dependencies = ["evolution-engine>=0.1.0"]

[project.entry-points."evo.adapters"]
{safe_name} = "{module_name}:register"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
""")

    # ── __init__.py (adapter + register function) ──
    (src_dir / "__init__.py").write_text(f'''\
"""
{class_name} — Evolution Engine plugin adapter for {name}.

Source family: {family}

Install:
    pip install {pkg_name}

After installing, `evo analyze .` will auto-discover this adapter
if it detects relevant files in your repository.
"""


def register():
    """Called by evo's plugin registry at startup.

    Returns a list of adapter descriptors. Each descriptor tells evo
    how to detect and load this adapter.
    """
    return [
        {{
            # Tier 1: file-based detection
            # Change this to the file pattern that indicates your tool is in use
            "pattern": "CHANGE_ME.yml",
            "adapter_name": "{safe_name}",
            "family": "{family}",
            "adapter_class": "{module_name}.{class_name}",
        }},
        # Uncomment for Tier 2 (token-based / API) detection:
        # {{
        #     "token_key": "{safe_name}_token",
        #     "adapter_name": "{safe_name}_api",
        #     "family": "{family}",
        #     "adapter_class": "{module_name}.{class_name}",
        # }},
    ]


class {class_name}:
    """Adapter for {name} ({family} family).

    This adapter must:
    1. Set the four required class attributes below
    2. Accept configuration in __init__()
    3. Implement iter_events() that yields SourceEvent dicts

    Run `evo adapter validate {module_name}.{class_name}` to verify.
    """

    # ── Required class attributes ──
    source_family = "{family}"
    source_type = "{safe_name}"
    ordering_mode = "{example["ordering_mode"]}"
    attestation_tier = "{example["attestation_tier"]}"

    def __init__(self, *, data=None, source_id=None):
        """Initialize the adapter.

        Args:
            data: Pre-loaded data (for testing/fixtures).
                  Replace with your actual data source.
            source_id: Unique identifier for this adapter instance.
        """
        self._data = data or []
        self.source_id = source_id or "{safe_name}:default"

    def iter_events(self):
        """Yield SourceEvent dicts.

        Each event must have these fields:
        - source_family: must match self.source_family
        - source_type: must match self.source_type
        - source_id: instance identifier
        - ordering_mode: "causal" or "temporal"
        - attestation: dict with at least "trust_tier"
        - payload: dict with family-specific data

        The payload should include a trigger.commit_sha field
        so Phase 4 can align events across families.
        """
        for item in self._data:
            # TODO: Replace with your actual data parsing logic
{example["payload_example"]}

            yield {{
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {{
                    "type": "{safe_name}_event",
                    "trust_tier": self.attestation_tier,
                }},
                "predecessor_refs": None,
                "payload": payload,
            }}
''')

    # ── tests/test_adapter.py ──
    (pkg_dir / "tests" / "test_adapter.py").write_text(f'''\
"""Tests for {class_name}."""

from {module_name} import {class_name}, register


def test_register_returns_descriptors():
    """register() must return a list of dicts with required fields."""
    descriptors = register()
    assert isinstance(descriptors, list)
    assert len(descriptors) >= 1
    for d in descriptors:
        assert "adapter_name" in d
        assert "family" in d


def test_adapter_has_required_attributes():
    assert {class_name}.source_family == "{family}"
    assert {class_name}.source_type == "{safe_name}"
    assert {class_name}.ordering_mode in ("causal", "temporal")
    assert {class_name}.attestation_tier in ("strong", "medium", "weak")


def test_adapter_yields_events():
    """Adapter should yield valid events from sample data."""
    # TODO: Replace with real sample data for your adapter
    sample_data = [
        {{"id": 1, "status": "success", "commit_sha": "abc123"}},
    ]
    adapter = {class_name}(data=sample_data)
    events = list(adapter.iter_events())
    assert len(events) >= 1

    for event in events:
        assert event["source_family"] == "{family}"
        assert "payload" in event
        assert isinstance(event["attestation"], dict)
        assert "trust_tier" in event["attestation"]


def test_certification():
    """Run the full evo adapter validation suite."""
    from evolution.adapter_validator import validate_adapter

    sample_data = [
        {{"id": 1, "status": "success", "commit_sha": "abc123"}},
    ]
    report = validate_adapter(
        {class_name},
        constructor_args={{"data": sample_data}},
    )
    assert report.passed, report.summary()
''')

    # ── README.md ──
    (pkg_dir / "README.md").write_text(f"""\
# {pkg_name}

Evolution Engine adapter for {name} ({family} family).

## Install

```bash
pip install {pkg_name}
```

After installing, `evo analyze .` will automatically detect and use this adapter.

## Verify

```bash
evo adapter validate {module_name}.{class_name}
evo adapter list .
```

## Development

```bash
git clone <this-repo>
cd {pkg_name}
pip install -e .
pytest tests/
evo adapter validate {module_name}.{class_name}
```
""")

    return {
        "package_dir": str(pkg_dir),
        "adapter_file": f"{module_name}/__init__.py",
        "adapter_class_path": f"{module_name}.{class_name}",
        "module_name": module_name,
    }


def generate_ai_prompt(
    name: str,
    family: str,
    description: str = "",
    data_source: str = "",
) -> str:
    """Generate a prompt for an AI agent to build an adapter.

    Args:
        name: Adapter name (e.g. "jenkins")
        family: Source family (e.g. "ci")
        description: What the adapter should do
        data_source: Where the data comes from (API URL, file format, etc.)

    Returns:
        A complete prompt string ready to paste into an AI assistant.
    """
    safe_name = _sanitize_name(name)
    class_name = _class_name(name)
    module_name = f"evo_{safe_name}"
    pkg_name = f"evo-adapter-{name}"
    example = FAMILY_EXAMPLES.get(family, FAMILY_EXAMPLES["ci"])

    context_block = ""
    if description:
        context_block += f"\nUser description: {description}\n"
    if data_source:
        context_block += f"Data source: {data_source}\n"

    return f"""\
Build an Evolution Engine adapter plugin for {name} ({family} family).
{context_block}
## What to build

A pip-installable Python package called `{pkg_name}` with:
- Module: `{module_name}/`
- Main class: `{class_name}`
- Entry point registration for evo's plugin system

## Adapter Contract (MUST follow exactly)

The adapter class MUST have these four class attributes:

    source_family = "{family}"
    source_type = "{safe_name}"
    ordering_mode = "{example["ordering_mode"]}"
    attestation_tier = "{example["attestation_tier"]}"

The constructor MUST set `self.source_id` (a unique string identifier).

The class MUST implement `iter_events()` that yields dicts with this exact structure:

    {{
        "source_family": "{family}",
        "source_type": "{safe_name}",
        "source_id": self.source_id,
        "ordering_mode": "{example["ordering_mode"]}",
        "attestation": {{
            "type": "{safe_name}_event",
            "trust_tier": "{example["attestation_tier"]}",
        }},
        "predecessor_refs": None,
        "payload": {{
            # Family-specific data here — see examples below
            "trigger": {{
                "commit_sha": "...",  # CRITICAL: needed for cross-family correlation
            }},
        }},
    }}

CRITICAL: Every event payload MUST include `trigger.commit_sha` so evo can correlate
events across families (e.g. linking a CI build to the git commit that triggered it).

## Example payload for {family} family

{example["payload_example"]}

## Reference: Real adapter (GitHubActionsAdapter for CI)

```python
class GitHubActionsAdapter:
    source_family = "ci"
    source_type = "github_actions"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, owner=None, repo=None, token=None, runs=None, source_id=None):
        self._fixture_runs = runs
        self.source_id = source_id or f"github_actions:{{owner}}/{{repo}}"

    def iter_events(self):
        runs = self._fixture_runs or self._fetch_runs()
        for run in runs:
            payload = {{
                "run_id": str(run["id"]),
                "workflow_name": run.get("name", "unknown"),
                "trigger": {{
                    "type": run.get("event", "unknown"),
                    "commit_sha": run.get("head_sha", ""),
                }},
                "status": run.get("conclusion", "unknown"),
                "timing": {{
                    "created_at": run.get("created_at", ""),
                    "duration_seconds": self._parse_duration(run),
                }},
            }}
            yield {{
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {{
                    "type": "ci_run",
                    "trust_tier": self.attestation_tier,
                }},
                "predecessor_refs": None,
                "payload": payload,
            }}
```

## Plugin registration

The package must have this in `pyproject.toml`:

```toml
[project.entry-points."evo.adapters"]
{safe_name} = "{module_name}:register"
```

And this function in `{module_name}/__init__.py`:

```python
def register():
    return [{{
        "pattern": "CHANGE_TO_REAL_FILE_PATTERN",  # e.g. "Jenkinsfile", ".circleci/config.yml"
        "adapter_name": "{safe_name}",
        "family": "{family}",
        "adapter_class": "{module_name}.{class_name}",
    }}]
```

## Package structure to create

```
{pkg_name}/
    pyproject.toml          # with entry_points and dependencies
    {module_name}/
        __init__.py         # register() function + {class_name} class
    tests/
        test_adapter.py     # basic tests + certification test
    README.md
```

## Tests MUST include

```python
def test_certification():
    from evolution.adapter_validator import validate_adapter
    report = validate_adapter({class_name}, constructor_args={{...sample data...}})
    assert report.passed, report.summary()
```

## Validation checklist (13 checks)

The adapter must pass ALL of these:
1. Has `source_family` class attribute
2. Has `source_type` class attribute
3. Has `ordering_mode` class attribute (must be "causal" or "temporal")
4. Has `attestation_tier` class attribute (must be "strong", "medium", or "weak")
5. `source_family` is a valid family: ci, testing, dependency, schema, deployment, config, security
6. Has `iter_events()` method
7. Can be instantiated
8. Sets `source_id` after construction
9. `iter_events()` yields at least 1 event
10. Events have required fields: source_family, source_type, source_id, ordering_mode, attestation, payload
11. Event `source_family` matches class attribute
12. `attestation` is a dict with `trust_tier` key
13. `payload` is a dict
14. Events are JSON-serializable (no sets, custom objects, etc.)

After building, the user will verify with: `evo adapter validate {module_name}.{class_name}`
"""


def print_guide():
    """Print the adapter development guide to stdout."""
    guide = """\
BUILDING AN EVO ADAPTER PLUGIN
===============================

An adapter teaches evo how to read data from a new source (CI system,
deployment tool, package manager, etc.). Once installed, it works
automatically with `evo analyze .`.

QUICK START (2 minutes)
-----------------------

  1. Scaffold a new adapter:

     evo adapter new jenkins --family ci

  2. Edit the generated adapter class with your logic

  3. Install locally and validate:

     cd evo-adapter-jenkins
     pip install -e .
     evo adapter validate evo_jenkins.JenkinsAdapter

  4. Publish to PyPI:

     pip install build twine
     python -m build
     twine upload dist/*

  Other users install with: pip install evo-adapter-jenkins
  Then `evo analyze .` auto-discovers it.

ADAPTER CONTRACT
----------------

Your adapter class must:

  1. Set four class attributes:
     - source_family:    "ci", "deployment", "dependency", etc.
     - source_type:      your unique name (e.g. "jenkins")
     - ordering_mode:    "temporal" (most adapters) or "causal" (git-like)
     - attestation_tier: "strong", "medium", or "weak"

  2. Set self.source_id in __init__() (unique instance identifier)

  3. Implement iter_events() that yields SourceEvent dicts:

     {
         "source_family": "ci",
         "source_type": "jenkins",
         "source_id": "jenkins:my-server",
         "ordering_mode": "temporal",
         "attestation": {
             "type": "jenkins_build",
             "trust_tier": "medium",
         },
         "predecessor_refs": None,
         "payload": {
             "run_id": "123",
             "status": "success",
             "duration_seconds": 300,
             "trigger": {
                 "commit_sha": "abc123def456",
             },
         },
     }

IMPORTANT: Include trigger.commit_sha in the payload so evo can
correlate events across families (Phase 4 pattern discovery).

PLUGIN REGISTRATION
-------------------

Your package must register an entry point in pyproject.toml:

  [project.entry-points."evo.adapters"]
  jenkins = "evo_jenkins:register"

The register() function returns a list of detector descriptors:

  def register():
      return [{
          "pattern": "Jenkinsfile",        # file that triggers detection
          "adapter_name": "jenkins",
          "family": "ci",
          "adapter_class": "evo_jenkins.JenkinsAdapter",
      }]

VALIDATION (13 CHECKS)
----------------------

Run before publishing:

  evo adapter validate evo_jenkins.JenkinsAdapter

Checks: required attributes, valid family, iter_events() works,
event structure, family consistency, attestation format, JSON
serializable, and more.

SOURCE FAMILIES
---------------

  ci          - CI/build systems (Jenkins, GitLab CI, CircleCI, etc.)
  deployment  - Release/deploy tools (ArgoCD, AWS CodeDeploy, etc.)
  dependency  - Package managers (Maven, NuGet, Composer, etc.)
  testing     - Test frameworks (Jest, Go test, etc.)
  schema      - API schemas (GraphQL, Protobuf, etc.)
  config      - Infrastructure as Code (Kubernetes, Helm, etc.)
  security    - Security scanners (Snyk, OWASP, etc.)

DON'T WANT TO BUILD IT YOURSELF?
---------------------------------

Request an adapter:

  evo adapter request "Jenkins CI adapter" --family ci

Or open an issue:

  https://github.com/evolution-engine/evolution-engine/issues/new
  Label: adapter-request

Popular requests get built into the core package.
"""
    click.echo(guide)
