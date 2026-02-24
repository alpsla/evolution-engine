"""
Adapter Registry — Auto-detect adapters from repo files + optional tokens.

Three tiers of detection:
  Tier 1: File-based (zero config, works fully offline)
  Tier 2: API-enriched (optional token unlocks CI, deployment, security data)
  Tier 3: Plugin adapters (installed via pip, auto-discovered at runtime)

Plugin system:
  Third-party packages register adapters via Python entry_points.
  Users install: `pip install evo-adapter-jenkins`
  The registry discovers them automatically at runtime.

  Entry point group: "evo.adapters"
  Each entry point must point to a callable that returns a list of dicts:
    [
        {
            "pattern": "Jenkinsfile",       # file pattern to detect (Tier 1)
            "adapter_name": "jenkins",
            "family": "ci",
            "adapter_class": "evo_jenkins.JenkinsAdapter",
        },
        {
            "token_key": "jenkins_url",     # token-based detection (Tier 2)
            "adapter_name": "jenkins_api",
            "family": "ci",
            "adapter_class": "evo_jenkins.JenkinsAPIAdapter",
        },
    ]

Usage:
    registry = AdapterRegistry(repo_path)
    adapters = registry.detect(tokens={"github_token": "ghp_..."})
    for config in adapters:
        print(f"{config.family}: {config.adapter_name} (tier {config.tier})")
"""

import json
import logging
import os
from dataclasses import dataclass, field
from glob import glob
from importlib.metadata import entry_points
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AdapterConfig:
    """Describes a detected adapter and how to instantiate it."""
    family: str           # e.g. "version_control", "dependency", "ci"
    adapter_name: str     # e.g. "git", "pip", "npm", "github_actions"
    tier: int             # 1 = file-based, 2 = API-enriched, 3 = plugin
    source_file: Optional[str] = None  # file that triggered detection
    token_key: Optional[str] = None    # env var / key needed (Tier 2)
    adapter_class: Optional[str] = None  # dotted path to adapter class (plugins)
    plugin_name: Optional[str] = None  # pip package that provided this adapter
    trust_level: str = ""  # "built-in", "verified", "community", "local"
    extras: dict = field(default_factory=dict)


# ─────────────────── Tier 1: File-based Detectors ───────────────────

# (glob_pattern, adapter_name, family)
TIER1_DETECTORS: list[tuple[str, str, str]] = [
    # Version control
    (".git/",               "git",      "version_control"),

    # Dependency — lockfiles/manifests (parsed by GitHistoryWalker)
    ("requirements.txt",    "pip",      "dependency"),
    ("pyproject.toml",      "pip",      "dependency"),
    ("setup.py",            "pip",      "dependency"),
    ("Pipfile.lock",        "pip",      "dependency"),
    ("package-lock.json",   "npm",      "dependency"),
    ("yarn.lock",           "npm",      "dependency"),
    ("pnpm-lock.yaml",     "npm",      "dependency"),
    ("go.mod",              "go",       "dependency"),
    ("go.sum",              "go",       "dependency"),
    ("Cargo.lock",          "cargo",    "dependency"),
    ("Cargo.toml",          "cargo",    "dependency"),
    ("Gemfile.lock",        "bundler",  "dependency"),
    ("Gemfile",             "bundler",  "dependency"),
    ("composer.lock",       "composer", "dependency"),

    # Schema
    ("openapi.yaml",        "openapi",  "schema"),
    ("openapi.yml",         "openapi",  "schema"),
    ("openapi.json",        "openapi",  "schema"),
    ("swagger.yaml",        "openapi",  "schema"),
    ("swagger.yml",         "openapi",  "schema"),
    ("swagger.json",        "openapi",  "schema"),

    # Config / IaC
    ("*.tf",                "terraform",    "config"),
    ("terraform.tfstate",   "terraform",    "config"),
    ("Dockerfile",          "docker",       "config"),
    ("docker-compose.yml",  "docker",       "config"),
    ("docker-compose.yaml", "docker",       "config"),

    # CI (local workflow files — no API needed)
    (".github/workflows/*.yml",   "github_actions_local", "ci"),
    (".github/workflows/*.yaml",  "github_actions_local", "ci"),
    (".gitlab-ci.yml",            "gitlab_ci_local",      "ci"),
    ("Jenkinsfile",               "jenkins_local",        "ci"),
    (".circleci/config.yml",      "circleci_local",       "ci"),

    # Testing — committed test reports (JUnit XML)
    ("junit.xml",                 "junit_xml",    "testing"),
    ("test-results.xml",          "junit_xml",    "testing"),
    ("surefire-reports/",         "junit_xml",    "testing"),
    ("TEST-*.xml",                "junit_xml",    "testing"),

    # Coverage — committed coverage reports (Cobertura XML)
    ("coverage.xml",              "coverage_xml", "coverage"),
    ("coverage/cobertura.xml",    "coverage_xml", "coverage"),
    ("coverage/coverage.xml",     "coverage_xml", "coverage"),
]

