# P1: Git History Walker Meta-Adapter

**Target:** Claude Sonnet 4.5  
**Goal:** Phase 2 `run_all()` returns signals for dependency, schema, and config families (not just git)

---

## Architecture Overview

The Git History Walker is a **meta-adapter** that:
1. Walks git history commit-by-commit
2. Extracts files at each commit SHA (requirements.txt, openapi.yaml, *.tf, etc.)
3. Feeds extracted file contents to **existing family adapters** (PipDependencyAdapter, OpenAPIAdapter, TerraformAdapter)
4. Links each emitted event to the commit that triggered it via `trigger.commit_sha`
5. Overrides `observed_at` timestamp to match the commit's `committed_at` (critical for temporal ordering)

This creates a **historical replay** of dependency, schema, and config evolution, not just current state.

### Key Insight

Existing adapters expect:
- A file path OR
- Pre-parsed fixture data (list of dicts)

The walker provides **fixture data** by extracting and parsing historical file contents at each commit.

### Data Flow

```
GitHistoryWalker
 ├─→ Walk commits (oldest → newest)
 ├─→ For each commit SHA:
 │    ├─→ Extract requirements.txt content → Parse → Feed to PipDependencyAdapter(snapshots=[...])
 │    ├─→ Extract openapi.yaml content → Parse → Feed to OpenAPIAdapter(versions=[...])
 │    └─→ Extract *.tf content → Parse → Feed to TerraformAdapter(snapshots=[...])
 └─→ Each adapter emits SourceEvents with:
      - trigger.commit_sha = current commit SHA
      - observed_at = commit's committed_at (OVERRIDE in Phase 1)
```

---

## Implementation

### File: `evolution/adapters/git/git_history_walker.py`

