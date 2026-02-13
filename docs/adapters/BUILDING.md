# Step-by-Step Adapter Building Guide

This guide walks you through building, testing, and publishing an Evolution
Engine adapter plugin.

## Prerequisites

- Python 3.9+
- `pip install evolution-engine` (latest version)

## 1. Scaffold Your Adapter

```bash
evo adapter new jenkins --family ci --output ~/projects
```

This creates:
```
~/projects/evo-adapter-jenkins/
├── evo_jenkins/
│   └── __init__.py       # Your adapter code goes here
├── tests/
│   └── test_adapter.py   # Test template
├── pyproject.toml         # Package metadata + entry point
├── README.md              # Documentation template
└── LICENSE
```

## 2. Understand the Adapter Contract

Every adapter class must have these 4 class attributes:

| Attribute | Type | Values |
|-----------|------|--------|
| `source_family` | str | `ci`, `testing`, `dependency`, `schema`, `deployment`, `config`, `security` |
| `source_type` | str | Identifier for your tool (e.g. `"jenkins"`, `"pytest_cov"`) |
| `ordering_mode` | str | `"temporal"` (time-ordered) or `"causal"` (dependency-ordered) |
| `attestation_tier` | str | `"strong"` (cryptographic), `"medium"` (API-verified), `"weak"` (self-reported) |

And implement one method:

```python
def iter_events(self) -> Iterator[dict]:
    """Yield SourceEvent dicts."""
    yield {
        "source_family": self.source_family,
        "source_type": self.source_type,
        "source_id": self.source_id,
        "ordering_mode": self.ordering_mode,
        "attestation": {"trust_tier": self.attestation_tier},
        "payload": {
            # Your event data here
            "trigger": {"commit_sha": "abc123"},
        },
    }
```

## 3. Implement Your Adapter

Edit `evo_jenkins/__init__.py`:

```python
class JenkinsAdapter:
    source_family = "ci"
    source_type = "jenkins"
    ordering_mode = "temporal"
    attestation_tier = "medium"

    def __init__(self, url=None, token=None):
        self.url = url or os.environ.get("JENKINS_URL", "")
        self.token = token or os.environ.get("JENKINS_TOKEN", "")
        self.source_id = f"jenkins:{self.url}"

    def iter_events(self):
        # Fetch data from Jenkins API
        builds = self._fetch_builds()
        for build in builds:
            yield {
                "source_family": self.source_family,
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {"trust_tier": self.attestation_tier},
                "payload": {
                    "build_number": build["number"],
                    "result": build["result"],
                    "duration_ms": build["duration"],
                    "trigger": {"commit_sha": build.get("commit", "")},
                },
            }
```

### Family-Specific Payload Examples

**CI** (`source_family = "ci"`):
```python
"payload": {
    "build_number": 42,
    "result": "SUCCESS",        # or "FAILURE", "UNSTABLE"
    "duration_ms": 45000,
    "trigger": {"commit_sha": "abc123"},
}
```

**Testing** (`source_family = "testing"`):
```python
"payload": {
    "line_rate": 0.85,
    "branch_rate": 0.72,
    "tests_passed": 150,
    "tests_failed": 3,
    "trigger": {"commit_sha": "abc123"},
}
```

**Deployment** (`source_family = "deployment"`):
```python
"payload": {
    "environment": "production",
    "version": "2.1.0",
    "deploy_time": "2024-01-15T10:30:00Z",
    "trigger": {"commit_sha": "abc123"},
}
```

## 4. Test Locally

```bash
cd ~/projects/evo-adapter-jenkins
pip install -e .

# Validate against the contract
evo adapter validate evo_jenkins.JenkinsAdapter --args '{"url": "http://ci"}'

# Security scan
evo adapter security-check evo_jenkins
```

## 5. Register via Entry Points

The scaffolded `pyproject.toml` already includes the entry point:

```toml
[project.entry-points."evo.adapters"]
evo-adapter-jenkins = "evo_jenkins:register"
```

And the `register()` function in `__init__.py`:

```python
def register():
    return [{
        "pattern": "Jenkinsfile",           # Tier 1: file detection
        "adapter_name": "jenkins",
        "family": "ci",
        "adapter_class": "evo_jenkins.JenkinsAdapter",
    }]
```

## 6. Publish to PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

After publishing, anyone can install and use your adapter:

```bash
pip install evo-adapter-jenkins
evo adapter list .  # Automatically detected
```

## 7. AI-Assisted Development

Generate a complete prompt for AI coding assistants:

```bash
evo adapter prompt jenkins --family ci -d "Fetch builds from Jenkins API" --copy
# Paste into Claude, ChatGPT, Cursor, etc.
```

The prompt includes the full adapter contract, examples, and validation
checklist. The AI will generate a complete, working adapter.