# ─────────────────── Tier 2: API-enriched Detectors ───────────────────

# token_key -> list of (adapter_name, family) unlocked by that token
TIER2_DETECTORS: dict[str, list[tuple[str, str]]] = {
    "github_token": [
        ("github_actions",   "ci"),
        ("github_releases",  "deployment"),
        ("github_security",  "security"),
    ],
    "gitlab_token": [
        ("gitlab_pipelines", "ci"),
        ("gitlab_releases",  "deployment"),
    ],
    "circleci_token": [
        ("circleci",         "ci"),
    ],
    "sentry_token": [
        ("sentry",           "error_tracking"),
    ],
    "jenkins_url": [
        ("jenkins",          "ci"),
    ],
}


class AdapterRegistry:
    """Auto-detect adapters from repo files + optional tokens + plugins."""

    # Entry point group for plugin discovery
    PLUGIN_GROUP = "evo.adapters"

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()
        self._plugin_detectors = None  # lazy-loaded
        self._blocked_configs: list[AdapterConfig] = []
        self._blocklist: Optional[list[dict]] = None
        self._verified: Optional[set[str]] = None

    def detect(self, tokens: dict[str, str] = None) -> list[AdapterConfig]:
        """Detect all available adapters for the repo.

        Discovers adapters from three sources:
          1. Built-in Tier 1 detectors (file patterns)
          2. Built-in Tier 2 detectors (API tokens)
          3. Plugin adapters (installed pip packages with evo.adapters entry points)

        Assigns trust_level automatically and filters out blocked adapters.

        Args:
            tokens: Optional dict of token_key -> token_value.
                    Also checks environment variables (e.g. GITHUB_TOKEN).

        Returns:
            List of AdapterConfig, sorted by tier then family.
        """
        tokens = tokens or {}
        configs = []
        seen = set()  # (family, adapter_name) dedup
        self._blocked_configs = []

        blocklist = self._load_blocklist()
        blocked_names = {b["name"] for b in blocklist}

        # ── Tier 1: File-based detection ──
        for pattern, adapter_name, family in TIER1_DETECTORS:
            key = (family, adapter_name)
            if key in seen:
                continue

            if self._match_pattern(pattern):
                source_file = self._first_match(pattern) or pattern
                config = AdapterConfig(
                    family=family,
                    adapter_name=adapter_name,
                    tier=1,
                    source_file=str(source_file),
                    trust_level="built-in",
                )
                if adapter_name in blocked_names:
                    self._blocked_configs.append(config)
                else:
                    configs.append(config)
                seen.add(key)

        # ── Tier 2: API-enriched detection ──
        for token_key, adapters in TIER2_DETECTORS.items():
            # Check explicit tokens dict, then environment variables
            token_value = tokens.get(token_key) or os.environ.get(token_key.upper())
            if not token_value:
                continue

            for adapter_name, family in adapters:
                key = (family, adapter_name)
                if key in seen:
                    continue
                config = AdapterConfig(
                    family=family,
                    adapter_name=adapter_name,
                    tier=2,
                    token_key=token_key,
                    trust_level="built-in",
                )
                if adapter_name in blocked_names:
                    self._blocked_configs.append(config)
                else:
                    configs.append(config)
                seen.add(key)

        # ── Tier 3: Plugin detection ──
        verified_set = self._load_verified()

        for plugin in self._get_plugin_detectors():
            pname = plugin.get("adapter_name", "unknown")
            pfamily = plugin.get("family", "unknown")
            ppackage = plugin.get("_plugin_name", "")
            key = (pfamily, pname)
            if key in seen:
                continue

            trust = self._determine_trust_level(ppackage, verified_set)

            # Plugin with file pattern → check if file exists
            if "pattern" in plugin:
                source_file = None
                if self._match_pattern(plugin["pattern"]):
                    source_file = self._first_match(plugin["pattern"]) or plugin["pattern"]

                config = AdapterConfig(
                    family=pfamily,
                    adapter_name=pname,
                    tier=3,
                    source_file=str(source_file) if source_file else None,
                    adapter_class=plugin.get("adapter_class"),
                    plugin_name=ppackage,
                    trust_level=trust,
                )
                if pname in blocked_names or ppackage in blocked_names:
                    self._blocked_configs.append(config)
                else:
                    configs.append(config)
                seen.add(key)

            # Plugin with token → check if token available
            elif "token_key" in plugin:
                tkey = plugin["token_key"]
                tval = tokens.get(tkey) or os.environ.get(tkey.upper())
                if tval:
                    config = AdapterConfig(
                        family=pfamily,
                        adapter_name=pname,
                        tier=3,
                        token_key=tkey,
                        adapter_class=plugin.get("adapter_class"),
                        plugin_name=ppackage,
                        trust_level=trust,
                    )
                    if pname in blocked_names or ppackage in blocked_names:
                        self._blocked_configs.append(config)
                    else:
                        configs.append(config)
                    seen.add(key)

            # Plugin with no detection requirement → always include
            else:
                config = AdapterConfig(
                    family=pfamily,
                    adapter_name=pname,
                    tier=3,
                    adapter_class=plugin.get("adapter_class"),
                    plugin_name=ppackage,
                    trust_level=trust,
                )
                if pname in blocked_names or ppackage in blocked_names:
                    self._blocked_configs.append(config)
                else:
                    configs.append(config)
                seen.add(key)

        configs.sort(key=lambda c: (c.tier, c.family, c.adapter_name))
        return configs

    def explain_missing(self, tokens: dict[str, str] = None) -> list[str]:
        """Explain what additional data could be unlocked with tokens.

        Returns human-readable messages like:
          "Set GITHUB_TOKEN to unlock CI runs, releases, and security alerts"
        """
        tokens = tokens or {}
        messages = []

        for token_key, adapters in TIER2_DETECTORS.items():
            token_value = tokens.get(token_key) or os.environ.get(token_key.upper())
            if token_value:
                continue  # already provided

            families = sorted(set(family for _, family in adapters))
            env_var = token_key.upper()
            families_str = ", ".join(families)
            messages.append(
                f"Set {env_var} or pass --token {token_key}=<value> "
                f"to unlock: {families_str}"
            )

        # Also report plugin token requirements
        for plugin in self._get_plugin_detectors():
            if "token_key" not in plugin:
                continue
            tkey = plugin["token_key"]
            tval = tokens.get(tkey) or os.environ.get(tkey.upper())
            if tval:
                continue
            pkg = plugin.get("_plugin_name", "plugin")
            messages.append(
                f"Set {tkey.upper()} to unlock: {plugin.get('family', '?')} "
                f"(from {pkg})"
            )

        return messages

    def _get_plugin_detectors(self) -> list[dict]:
        """Discover plugin adapters from installed pip packages.

        Looks for packages with entry points in the "evo.adapters" group.
        Each entry point must be a callable that returns a list of dicts.
        """
        if self._plugin_detectors is not None:
            return self._plugin_detectors

        self._plugin_detectors = []

        try:
            eps = entry_points(group=self.PLUGIN_GROUP)
        except TypeError:
            # Fallback for Python 3.9
            all_eps = entry_points()
            eps = all_eps.get(self.PLUGIN_GROUP, [])

        for ep in eps:
            try:
                register_fn = ep.load()
                descriptors = register_fn()
                if not isinstance(descriptors, list):
                    logger.warning(
                        "Plugin %s: register() must return a list, got %s",
                        ep.name, type(descriptors).__name__,
                    )
                    continue

                for desc in descriptors:
                    if not isinstance(desc, dict):
                        continue
                    if "adapter_name" not in desc or "family" not in desc:
                        logger.warning(
                            "Plugin %s: descriptor missing adapter_name or family",
                            ep.name,
                        )
                        continue
                    desc["_plugin_name"] = ep.name
                    self._plugin_detectors.append(desc)

                logger.debug(
                    "Plugin %s: registered %d adapter(s)", ep.name, len(descriptors)
                )
            except Exception as e:
                logger.warning("Plugin %s failed to load: %s", ep.name, e)

        return self._plugin_detectors

    def list_plugins(self) -> list[dict]:
        """List all installed plugin adapters and their status.

        Returns:
            List of dicts with plugin_name, adapter_name, family, detected (bool).
        """
        detected_keys = {
            (c.family, c.adapter_name) for c in self.detect()
        }
        results = []
        for plugin in self._get_plugin_detectors():
            key = (plugin.get("family"), plugin.get("adapter_name"))
            results.append({
                "plugin_name": plugin.get("_plugin_name"),
                "adapter_name": plugin.get("adapter_name"),
                "family": plugin.get("family"),
                "adapter_class": plugin.get("adapter_class"),
                "detected": key in detected_keys,
            })
        return results

    def _match_pattern(self, pattern: str) -> bool:
        """Check if a pattern matches any files in the repo."""
        # Directory check
        if pattern.endswith("/"):
            return (self.repo_path / pattern.rstrip("/")).is_dir()

        # Glob pattern
        if "*" in pattern:
            matches = glob(str(self.repo_path / pattern))
            return len(matches) > 0

        # Exact file
        return (self.repo_path / pattern).exists()

    def _first_match(self, pattern: str) -> Optional[str]:
        """Return the first matching file path for a pattern."""
        if pattern.endswith("/"):
            return pattern.rstrip("/")

        if "*" in pattern:
            matches = glob(str(self.repo_path / pattern))
            if matches:
                return str(Path(matches[0]).relative_to(self.repo_path))
            return None

        if (self.repo_path / pattern).exists():
            return pattern
        return None

    def _load_blocklist(self) -> list[dict]:
        """Load and merge bundled + local blocklists."""
        if self._blocklist is not None:
            return self._blocklist

        entries: list[dict] = []

        # Bundled blocklist (ships with package)
        bundled = Path(__file__).parent / "data" / "adapter_blocklist.json"
        if bundled.exists():
            try:
                data = json.loads(bundled.read_text())
                if isinstance(data, list):
                    entries.extend(data)
            except (json.JSONDecodeError, OSError):
                pass

        # Local user blocklist
        local = Path.home() / ".evo" / "blocklist.json"
        if local.exists():
            try:
                data = json.loads(local.read_text())
                if isinstance(data, list):
                    entries.extend(data)
            except (json.JSONDecodeError, OSError):
                pass

        self._blocklist = entries
        return entries

    def _load_verified(self) -> set[str]:
        """Load the verified adapters list."""
        if self._verified is not None:
            return self._verified

        verified_path = Path(__file__).parent / "data" / "verified_adapters.json"
        try:
            data = json.loads(verified_path.read_text())
            self._verified = set(data) if isinstance(data, list) else set()
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            self._verified = set()

        return self._verified

    def _determine_trust_level(self, plugin_name: str, verified_set: set[str]) -> str:
        """Determine trust level for a Tier 3 plugin adapter."""
        if not plugin_name:
            return "local"

        if plugin_name in verified_set:
            return "verified"

        # Check if the package has PyPI version metadata
        try:
            import importlib.metadata
            importlib.metadata.version(plugin_name)
            return "community"
        except Exception:
            return "local"

    def get_blocked(self) -> list[dict]:
        """Return blocked adapter configs with reasons.

        Returns:
            List of dicts with adapter info and block reason.
        """
        blocklist = self._load_blocklist()
        reason_map = {b["name"]: b.get("reason", "") for b in blocklist}

        results = []
        for config in self._blocked_configs:
            name = config.plugin_name or config.adapter_name
            results.append({
                "family": config.family,
                "adapter_name": config.adapter_name,
                "plugin_name": config.plugin_name,
                "reason": reason_map.get(name, reason_map.get(config.adapter_name, "")),
            })
        return results

    @staticmethod
    def block_adapter(name: str, reason: str = ""):
        """Add an adapter to the local blocklist."""
        blocklist_path = Path.home() / ".evo" / "blocklist.json"
        blocklist_path.parent.mkdir(parents=True, exist_ok=True)

        entries: list[dict] = []
        if blocklist_path.exists():
            try:
                entries = json.loads(blocklist_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        # Check if already blocked
        if any(e.get("name") == name for e in entries):
            return False

        entries.append({"name": name, "reason": reason})
        blocklist_path.write_text(json.dumps(entries, indent=2))
        return True

    @staticmethod
    def unblock_adapter(name: str) -> bool:
        """Remove an adapter from the local blocklist."""
        blocklist_path = Path.home() / ".evo" / "blocklist.json"
        if not blocklist_path.exists():
            return False

        try:
            entries = json.loads(blocklist_path.read_text())
        except (json.JSONDecodeError, OSError):
            return False

        original_len = len(entries)
        entries = [e for e in entries if e.get("name") != name]

        if len(entries) == original_len:
            return False

        blocklist_path.write_text(json.dumps(entries, indent=2))
        return True

    def summary(self, tokens: dict[str, str] = None) -> dict:
        """Return a structured summary of detection results."""
        configs = self.detect(tokens)
        missing = self.explain_missing(tokens)
        plugins = self.list_plugins()

        families = {}
        for c in configs:
            if c.family not in families:
                families[c.family] = []
            families[c.family].append({
                "adapter": c.adapter_name,
                "tier": c.tier,
                "source": c.source_file,
                "plugin": c.plugin_name,
                "trust_level": c.trust_level,
            })

        return {
            "repo_path": str(self.repo_path),
            "adapters_detected": len(configs),
            "families": families,
            "tier1_count": sum(1 for c in configs if c.tier == 1),
            "tier2_count": sum(1 for c in configs if c.tier == 2),
            "plugin_count": sum(1 for c in configs if c.tier == 3),
            "plugins_installed": len(plugins),
            "missing_tokens": missing,
            "blocked": self.get_blocked(),
        }