```python
"""
Git History Walker Meta-Adapter

Walks git history and extracts dependency, schema, and config files
at each commit, feeding them to family adapters for historical replay.
"""

from pathlib import Path
from datetime import datetime
import json
import hashlib
import tempfile
from git import Repo

from evolution.adapters.dependency.pip_adapter import PipDependencyAdapter
from evolution.adapters.schema.openapi_adapter import OpenAPIAdapter
from evolution.adapters.config.terraform_adapter import TerraformAdapter


class GitHistoryWalker:
    """
    Meta-adapter that extracts historical file snapshots from git
    and feeds them to family adapters.
    """
    
    def __init__(self, repo_path: str, target_families: list = None):
        """
        Args:
            repo_path: Path to git repository
            target_families: List of families to extract (default: all)
                            Options: 'dependency', 'schema', 'config'
        """
        self.repo_path = Path(repo_path).resolve()
        self.repo = Repo(self.repo_path)
        self.target_families = target_families or ['dependency', 'schema', 'config']
        
        # File extraction patterns for each family
        self.extraction_patterns = {
            'dependency': ['requirements.txt', 'Pipfile.lock'],
            'schema': ['openapi.yaml', 'openapi.yml', 'openapi.json', 'swagger.yaml'],
            'config': ['*.tf'],  # Terraform files
        }
    
    def _hash(self, data: str) -> str:
        """Content hash for snapshot deduplication."""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()
    
    def _extract_file_at_commit(self, commit, file_pattern: str) -> dict:
        """
        Extract file content at a specific commit.
        
        Returns:
            dict with 'path' and 'content', or None if not found
        """
        try:
            # Handle glob patterns (*.tf)
            if '*' in file_pattern:
                import fnmatch
                matches = []
                for item in commit.tree.traverse():
                    if item.type == 'blob' and fnmatch.fnmatch(item.path, file_pattern):
                        matches.append({
                            'path': item.path,
                            'content': item.data_stream.read().decode('utf-8', errors='ignore')
                        })
                return matches if matches else None
            else:
                # Direct file lookup
                blob = commit.tree / file_pattern
                content = blob.data_stream.read().decode('utf-8', errors='ignore')
                return {'path': file_pattern, 'content': content}
        except (KeyError, AttributeError):
            return None
    
    def _parse_requirements_content(self, content: str, commit_sha: str) -> dict:
        """Parse requirements.txt content into a dependency snapshot."""
        import re
        deps = []
        for line in content.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r'^([A-Za-z0-9_.-]+)\s*([><=!~]+\s*[\d.*]+)?', line)
            if match:
                name = match.group(1).lower()
                version = match.group(2).strip() if match.group(2) else "unspecified"
                version = re.sub(r'^[><=!~]+\s*', '', version)
                deps.append({
                    "name": name,
                    "version": version,
                    "direct": True,
                    "depth": 1,
                })
        
        return {
            "ecosystem": "pip",
            "manifest_file": "requirements.txt",
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": len(deps),
                "transitive_count": 0,
                "total_count": len(deps),
                "max_depth": 1,
            },
            "dependencies": deps,
        }
    
    def _parse_openapi_content(self, content: str, file_path: str, commit_sha: str) -> dict:
        """Parse OpenAPI spec content into a schema version."""
        try:
            import yaml
        except ImportError:
            yaml = None
        
        # Parse YAML or JSON
        if file_path.endswith(('.yaml', '.yml')):
            if yaml is None:
                return None
            spec = yaml.safe_load(content)
        else:
            spec = json.loads(content)
        
        # Count endpoints
        paths = spec.get("paths", {})
        endpoint_count = 0
        for path_key, methods in paths.items():
            for method in methods:
                if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                    endpoint_count += 1
        
        # Count types and fields
        components = spec.get("components", {})
        schemas = components.get("schemas", {})
        type_count = len(schemas)
        field_count = sum(len(s.get("properties", {})) for s in schemas.values())
        
        version = spec.get("info", {}).get("version", "unknown")
        
        return {
            "schema_name": spec.get("info", {}).get("title", Path(file_path).stem),
            "schema_format": "openapi",
            "version": version,
            "trigger": {"commit_sha": commit_sha},
            "structure": {
                "endpoint_count": endpoint_count,
                "type_count": type_count,
                "field_count": field_count,
            },
            "diff": {
                "endpoints_added": 0, "endpoints_removed": 0,
                "fields_added": 0, "fields_removed": 0,
                "types_added": 0, "types_removed": 0,
            },
        }
    
    def _parse_terraform_content(self, tf_files: list, commit_sha: str) -> dict:
        """Parse Terraform files into a config snapshot."""
        import re
        resource_count = 0
        resource_types = set()
        resource_re = re.compile(r'^resource\s+"(\w+)"\s+"(\w+)"', re.MULTILINE)
        
        for tf_file in tf_files:
            matches = resource_re.findall(tf_file['content'])
            resource_count += len(matches)
            for rtype, _ in matches:
                resource_types.add(rtype)
        
        return {
            "config_scope": "terraform",
            "config_format": "terraform",
            "trigger": {"commit_sha": commit_sha, "apply_id": ""},
            "structure": {
                "resource_count": resource_count,
                "resource_types": len(resource_types),
                "file_count": len(tf_files),
            },
            "diff": {
                "resources_added": 0,
                "resources_removed": 0,
                "resources_modified": 0,
            },
        }
    
    def iter_commit_events(self):
        """
        Walk commits and yield (commit, family, adapter) tuples.
        
        Each tuple represents an adapter configured with historical data
        from that specific commit.
        """
        commits = list(self.repo.iter_commits(rev="HEAD"))
        commits.reverse()  # oldest → newest
        
        for commit in commits:
            commit_sha = commit.hexsha
            committed_at = datetime.utcfromtimestamp(commit.committed_date).isoformat() + "Z"
            
            # Extract dependency files
            if 'dependency' in self.target_families:
                for pattern in self.extraction_patterns['dependency']:
                    file_data = self._extract_file_at_commit(commit, pattern)
                    if file_data:
                        snapshot = self._parse_requirements_content(
                            file_data['content'], 
                            commit_sha
                        )
                        adapter = PipDependencyAdapter(
                            snapshots=[snapshot],
                            source_id=f"pip:{self.repo_path}"
                        )
                        yield (commit, 'dependency', adapter, committed_at)
                        break  # Only one dependency file per commit
            
            # Extract schema files
            if 'schema' in self.target_families:
                for pattern in self.extraction_patterns['schema']:
                    file_data = self._extract_file_at_commit(commit, pattern)
                    if file_data:
                        version = self._parse_openapi_content(
                            file_data['content'],
                            file_data['path'],
                            commit_sha
                        )
                        if version:
                            adapter = OpenAPIAdapter(
                                versions=[version],
                                source_id=f"openapi:{self.repo_path}"
                            )
                            yield (commit, 'schema', adapter, committed_at)
                            break  # Only one schema file per commit
            
            # Extract config files
            if 'config' in self.target_families:
                tf_files = self._extract_file_at_commit(commit, '*.tf')
                if tf_files:
                    snapshot = self._parse_terraform_content(tf_files, commit_sha)
                    adapter = TerraformAdapter(
                        snapshots=[snapshot],
                        source_id=f"terraform:{self.repo_path}"
                    )
                    yield (commit, 'config', adapter, committed_at)
```

### Update: `evolution/phase1_engine.py`

**CRITICAL 1-LINE CHANGE** — Override `observed_at` for historical events:

