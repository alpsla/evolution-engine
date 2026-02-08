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
        Walk commits and yield (commit, family, adapter, committed_at) tuples.
        
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
