"""
Git History Walker Meta-Adapter

Walks git history and extracts dependency, schema, and config files
at each commit, feeding them to family adapters for historical replay.
"""

from pathlib import Path
from datetime import datetime
import json
import hashlib
import re
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
        # Ordered by preference: lockfiles before manifests
        self.extraction_patterns = {
            'dependency': [
                'go.sum', 'go.mod',
                'package-lock.json', 'yarn.lock',
                'Cargo.lock',
                'Gemfile.lock',
                'requirements.txt', 'Pipfile.lock',
            ],
            'schema': ['openapi.yaml', 'openapi.yml', 'openapi.json', 'swagger.yaml'],
            'config': ['*.tf'],  # Terraform files
        }

        # Maps file pattern to parser method name
        self.dependency_parsers = {
            'go.sum': '_parse_gosum_content',
            'go.mod': '_parse_gomod_content',
            'package-lock.json': '_parse_package_lock_content',
            'yarn.lock': '_parse_yarn_lock_content',
            'Cargo.lock': '_parse_cargo_lock_content',
            'Gemfile.lock': '_parse_gemfile_lock_content',
            'requirements.txt': '_parse_requirements_content',
            'Pipfile.lock': '_parse_requirements_content',
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
    
    def _parse_requirements_content(self, content: str, commit_sha: str,
                                     manifest_file: str = "requirements.txt") -> dict:
        """Parse requirements.txt / Pipfile.lock content into a dependency snapshot."""
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
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": len(deps),
                "transitive_count": 0,
                "total_count": len(deps),
                "max_depth": 1,
            },
            "dependencies": deps,
        }

    def _parse_gosum_content(self, content: str, commit_sha: str,
                              manifest_file: str = "go.sum") -> dict:
        """Parse go.sum — count unique module paths (skip /go.mod lines)."""
        modules = set()
        for line in content.strip().splitlines():
            line = line.strip()
            if not line or '/go.mod ' in line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                modules.add(parts[0])

        total_count = len(modules)
        return {
            "ecosystem": "go",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": 0,
                "transitive_count": total_count,
                "total_count": total_count,
                "max_depth": 2,
            },
            "dependencies": [],
        }

    def _parse_gomod_content(self, content: str, commit_sha: str,
                              manifest_file: str = "go.mod") -> dict:
        """Parse go.mod require blocks into direct dependencies."""
        deps = []
        in_require_block = False

        for line in content.splitlines():
            line = line.strip()
            if line.startswith('require ('):
                in_require_block = True
                continue
            if in_require_block and line == ')':
                in_require_block = False
                continue
            if in_require_block:
                if not line or line.startswith('//'):
                    continue
                match = re.match(r'^([^\s]+)\s+(v[\d.]+.*?)(?:\s|$)', line)
                if match:
                    deps.append({
                        "name": match.group(1),
                        "version": match.group(2),
                        "direct": True,
                        "depth": 1,
                    })

        return {
            "ecosystem": "go",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": len(deps),
                "transitive_count": 0,
                "total_count": len(deps),
                "max_depth": 1,
            },
            "dependencies": deps,
        }

    def _parse_package_lock_content(self, content: str, commit_sha: str,
                                     manifest_file: str = "package-lock.json") -> dict:
        """Parse package-lock.json (npm v6 + v7+ formats)."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return self._empty_dependency_snapshot("npm", manifest_file, commit_sha)

        if "packages" in data:
            total_count = len([k for k in data["packages"].keys() if k])
        elif "dependencies" in data:
            total_count = len(data["dependencies"])
        else:
            total_count = 0

        return {
            "ecosystem": "npm",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": 0,
                "transitive_count": total_count,
                "total_count": total_count,
                "max_depth": 2,
            },
            "dependencies": [],
        }

    def _parse_yarn_lock_content(self, content: str, commit_sha: str,
                                  manifest_file: str = "yarn.lock") -> dict:
        """Parse yarn.lock — count package header lines."""
        package_count = 0
        for line in content.splitlines():
            if re.match(r'^"?[a-zA-Z@].*:$', line):
                package_count += 1

        return {
            "ecosystem": "npm",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": 0,
                "transitive_count": package_count,
                "total_count": package_count,
                "max_depth": 2,
            },
            "dependencies": [],
        }

    def _parse_cargo_lock_content(self, content: str, commit_sha: str,
                                   manifest_file: str = "Cargo.lock") -> dict:
        """Parse Cargo.lock — count [[package]] sections minus root crate."""
        package_count = 0
        for line in content.splitlines():
            if line.strip() == '[[package]]':
                package_count += 1

        total_count = max(0, package_count - 1)
        return {
            "ecosystem": "cargo",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": 0,
                "transitive_count": total_count,
                "total_count": total_count,
                "max_depth": 2,
            },
            "dependencies": [],
        }

    def _parse_gemfile_lock_content(self, content: str, commit_sha: str,
                                     manifest_file: str = "Gemfile.lock") -> dict:
        """Parse Gemfile.lock GEM/specs section."""
        in_gem_section = False
        in_specs_section = False
        direct_count = 0
        total_count = 0

        for line in content.splitlines():
            if line.strip() == 'GEM':
                in_gem_section = True
                continue
            if in_gem_section and line.strip().startswith('specs:'):
                in_specs_section = True
                continue
            if in_specs_section and line and not line.startswith(' '):
                break
            if in_specs_section and line.startswith('    '):
                if not line.startswith('      '):
                    direct_count += 1
                total_count += 1

        return {
            "ecosystem": "bundler",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": direct_count,
                "transitive_count": total_count - direct_count,
                "total_count": total_count,
                "max_depth": 2,
            },
            "dependencies": [],
        }

    def _empty_dependency_snapshot(self, ecosystem: str, manifest_file: str,
                                   commit_sha: str) -> dict:
        """Return an empty dependency snapshot for error/fallback cases."""
        return {
            "ecosystem": ecosystem,
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": 0,
                "transitive_count": 0,
                "total_count": 0,
                "max_depth": 0,
            },
            "dependencies": [],
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
    
    def _process_commit(self, commit):
        """Process a single commit, extracting all family data.

        Returns a list of (family, adapter, committed_at) tuples.
        Thread-safe: only reads git objects (no shared mutable state).
        """
        results = []
        commit_sha = commit.hexsha
        committed_at = datetime.utcfromtimestamp(commit.committed_date).isoformat() + "Z"

        # Dependency
        if 'dependency' in self.target_families:
            for pattern in self.extraction_patterns['dependency']:
                file_data = self._extract_file_at_commit(commit, pattern)
                if file_data:
                    parser_name = self.dependency_parsers.get(pattern)
                    if parser_name:
                        parser = getattr(self, parser_name)
                        snapshot = parser(
                            file_data['content'],
                            commit_sha,
                            manifest_file=pattern,
                        )
                        adapter = PipDependencyAdapter(
                            snapshots=[snapshot],
                            source_id=f"{snapshot['ecosystem']}:{self.repo_path}"
                        )
                        results.append(('dependency', adapter, committed_at))
                        break

        # Schema
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
                        results.append(('schema', adapter, committed_at))
                        break

        # Config
        if 'config' in self.target_families:
            tf_files = self._extract_file_at_commit(commit, '*.tf')
            if tf_files:
                snapshot = self._parse_terraform_content(tf_files, commit_sha)
                adapter = TerraformAdapter(
                    snapshots=[snapshot],
                    source_id=f"terraform:{self.repo_path}"
                )
                results.append(('config', adapter, committed_at))

        return results

    def iter_commit_events(self):
        """
        Walk commits and yield (commit, family, adapter, committed_at) tuples.

        Each tuple represents an adapter configured with historical data
        from that specific commit.
        """
        commits = list(self.repo.iter_commits(rev="HEAD"))
        commits.reverse()  # oldest → newest

        for commit in commits:
            for family, adapter, committed_at in self._process_commit(commit):
                yield (commit, family, adapter, committed_at)

    def _git_show(self, commit_sha: str, file_path: str) -> str | None:
        """Read file content at a commit using subprocess (thread-safe).

        Unlike GitPython's tree traversal, each call spawns an independent
        git process, so it's safe to call from multiple threads.
        """
        import subprocess
        try:
            result = subprocess.run(
                ["git", "show", f"{commit_sha}:{file_path}"],
                cwd=str(self.repo_path),
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.decode("utf-8", errors="ignore")
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None

    def _git_ls_tree(self, commit_sha: str, pattern: str) -> list[str]:
        """List files matching a glob pattern at a commit (thread-safe)."""
        import subprocess
        import fnmatch
        try:
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", commit_sha],
                cwd=str(self.repo_path),
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                paths = result.stdout.decode("utf-8", errors="ignore").splitlines()
                return [p for p in paths if fnmatch.fnmatch(p, pattern)]
        except (subprocess.TimeoutExpired, OSError):
            pass
        return []

    def _process_commit_subprocess(self, commit_sha: str, committed_at: str):
        """Process a single commit using subprocess git calls (thread-safe).

        Returns a list of (family, adapter, committed_at) tuples.
        """
        results = []

        # Dependency
        if 'dependency' in self.target_families:
            for pattern in self.extraction_patterns['dependency']:
                if '*' in pattern:
                    continue  # dependency patterns are exact filenames
                content = self._git_show(commit_sha, pattern)
                if content:
                    parser_name = self.dependency_parsers.get(pattern)
                    if parser_name:
                        parser = getattr(self, parser_name)
                        snapshot = parser(content, commit_sha, manifest_file=pattern)
                        adapter = PipDependencyAdapter(
                            snapshots=[snapshot],
                            source_id=f"{snapshot['ecosystem']}:{self.repo_path}"
                        )
                        results.append(('dependency', adapter, committed_at))
                        break

        # Schema
        if 'schema' in self.target_families:
            for pattern in self.extraction_patterns['schema']:
                content = self._git_show(commit_sha, pattern)
                if content:
                    version = self._parse_openapi_content(content, pattern, commit_sha)
                    if version:
                        adapter = OpenAPIAdapter(
                            versions=[version],
                            source_id=f"openapi:{self.repo_path}"
                        )
                        results.append(('schema', adapter, committed_at))
                        break

        # Config (glob pattern)
        if 'config' in self.target_families:
            tf_paths = self._git_ls_tree(commit_sha, '*.tf')
            if tf_paths:
                tf_files = []
                for tf_path in tf_paths:
                    content = self._git_show(commit_sha, tf_path)
                    if content:
                        tf_files.append({'path': tf_path, 'content': content})
                if tf_files:
                    snapshot = self._parse_terraform_content(tf_files, commit_sha)
                    adapter = TerraformAdapter(
                        snapshots=[snapshot],
                        source_id=f"terraform:{self.repo_path}"
                    )
                    results.append(('config', adapter, committed_at))

        return results

    def iter_commit_events_parallel(self, max_workers: int = 4, batch_size: int = 200):
        """Walk commits with parallel file extraction and parsing.

        Uses subprocess-based git access (not GitPython) so each thread
        has fully independent I/O. Processes commits in batches to control
        memory, yielding results in commit order.

        Args:
            max_workers: Number of threads for parallel extraction.
            batch_size: Commits per batch (controls memory and subprocess count).
        """
        from concurrent.futures import ThreadPoolExecutor

        # Use GitPython only to list commits (single-threaded, fast)
        commits = list(self.repo.iter_commits(rev="HEAD"))
        commits.reverse()  # oldest → newest
        total = len(commits)

        # Pre-extract sha + timestamp (lightweight, no tree access)
        commit_info = [
            (c.hexsha, datetime.utcfromtimestamp(c.committed_date).isoformat() + "Z")
            for c in commits
        ]

        for batch_start in range(0, total, batch_size):
            batch = commit_info[batch_start:batch_start + batch_size]
            batch_commits = commits[batch_start:batch_start + batch_size]

            with ThreadPoolExecutor(max_workers=max_workers,
                                    thread_name_prefix="walker") as executor:
                future_to_idx = {
                    executor.submit(
                        self._process_commit_subprocess, sha, ts
                    ): i
                    for i, (sha, ts) in enumerate(batch)
                }

                batch_results = [None] * len(batch)
                for future in future_to_idx:
                    idx = future_to_idx[future]
                    try:
                        batch_results[idx] = future.result()
                    except Exception:
                        batch_results[idx] = []

            # Yield in commit order
            for i, results in enumerate(batch_results):
                commit = batch_commits[i]
                for family, adapter, committed_at in (results or []):
                    yield (commit, family, adapter, committed_at)