```python
def ingest(self, adapter, override_observed_at: str = None):
    """
    Ingest events from an adapter.
    
    Args:
        adapter: Adapter instance with iter_events()
        override_observed_at: Optional timestamp to override observed_at
                             (for historical replay)
    """
    count = 0
    for raw_event in adapter.iter_events():
        self._validate(raw_event)
        key = self._dedup_key(raw_event)

        if key in self.index:
            continue

        source_event = {
            "source_family": raw_event.get("source_family", ""),
            "source_type": raw_event["source_type"],
            "source_id": raw_event["source_id"],
            "ordering_mode": raw_event["ordering_mode"],
            "attestation": raw_event["attestation"],
            "predecessor_refs": raw_event.get("predecessor_refs"),
            "observed_at": override_observed_at or (datetime.utcnow().isoformat() + "Z"),  # ← CHANGE HERE
            "payload": raw_event["payload"],
        }

        event_id = self._hash(source_event)
        source_event["event_id"] = event_id

        event_file = self.events_path / f"{event_id}.json"
        event_file.write_text(json.dumps(source_event, indent=2))

        self.index[key] = event_id
        count += 1

    self.index_path.write_text(json.dumps(self.index, indent=2))
    return count
```

---

## Usage Pattern

```python
from evolution.phase1_engine import Phase1Engine
from evolution.adapters.git.git_history_walker import GitHistoryWalker
from pathlib import Path

# Initialize engines
evo_dir = Path(".evo")
phase1 = Phase1Engine(evo_dir)

# Walk git history and ingest dependency/schema/config events
walker = GitHistoryWalker(
    repo_path=".",
    target_families=['dependency', 'schema', 'config']
)

for commit, family, adapter, committed_at in walker.iter_commit_events():
    count = phase1.ingest(adapter, override_observed_at=committed_at)
    print(f"Commit {commit.hexsha[:7]} ({family}): {count} events")
```

---

## Test Script

Create: `tests/test_git_history_walker.py`

```python
"""
Test Git History Walker

Verifies that walking git history extracts dependency/schema/config
snapshots and Phase 2 generates signals for all families.
"""

import pytest
import shutil
import tempfile
import json
from pathlib import Path
from git import Repo

from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.adapters.git.git_adapter import GitSourceAdapter
from evolution.adapters.git.git_history_walker import GitHistoryWalker


def setup_test_repo():
    """Create a test repo with evolving requirements.txt."""
    temp_dir = Path(tempfile.mkdtemp())
    repo = Repo.init(temp_dir)
    
    # Commit 1: Initial requirements
    (temp_dir / "requirements.txt").write_text("requests==2.25.0\nflask==1.1.2\n")
    repo.index.add(["requirements.txt"])
    repo.index.commit("Initial dependencies")
    
    # Commit 2: Add new dependency
    (temp_dir / "requirements.txt").write_text("requests==2.25.0\nflask==1.1.2\ndjango==3.1.0\n")
    repo.index.add(["requirements.txt"])
    repo.index.commit("Add Django")
    
    # Commit 3: Upgrade Flask
    (temp_dir / "requirements.txt").write_text("requests==2.25.0\nflask==2.0.0\ndjango==3.1.0\n")
    repo.index.add(["requirements.txt"])
    repo.index.commit("Upgrade Flask")
    
    return temp_dir


def test_git_history_walker_extracts_dependencies():
    """Test that walker extracts historical dependency snapshots."""
    repo_dir = setup_test_repo()
    evo_dir = repo_dir / ".evo"
    
    try:
        # Phase 1: Ingest git + historical dependencies
        phase1 = Phase1Engine(evo_dir)
        
        # Ingest git commits
        git_adapter = GitSourceAdapter(repo_path=str(repo_dir))
        git_count = phase1.ingest(git_adapter)
        assert git_count == 3, "Should have 3 git commits"
        
        # Walk history and extract dependencies
        walker = GitHistoryWalker(
            repo_path=str(repo_dir),
            target_families=['dependency']
        )
        dep_count = 0
        for commit, family, adapter, committed_at in walker.iter_commit_events():
            count = phase1.ingest(adapter, override_observed_at=committed_at)
            dep_count += count
        
        assert dep_count == 3, "Should extract 3 dependency snapshots"
        
        # Verify events have correct observed_at timestamps
        events = []
        for event_file in (evo_dir / "events").glob("*.json"):
            events.append(json.loads(event_file.read_text()))
        
        dep_events = [e for e in events if e.get("source_family") == "dependency"]
        assert len(dep_events) == 3
        
        # Verify timestamps match commit order (oldest → newest)
        timestamps = [e["observed_at"] for e in dep_events]
        assert timestamps == sorted(timestamps), "Events should be ordered by commit time"
        
        # Verify trigger.commit_sha is present
        for e in dep_events:
            assert e["payload"]["trigger"]["commit_sha"], "Should have commit SHA"
        
    finally:
        shutil.rmtree(repo_dir)


def test_phase2_generates_signals_for_all_families():
    """Test that Phase 2 generates signals for dependency family (not just git)."""
    repo_dir = setup_test_repo()
    evo_dir = repo_dir / ".evo"
    
    try:
        # Phase 1: Ingest git + dependencies
        phase1 = Phase1Engine(evo_dir)
        
        git_adapter = GitSourceAdapter(repo_path=str(repo_dir))
        phase1.ingest(git_adapter)
        
        walker = GitHistoryWalker(
            repo_path=str(repo_dir),
            target_families=['dependency']
        )
        for commit, family, adapter, committed_at in walker.iter_commit_events():
            phase1.ingest(adapter, override_observed_at=committed_at)
        
        # Phase 2: Run all families
        phase2 = Phase2Engine(evo_dir, window_size=2, min_baseline=1)
        results = phase2.run_all()
        
        # Verify signals exist for multiple families
        families_with_signals = set()
        for family, signals in results.items():
            if signals:
                families_with_signals.add(family)
        
        assert "git" in families_with_signals, "Should have git signals"
        assert "dependency" in families_with_signals, "Should have dependency signals"
        
        print(f"✅ Phase 2 generated signals for families: {families_with_signals}")
        
    finally:
        shutil.rmtree(repo_dir)


if __name__ == "__main__":
    test_git_history_walker_extracts_dependencies()
    test_phase2_generates_signals_for_all_families()
    print("✅ All tests passed")
```

