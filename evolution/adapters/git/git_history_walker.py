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
from evolution.adapters.testing.junit_adapter import JUnitXMLAdapter
from evolution.adapters.testing.coverage_adapter import CoberturaAdapter


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
        self.target_families = target_families or ['dependency', 'schema', 'config', 'testing', 'coverage']
        
        # File extraction patterns for each family
        # Ordered by preference: lockfiles before manifests
        self.extraction_patterns = {
            'dependency': [
                'go.sum', 'go.mod',
                'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
                'Cargo.lock',
                'Gemfile.lock',
                'requirements.txt', 'Pipfile.lock', 'pyproject.toml',
                'composer.lock',
                'build.gradle', 'build.gradle.kts', 'pom.xml',
                'Package.resolved',
                'CMakeLists.txt',
            ],
            'schema': ['openapi.yaml', 'openapi.yml', 'openapi.json', 'swagger.yaml'],
            'config': ['*.tf'],  # Terraform files
            'testing': [
                'junit.xml', 'test-results.xml',
                'TEST-*.xml',  # surefire-style
            ],
            'coverage': [
                'coverage.xml',
                'coverage/cobertura.xml',
                'coverage/coverage.xml',
            ],
        }

        # Maps file pattern to parser method name
        self.dependency_parsers = {
            'go.sum': '_parse_gosum_content',
            'go.mod': '_parse_gomod_content',
            'package-lock.json': '_parse_package_lock_content',
            'yarn.lock': '_parse_yarn_lock_content',
            'pnpm-lock.yaml': '_parse_pnpm_lock_content',
            'Cargo.lock': '_parse_cargo_lock_content',
            'Gemfile.lock': '_parse_gemfile_lock_content',
            'requirements.txt': '_parse_requirements_content',
            'Pipfile.lock': '_parse_requirements_content',
            'pyproject.toml': '_parse_pyproject_content',
            'composer.lock': '_parse_composer_lock_content',
            'build.gradle': '_parse_gradle_content',
            'build.gradle.kts': '_parse_gradle_content',
            'pom.xml': '_parse_pom_content',
            'Package.resolved': '_parse_swift_package_resolved_content',
            'CMakeLists.txt': '_parse_cmake_content_deps',
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

    def _parse_pnpm_lock_content(self, content: str, commit_sha: str,
                                  manifest_file: str = "pnpm-lock.yaml") -> dict:
        """Parse pnpm-lock.yaml — count package entries under packages: section."""
        package_count = 0
        in_packages = False

        for line in content.splitlines():
            # Detect top-level packages: key (no leading whitespace)
            if line.rstrip() == 'packages:':
                in_packages = True
                continue
            if in_packages:
                # A new top-level key ends the packages section
                if line and not line[0].isspace():
                    break
                # Package entries are at 2-space indentation only.
                # Deeper indentation (resolution:, dependencies:, dev:) is skipped.
                if not line.startswith('  ') or line.startswith('    '):
                    continue
                stripped = line.strip()
                if stripped and stripped.endswith(':') and not stripped.startswith('#'):
                    # pnpm v6: "/express/4.18.1:" or "/@scope/name/1.0.0:"
                    # pnpm v9: "express@4.18.1:" or "@scope/name@1.0.0:"
                    if stripped[0] in ('/', '@') or stripped[0].isalnum():
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

    def _parse_pyproject_content(self, content: str, commit_sha: str,
                                  manifest_file: str = "pyproject.toml") -> dict:
        """Parse pyproject.toml dependencies (PEP 621 and Poetry formats)."""
        deps = []

        # PEP 621: dependencies = ["requests>=2.28", ...]
        # Use greedy match up to ] at start of line or ] followed by newline/EOF
        pep621_match = re.search(
            r'^\s*dependencies\s*=\s*\[(.*?)\n\s*\]',
            content, re.MULTILINE | re.DOTALL
        )
        if pep621_match:
            for m in re.finditer(r'"([^"]+)"', pep621_match.group(1)):
                raw = m.group(1).strip()
                # Extract package name (before any version specifier or extras)
                name_match = re.match(r'^([A-Za-z0-9_.-]+)', raw)
                if name_match:
                    deps.append({
                        "name": name_match.group(1).lower(),
                        "version": "unspecified",
                        "direct": True,
                        "depth": 1,
                    })

        # Poetry: [tool.poetry.dependencies] section
        poetry_match = re.search(
            r'^\[tool\.poetry\.dependencies\]\s*\n(.*?)(?=^\[|\Z)',
            content, re.MULTILINE | re.DOTALL
        )
        if poetry_match and not deps:
            for line in poetry_match.group(1).splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                match = re.match(r'^([A-Za-z0-9_.-]+)\s*=', line)
                if match:
                    name = match.group(1).lower()
                    if name != 'python':
                        deps.append({
                            "name": name,
                            "version": "unspecified",
                            "direct": True,
                            "depth": 1,
                        })

        if not deps:
            return self._empty_dependency_snapshot("pip", manifest_file, commit_sha)

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

    def _parse_composer_lock_content(self, content: str, commit_sha: str,
                                      manifest_file: str = "composer.lock") -> dict:
        """Parse composer.lock (PHP) — count packages and packages-dev arrays."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return self._empty_dependency_snapshot("composer", manifest_file, commit_sha)

        direct_count = len(data.get("packages", []))
        dev_count = len(data.get("packages-dev", []))
        total_count = direct_count + dev_count

        return {
            "ecosystem": "composer",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": direct_count,
                "transitive_count": dev_count,
                "total_count": total_count,
                "max_depth": 1,
            },
            "dependencies": [],
        }

    def _parse_gradle_content(self, content: str, commit_sha: str,
                               manifest_file: str = "build.gradle") -> dict:
        """Parse build.gradle / build.gradle.kts dependency declarations."""
        # Match both Groovy and Kotlin DSL dependency declarations
        # Groovy: implementation 'group:artifact:version'
        # Kotlin: implementation("group:artifact:version")
        dep_pattern = re.compile(
            r'^\s*(?:implementation|api|compileOnly|runtimeOnly'
            r'|testImplementation|testRuntimeOnly|testCompileOnly'
            r'|compile|testCompile|runtime|provided'
            r'|annotationProcessor|kapt)'
            r'''[\s(]+['"]([^'"]+:[^'"]+)['"]''',
            re.MULTILINE
        )

        deps = dep_pattern.findall(content)

        # Separate test vs production
        test_pattern = re.compile(
            r'^\s*(?:testImplementation|testRuntimeOnly|testCompileOnly|testCompile)'
            r'''[\s(]+['"]([^'"]+:[^'"]+)['"]''',
            re.MULTILINE
        )
        test_deps = test_pattern.findall(content)
        prod_count = len(deps) - len(test_deps)

        if not deps:
            return self._empty_dependency_snapshot("gradle", manifest_file, commit_sha)

        return {
            "ecosystem": "gradle",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": prod_count,
                "transitive_count": len(test_deps),
                "total_count": len(deps),
                "max_depth": 1,
            },
            "dependencies": [],
        }

    def _parse_pom_content(self, content: str, commit_sha: str,
                            manifest_file: str = "pom.xml") -> dict:
        """Parse pom.xml — count <dependency> elements."""
        # Count all <dependency> blocks
        dep_blocks = re.findall(
            r'<dependency>\s*.*?</dependency>', content, re.DOTALL
        )
        total_count = len(dep_blocks)

        # Count test-scope dependencies
        test_count = sum(
            1 for b in dep_blocks if '<scope>test</scope>' in b
        )
        prod_count = total_count - test_count

        if total_count == 0:
            return self._empty_dependency_snapshot("maven", manifest_file, commit_sha)

        return {
            "ecosystem": "maven",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": prod_count,
                "transitive_count": test_count,
                "total_count": total_count,
                "max_depth": 1,
            },
            "dependencies": [],
        }

    def _parse_swift_package_resolved_content(self, content: str, commit_sha: str,
                                               manifest_file: str = "Package.resolved") -> dict:
        """Parse Swift Package.resolved — count pins array."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return self._empty_dependency_snapshot("swift", manifest_file, commit_sha)

        # v2 format (Xcode 13.3+): {"pins": [...], "version": 2}
        # v1 format: {"object": {"pins": [...]}, "version": 1}
        if data.get("version", 0) >= 2:
            pins = data.get("pins", [])
        else:
            pins = data.get("object", {}).get("pins", [])

        total_count = len(pins)
        return {
            "ecosystem": "swift",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": total_count,
                "transitive_count": 0,
                "total_count": total_count,
                "max_depth": 1,
            },
            "dependencies": [],
        }

    def _parse_cmake_content_deps(self, content: str, commit_sha: str,
                                   manifest_file: str = "CMakeLists.txt") -> dict:
        """Parse CMakeLists.txt — count find_package() and FetchContent_Declare() calls."""
        # find_package(Boost REQUIRED) or find_package(OpenSSL 1.1)
        find_packages = set(re.findall(
            r'find_package\s*\(\s*(\w+)', content
        ))

        # FetchContent_Declare(googletest ...) or FetchContent_Declare(fmt ...)
        fetch_content = set(re.findall(
            r'FetchContent_Declare\s*\(\s*(\w+)', content
        ))

        all_deps = find_packages | fetch_content
        total_count = len(all_deps)

        if total_count == 0:
            return self._empty_dependency_snapshot("cmake", manifest_file, commit_sha)

        return {
            "ecosystem": "cmake",
            "manifest_file": manifest_file,
            "trigger": {"commit_sha": commit_sha},
            "snapshot": {
                "direct_count": total_count,
                "transitive_count": 0,
                "total_count": total_count,
                "max_depth": 1,
            },
            "dependencies": [],
        }

    def _parse_junit_xml_content(self, content: str, commit_sha: str,
                                  manifest_file: str = "junit.xml") -> dict:
        """Parse JUnit XML content into a test run dict."""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return None

        # Handle both <testsuites> and <testsuite> root elements
        if root.tag == "testsuites":
            suites = list(root)
        else:
            suites = [root]

        total = passed = failed = skipped = errored = 0
        total_time = 0.0

        for suite in suites:
            for tc in suite.findall("testcase"):
                duration = float(tc.get("time", "0"))
                total_time += duration

                if tc.find("failure") is not None:
                    failed += 1
                elif tc.find("error") is not None:
                    errored += 1
                elif tc.find("skipped") is not None:
                    skipped += 1
                else:
                    passed += 1
                total += 1

        suite_name = suites[0].get("name", "unknown") if suites else "unknown"

        return {
            "suite_name": suite_name,
            "trigger": {"commit_sha": commit_sha},
            "execution": {
                "duration_seconds": round(total_time, 3),
            },
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errored": errored,
            },
        }

    def _parse_cobertura_xml_content(self, content: str, commit_sha: str) -> dict:
        """Parse Cobertura XML content into a coverage dict."""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return None

        line_rate = float(root.get("line-rate", "0"))
        branch_rate = float(root.get("branch-rate", "0"))
        lines_valid = int(root.get("lines-valid", "0"))
        lines_covered = int(root.get("lines-covered", "0"))
        branches_valid = int(root.get("branches-valid", "0"))
        branches_covered = int(root.get("branches-covered", "0"))
        packages = root.findall(".//package")

        return {
            "trigger": {"commit_sha": commit_sha},
            "line_rate": round(line_rate, 4),
            "branch_rate": round(branch_rate, 4),
            "lines_covered": lines_covered,
            "lines_missing": lines_valid - lines_covered,
            "branches_covered": branches_covered,
            "branches_missing": branches_valid - branches_covered,
            "packages_covered": len(packages),
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

        # Testing
        if 'testing' in self.target_families:
            for pattern in self.extraction_patterns['testing']:
                file_data = self._extract_file_at_commit(commit, pattern)
                if file_data:
                    # Handle glob results (list) vs single file (dict)
                    files = file_data if isinstance(file_data, list) else [file_data]
                    for f in files:
                        run = self._parse_junit_xml_content(
                            f['content'], commit_sha, f['path']
                        )
                        if run:
                            adapter = JUnitXMLAdapter(
                                runs=[run],
                                source_id=f"junit_xml:{self.repo_path}"
                            )
                            results.append(('testing', adapter, committed_at))
                    break  # first matching pattern wins

        # Coverage
        if 'coverage' in self.target_families:
            for pattern in self.extraction_patterns['coverage']:
                file_data = self._extract_file_at_commit(commit, pattern)
                if file_data:
                    files = file_data if isinstance(file_data, list) else [file_data]
                    for f in files:
                        report = self._parse_cobertura_xml_content(
                            f['content'], commit_sha
                        )
                        if report:
                            adapter = CoberturaAdapter(
                                reports=[report],
                                source_id=f"coverage_xml:{self.repo_path}"
                            )
                            results.append(('coverage', adapter, committed_at))
                    break  # first matching pattern wins

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

        # Testing
        if 'testing' in self.target_families:
            for pattern in self.extraction_patterns['testing']:
                if '*' in pattern:
                    paths = self._git_ls_tree(commit_sha, pattern)
                    if paths:
                        for fpath in paths:
                            content = self._git_show(commit_sha, fpath)
                            if content:
                                run = self._parse_junit_xml_content(
                                    content, commit_sha, fpath
                                )
                                if run:
                                    adapter = JUnitXMLAdapter(
                                        runs=[run],
                                        source_id=f"junit_xml:{self.repo_path}"
                                    )
                                    results.append(('testing', adapter, committed_at))
                        break  # first matching pattern wins
                else:
                    content = self._git_show(commit_sha, pattern)
                    if content:
                        run = self._parse_junit_xml_content(
                            content, commit_sha, pattern
                        )
                        if run:
                            adapter = JUnitXMLAdapter(
                                runs=[run],
                                source_id=f"junit_xml:{self.repo_path}"
                            )
                            results.append(('testing', adapter, committed_at))
                        break  # first matching pattern wins

        # Coverage (no glob patterns — all exact filenames)
        if 'coverage' in self.target_families:
            for pattern in self.extraction_patterns['coverage']:
                content = self._git_show(commit_sha, pattern)
                if content:
                    report = self._parse_cobertura_xml_content(
                        content, commit_sha
                    )
                    if report:
                        adapter = CoberturaAdapter(
                            reports=[report],
                            source_id=f"coverage_xml:{self.repo_path}"
                        )
                        results.append(('coverage', adapter, committed_at))
                    break  # first matching pattern wins

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
