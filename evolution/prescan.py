"""
Source Prescan — Detect external tools from repo artifacts.

Scans three layers to find tools the team already uses:
  1. Config files (glob for known filenames)
  2. SDK packages (search lockfile contents for known package names)
  3. Import statements (grep source files for known import patterns)

The prescan runs automatically during `evo analyze` and via `evo sources`.
It reads only filenames and dependency lists — never executes code or sends data.

Usage:
    prescan = SourcePrescan("/path/to/repo")
    detected = prescan.scan()
    for svc in detected:
        print(f"{svc.display_name} ({svc.family}) — {svc.evidence}")
"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DetectedService:
    """A tool/service detected in the repository."""
    service: str              # key in fingerprints DB (e.g. "datadog")
    display_name: str         # human name (e.g. "Datadog")
    family: str               # signal family (e.g. "monitoring")
    adapter: str              # pip package (e.g. "evo-adapter-datadog")
    detection_layers: list[str] = field(default_factory=list)  # ["config", "package", "import"]
    evidence: list[str] = field(default_factory=list)          # human-readable evidence


# Lockfile names → how to search for package names in them
LOCKFILES = {
    "package-lock.json": "json_key",
    "yarn.lock": "text_line",
    "pnpm-lock.yaml": "text_line",
    "requirements.txt": "text_line",
    "Pipfile.lock": "json_key",
    "go.sum": "text_line",
    "go.mod": "text_line",
    "Cargo.lock": "text_field",
    "Gemfile.lock": "text_line",
    "composer.lock": "json_key",
}

# Source file extensions to search for import patterns
SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".java", ".rb", ".rs",
}

# Directories to skip during import scanning
SKIP_DIRS = {
    "node_modules", "vendor", "venv", ".venv", "__pycache__",
    ".git", ".evo", "dist", "build", ".tox", ".mypy_cache",
    "target", "pkg", "bin", "obj",
}


class SourcePrescan:
    """Detect external tools by scanning repo artifacts.

    Args:
        repo_path: Path to the git repository root.
        max_import_files: Max source files to scan for imports (speed limit).
    """

    def __init__(self, repo_path: str | Path, max_import_files: int = 500):
        self.repo_path = Path(repo_path).resolve()
        self.max_import_files = max_import_files
        self._fingerprints = self._load_fingerprints()

    def scan(self) -> list[DetectedService]:
        """Run all three detection layers.

        Returns:
            List of DetectedService, sorted by family then service name.
        """
        detected: dict[str, DetectedService] = {}

        self._scan_configs(detected)
        self._scan_packages(detected)
        self._scan_imports(detected)

        result = sorted(detected.values(), key=lambda s: (s.family, s.service))
        return result

    def what_if(
        self,
        current_families: list[str],
        additional_adapters: list[str] = None,
    ) -> dict:
        """Estimate the impact of connecting additional families.

        Args:
            current_families: Families already connected.
            additional_adapters: Service keys to hypothetically add (e.g. ["datadog", "pagerduty"]).
                If None, uses all detected services.

        Returns:
            Dict with current/proposed family counts, combination counts,
            and descriptions of new cross-family questions.
        """
        detected = self.scan()

        if additional_adapters is None:
            # Use all detected services
            new_families = {s.family for s in detected}
        else:
            new_families = set()
            for key in additional_adapters:
                fp = self._fingerprints.get(key)
                if fp:
                    new_families.add(fp["family"])

        current_set = set(current_families)
        proposed_set = current_set | new_families
        added_families = proposed_set - current_set

        def combos(n):
            return n * (n - 1) // 2

        current_combos = combos(len(current_set))
        proposed_combos = combos(len(proposed_set))

        # Generate descriptions of new cross-family questions
        questions = []
        family_labels = {
            "monitoring": "monitoring",
            "error_tracking": "error tracking",
            "incidents": "incidents",
            "security_scan": "security scanning",
            "quality_gate": "code quality",
            "code_review": "code review",
            "work_items": "work items",
            "feature_flags": "feature flags",
            "version_control": "git",
            "dependency": "dependencies",
            "ci": "CI pipeline",
            "deployment": "deployments",
        }

        question_templates = {
            ("version_control", "monitoring"): "Do large commits correlate with error rate spikes?",
            ("version_control", "incidents"): "Do scattered commits correlate with more incidents?",
            ("version_control", "error_tracking"): "Do novel file combinations trigger more errors?",
            ("version_control", "security_scan"): "Do high-dispersion commits introduce vulnerabilities?",
            ("version_control", "quality_gate"): "Do commits with low locality have more code smells?",
            ("version_control", "code_review"): "Do AI-generated commits get more review findings?",
            ("version_control", "work_items"): "Do rework items have higher co-change novelty?",
            ("version_control", "feature_flags"): "Do feature flag changes correlate with deployment risk?",
            ("dependency", "monitoring"): "Do dependency updates affect error rates or latency?",
            ("dependency", "incidents"): "Do dependency updates correlate with incident spikes?",
            ("dependency", "security_scan"): "Do dependency-heavy commits introduce more vulnerabilities?",
            ("dependency", "quality_gate"): "Do dependency changes affect code quality metrics?",
            ("ci", "monitoring"): "Do CI failures predict production monitoring anomalies?",
            ("ci", "incidents"): "Do CI duration spikes precede incidents?",
            ("ci", "security_scan"): "Do CI-triggering commits have more security findings?",
            ("deployment", "monitoring"): "Do deployments with high dispersion cause error spikes?",
            ("deployment", "incidents"): "Do deployment pace changes correlate with incidents?",
            ("deployment", "security_scan"): "Do rapid releases introduce more vulnerabilities?",
            ("incidents", "monitoring"): "Do monitoring anomalies precede incidents?",
            ("monitoring", "error_tracking"): "Do error spikes correlate with monitoring anomalies?",
            ("quality_gate", "security_scan"): "Do quality gate failures predict security issues?",
            ("code_review", "quality_gate"): "Do review findings correlate with quality metrics?",
        }

        for f1 in proposed_set:
            for f2 in proposed_set:
                if f1 >= f2:
                    continue
                # Only include pairs where at least one is newly added
                if f1 not in added_families and f2 not in added_families:
                    continue
                pair = (f1, f2) if f1 < f2 else (f2, f1)
                label1 = family_labels.get(f1, f1)
                label2 = family_labels.get(f2, f2)
                question = question_templates.get(pair)
                if not question:
                    question = f"How do {label1} signals correlate with {label2} signals?"
                questions.append({
                    "families": [f1, f2],
                    "question": question,
                })

        return {
            "current_families": sorted(current_set),
            "current_combinations": current_combos,
            "proposed_families": sorted(proposed_set),
            "proposed_combinations": proposed_combos,
            "added_families": sorted(added_families),
            "multiplier": (
                f"{proposed_combos}x" if current_combos == 0
                else f"{proposed_combos / current_combos:.0f}x"
                if current_combos > 0 else "∞"
            ),
            "new_questions": questions,
        }

    # ─────────────────── Layer 1: Config Files ───────────────────

    def _scan_configs(self, detected: dict[str, DetectedService]):
        """Check for known config files in the repo root."""
        for service_key, fp in self._fingerprints.items():
            for config_path in fp.get("detect_configs", []):
                full_path = self.repo_path / config_path
                if full_path.exists():
                    svc = self._get_or_create(detected, service_key, fp)
                    if "config" not in svc.detection_layers:
                        svc.detection_layers.append("config")
                    svc.evidence.append(f"{config_path} found")

    # ─────────────────── Layer 2: SDK Packages ───────────────────

    def _scan_packages(self, detected: dict[str, DetectedService]):
        """Search lockfile contents for known SDK package names."""
        for lockfile_name, search_mode in LOCKFILES.items():
            lockfile_path = self.repo_path / lockfile_name
            if not lockfile_path.exists():
                continue

            try:
                content = lockfile_path.read_text(errors="replace")
            except OSError:
                continue

            if not content:
                continue

            for service_key, fp in self._fingerprints.items():
                for pkg in fp.get("detect_packages", []):
                    if self._package_in_lockfile(pkg, content, search_mode):
                        svc = self._get_or_create(detected, service_key, fp)
                        if "package" not in svc.detection_layers:
                            svc.detection_layers.append("package")
                        evidence = f"'{pkg}' in {lockfile_name}"
                        if evidence not in svc.evidence:
                            svc.evidence.append(evidence)

    @staticmethod
    def _package_in_lockfile(pkg: str, content: str, mode: str) -> bool:
        """Check if a package name appears in lockfile content.

        Package names are specific enough (dd-trace, @sentry/node, sentry-sdk)
        that a bounded substring search in structured lockfile content is reliable.
        """
        escaped = re.escape(pkg)
        if mode == "json_key":
            # JSON lockfiles: package appears in key paths like
            # "node_modules/dd-trace" or "dd-trace": or "@sentry/node":
            # Match package name bounded by non-alphanumeric (except @/-/_)
            return bool(re.search(
                rf'(?:^|[/"\':\s,])' + escaped + rf'(?:[/"\':\s,\]\}}]|$)',
                content, re.MULTILINE,
            ))
        elif mode == "text_field":
            # TOML-style (Cargo.lock): name = "package"
            return f'"{pkg}"' in content
        else:
            # Text lockfiles (requirements.txt, go.sum, yarn.lock, etc.)
            # Package at start of line or after separator, followed by
            # version spec (==, >=, @, space, etc.) or end of line
            return bool(re.search(
                rf'(?:^|[\s"\'/@])' + escaped + rf'(?:[\s"\'/@:,=\[\]><~!;]|$)',
                content, re.MULTILINE,
            ))

    # ─────────────────── Layer 3: Import Statements ───────────────────

    def _scan_imports(self, detected: dict[str, DetectedService]):
        """Grep source files for known import patterns."""
        # Collect all import patterns we're looking for
        patterns_by_service: dict[str, list[tuple[str, re.Pattern]]] = {}
        for service_key, fp in self._fingerprints.items():
            for imp in fp.get("detect_imports", []):
                if not imp:
                    continue
                # Build regex: match the import string in common import statements
                escaped = re.escape(imp)
                # Python: import X / from X
                # JS/TS: require("X") / import ... from "X" / import "X"
                # Go: "X"
                pattern = re.compile(
                    rf'''(?:import\s+|from\s+|require\s*\(\s*['"]|['"])'''
                    + escaped,
                    re.MULTILINE,
                )
                if service_key not in patterns_by_service:
                    patterns_by_service[service_key] = []
                patterns_by_service[service_key].append((imp, pattern))

        if not patterns_by_service:
            return

        # Walk source files (bounded)
        files_scanned = 0
        for dirpath, dirnames, filenames in os.walk(self.repo_path):
            # Prune skip directories
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for fname in filenames:
                if files_scanned >= self.max_import_files:
                    return

                ext = os.path.splitext(fname)[1]
                if ext not in SOURCE_EXTENSIONS:
                    continue

                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, "r", errors="replace") as f:
                        content = f.read(64_000)  # first 64KB is enough
                except OSError:
                    continue

                files_scanned += 1

                for service_key, patterns in patterns_by_service.items():
                    for imp_str, pattern in patterns:
                        if pattern.search(content):
                            fp = self._fingerprints[service_key]
                            svc = self._get_or_create(detected, service_key, fp)
                            if "import" not in svc.detection_layers:
                                svc.detection_layers.append("import")
                            relpath = os.path.relpath(fpath, self.repo_path)
                            evidence = f"'{imp_str}' imported in {relpath}"
                            if evidence not in svc.evidence:
                                svc.evidence.append(evidence)
                            break  # one match per service per file is enough

    # ─────────────────── Helpers ───────────────────

    @staticmethod
    def _get_or_create(
        detected: dict[str, DetectedService],
        service_key: str,
        fp: dict,
    ) -> DetectedService:
        """Get or create a DetectedService entry."""
        if service_key not in detected:
            detected[service_key] = DetectedService(
                service=service_key,
                display_name=fp.get("display_name", service_key),
                family=fp["family"],
                adapter=fp.get("adapter", f"evo-adapter-{service_key}"),
            )
        return detected[service_key]

    def _load_fingerprints(self) -> dict:
        """Load SDK fingerprint database."""
        data_dir = Path(__file__).parent / "data"
        fp_path = data_dir / "sdk_fingerprints.json"
        if not fp_path.exists():
            return {}
        data = json.loads(fp_path.read_text())
        # Strip metadata keys
        return {k: v for k, v in data.items() if not k.startswith("_")}