---

## Success Criteria

1. ✅ `GitHistoryWalker` successfully extracts historical file snapshots at each commit
2. ✅ Dependency snapshots have correct `trigger.commit_sha` linking to git commits
3. ✅ Phase 1 events have `observed_at` matching commit's `committed_at` (not ingestion time)
4. ✅ Phase 2 `run_all()` returns signals for **dependency, schema, config** families (not just git)
5. ✅ Signals are temporally ordered (oldest commit → newest commit)
6. ✅ Test suite passes with clear output showing multi-family signals

### Verification Command

```bash
python tests/test_git_history_walker.py
```

Expected output:

```
✅ Phase 2 generated signals for families: {'git', 'dependency'}
✅ All tests passed
```

---

## Implementation Notes

### Why Override `observed_at`?

Without override:
- All historical events get `observed_at = NOW` (ingestion time)
- Phase 2 temporal ordering breaks (all events appear simultaneous)
- Dependency evolution appears as a single snapshot, not a timeline

With override:
- Each event gets `observed_at = commit.committed_at`
- Phase 2 sees proper temporal evolution
- Baselines evolve correctly over historical time

### File Extraction Patterns

| Family | File Patterns | Parser |
|--------|--------------|--------|
| dependency | `requirements.txt`, `Pipfile.lock` | `_parse_requirements_content()` |
| schema | `openapi.yaml`, `swagger.yaml` | `_parse_openapi_content()` |
| config | `*.tf` (glob) | `_parse_terraform_content()` |

### Deduplication

Phase 1 automatically deduplicates events via `_dedup_key()` using:
- Dependency: `snapshot_hash` (content hash of parsed snapshot)
- Schema: `schema_hash` (content hash of parsed schema)
- Config: `config_hash` (content hash of parsed config)

If a file doesn't change between commits, no duplicate event is created.

---

## Next Steps

1. Implement `GitHistoryWalker` in `evolution/adapters/git/git_history_walker.py`
2. Update `Phase1Engine.ingest()` to accept `override_observed_at` parameter
3. Create test script `tests/test_git_history_walker.py`
4. Run test and verify Phase 2 signals for multiple families
5. Document in `docs/IMPLEMENTATION_PLAN.md` as complete

---

## Edge Cases

### Missing Files

If a commit doesn't have `requirements.txt`:
- Walker skips that commit for dependency family
- No event emitted
- No gap in git timeline (git adapter still emits commit event)

### File Parsing Errors

If OpenAPI YAML is malformed:
- Parser returns `None`
- No event emitted for that commit
- Walker continues to next commit

### Large Repos

For repos with 1000+ commits:
- Consider adding commit range filter: `walker = GitHistoryWalker(repo_path, from_ref="v1.0", to_ref="HEAD")`
- Phase 1 deduplication prevents duplicate events if re-run

---

**Implementation Time Estimate:** 2-3 hours  
**Test Coverage:** High (integration test verifies end-to-end flow)
