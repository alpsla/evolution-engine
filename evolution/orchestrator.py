"""
Pipeline Orchestrator — Core flow for `evo analyze`.

Extracted from examples/calibrate_repo.py into an importable module.
Detect → Ingest → Phase 2 → 3 → 4 → 5.

Usage:
    from evolution.orchestrator import Orchestrator
    orch = Orchestrator(repo_path=".", evo_dir=".evo")
    result = orch.run()
"""

import inspect
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

from evolution.license import get_license
from evolution.registry import TIER2_DETECTORS, AdapterRegistry

logger = logging.getLogger(__name__)


class Orchestrator:
    """Run the full 5-phase pipeline on a repository.

    Args:
        repo_path: Path to the git repository.
        evo_dir: Directory for pipeline output (default: <repo_path>/.evo).
        tokens: Optional dict of token_key -> token_value for Tier 2 adapters.
        enable_llm: Enable LLM-enhanced explanations and patterns (default False).
        families: Override auto-detected families (default: auto-detect all).
    """

    def __init__(
        self,
        repo_path: str | Path,
        evo_dir: str | Path = None,
        tokens: dict[str, str] = None,
        enable_llm: bool = False,
        families: list[str] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.evo_dir = Path(evo_dir).resolve() if evo_dir else self.repo_path / ".evo"
        self.tokens = tokens or {}
        self.families_override = families

        # Check license
        self.license = get_license(str(self.repo_path))

        # Gate LLM features behind Pro tier (message deferred to "Next steps")
        if enable_llm and not self.license.is_pro():
            self.enable_llm = False
            self._llm_gated = True
        else:
            self.enable_llm = enable_llm
            self._llm_gated = False

        # Disable LLM by default
        if not self.enable_llm:
            os.environ.setdefault("PHASE31_ENABLED", "false")
            os.environ.setdefault("PHASE4B_ENABLED", "false")

        # Detect adapters
        self.registry = AdapterRegistry(self.repo_path)

    def run(
        self,
        scope: str = None,
        json_output: bool = False,
        quiet: bool = False,
        verbose: bool = False,
    ) -> dict:
        """Execute the full pipeline.

        Args:
            scope: Scope identifier for the advisory (default: repo dir name).
            json_output: If True, return machine-readable dict only.
            quiet: If True, suppress stdout output.
            verbose: If True, show detailed phase-level output.

        Returns:
            Pipeline result dict with event/signal/pattern/advisory counts.
        """
        from evolution.phase1_engine import Phase1Engine
        from evolution.phase2_engine import Phase2Engine
        from evolution.phase3_engine import Phase3Engine
        from evolution.phase4_engine import Phase4Engine
        from evolution.phase5_engine import Phase5Engine

        scope = scope or self.repo_path.name
        start = time.monotonic()
        log = self._log if not quiet else lambda *a, **k: None
        vlog = log if verbose else lambda *a, **k: None

        # ── Snapshot previous advisory for loop closure ──
        previous_advisory = self._load_previous_advisory()

        # ── Clean previous run data for a fresh analysis ──
        self._clean_pipeline_data()

        # ── Detect adapters ──
        detected = self.registry.detect(self.tokens)
        vlog(f"Detected {len(detected)} adapters across "
             f"{len(set(c.family for c in detected))} families")

        for c in detected:
            vlog(f"  [{c.family}] {c.adapter_name} (tier {c.tier})")

        missing = self.registry.explain_missing(self.tokens)
        for msg in missing:
            vlog(f"  {msg}")

        # ── Phase 1: Ingest events ──
        phase1 = Phase1Engine(self.evo_dir)
        family_counts = {}
        families_detected = set(c.family for c in detected)

        # Apply override if specified
        if self.families_override:
            families_to_run = set(self.families_override)
        else:
            families_to_run = families_detected

        # Git commits (always first — other families may depend on commit SHAs)
        if "version_control" in families_to_run:
            vlog("\n[Phase 1] Ingesting git commits...")
            count = self._ingest_git(phase1)
            family_counts["version_control"] = count
            vlog(f"  git: {count} events")

        # File-based families via GitHistoryWalker
        walker_families = []
        if "dependency" in families_to_run:
            walker_families.append("dependency")
        if "schema" in families_to_run:
            walker_families.append("schema")
        if "config" in families_to_run:
            walker_families.append("config")

        if walker_families:
            vlog(f"\n[Phase 1] Walking git history for {', '.join(walker_families)}...")
            walker_counts = self._ingest_walker(phase1, walker_families)
            family_counts.update(walker_counts)
            for fam, count in walker_counts.items():
                vlog(f"  {fam}: {count} events")

        # API families (concurrent) — gated by Pro license
        api_families = []
        _gated_families = []
        if not self.license.is_pro() and any(
            f in families_to_run for f in ["ci", "deployment", "security"]
        ):
            _gated_families = [f for f in ["ci", "deployment", "security"] if f in families_to_run]
        else:
            if "ci" in families_to_run and self._has_tier2("ci"):
                api_families.append("ci")
            if "deployment" in families_to_run and self._has_tier2("deployment"):
                api_families.append("deployment")
            if "security" in families_to_run and self._has_tier2("security"):
                api_families.append("security")

        if api_families:
            vlog(f"\n[Phase 1] Fetching API data for {', '.join(api_families)}...")
            api_counts = self._ingest_api(phase1, api_families)
            family_counts.update(api_counts)
            for fam, count in api_counts.items():
                vlog(f"  {fam}: {count} events")

        # ── Tier 3: Plugin adapters ──
        plugin_configs = [c for c in detected if c.tier == 3 and c.adapter_class]
        if plugin_configs:
            vlog(f"\n[Phase 1] Ingesting from {len(plugin_configs)} plugin adapter(s)...")
            plugin_counts = self._ingest_plugins(phase1, plugin_configs, vlog)
            for f, c in plugin_counts.items():
                family_counts[f] = family_counts.get(f, 0) + c
                vlog(f"  {f}: {c} events (plugin)")

        total_events = sum(family_counts.values())
        active_families = [f for f, c in family_counts.items() if c > 0]

        # Simplified progress: show what was analyzed
        _family_labels = {
            "version_control": "Git history",
            "dependency": "Dependencies",
            "schema": "API schemas",
            "config": "Configuration",
            "ci": "CI/CD",
            "deployment": "Deployments",
            "security": "Security",
        }
        for fam in active_families:
            label = _family_labels.get(fam, fam)
            count = family_counts.get(fam, 0)
            log(f"  \u2713 {label} ({count} events)")

        vlog(f"\n  Total: {total_events} events across {len(active_families)} families")

        if total_events == 0:
            return {
                "status": "no_events",
                "message": "No events ingested. Check that the repo has git history.",
                "elapsed_seconds": round(time.monotonic() - start, 1),
            }

        # ── Phase 2: Baselines & Signals ──
        vlog("\n[Phase 2] Computing baselines...")
        t0 = time.monotonic()
        phase2 = Phase2Engine(self.evo_dir, window_size=50, min_baseline=5)
        signals = phase2.run_all_parallel()
        signal_counts = {f: len(s) for f, s in signals.items() if s}
        total_signals = sum(signal_counts.values())
        vlog(f"  {total_signals} signals ({time.monotonic() - t0:.1f}s)")

        # ── Phase 3: Explanations ──
        vlog("\n[Phase 3] Generating explanations...")
        t0 = time.monotonic()
        phase3 = Phase3Engine(self.evo_dir)
        explanations = phase3.run()
        vlog(f"  {len(explanations)} explanations ({time.monotonic() - t0:.1f}s)")

        # ── Phase 4: Pattern Discovery ──
        vlog("\n[Phase 4] Discovering patterns...")
        t0 = time.monotonic()
        phase4 = Phase4Engine(self.evo_dir)

        # Auto-pull community patterns if enabled (before discovery)
        self._auto_pull_community_patterns(vlog)

        # Fetch patterns from registry handler (immediate availability)
        registry_imported = self._import_registry_patterns(active_families, vlog)
        if registry_imported:
            vlog(f"  Imported {registry_imported} pattern(s) from community registry")

        # Auto-fetch and import patterns from PyPI pattern packages (durable backup)
        pkg_imported = self._import_pattern_packages(active_families, vlog)
        if pkg_imported:
            vlog(f"  Imported {pkg_imported} pattern(s) from community packages")

        p4_result = phase4.run()
        phase4.close()
        vlog(f"  {p4_result.get('patterns_discovered', 0)} discovered, "
             f"{p4_result.get('knowledge_artifacts', 0)} knowledge "
             f"({time.monotonic() - t0:.1f}s)")

        # ── Phase 5: Advisory ──
        vlog("\n[Phase 5] Generating advisory...")
        t0 = time.monotonic()
        phase5 = Phase5Engine(self.evo_dir)
        p5_result = phase5.run(scope=scope)
        vlog(f"  Status: {p5_result['status']} ({time.monotonic() - t0:.1f}s)")

        # ── Auto-snapshot advisory for run history ──
        if p5_result["status"] == "complete" and p5_result.get("advisory"):
            try:
                from evolution.history import HistoryManager
                hm = HistoryManager(self.evo_dir)
                hm.snapshot(p5_result["advisory"], scope)
            except Exception:
                pass  # History should never block the pipeline

        # ── Loop closure: compare with previous advisory ──
        resolution = self._compute_resolution(previous_advisory, p5_result)

        elapsed = round(time.monotonic() - start, 1)

        result = {
            "status": "complete",
            "scope": scope,
            "repo_path": str(self.repo_path),
            "evo_dir": str(self.evo_dir),
            "events": total_events,
            "families": active_families,
            "family_counts": family_counts,
            "signals": total_signals,
            "signal_counts": signal_counts,
            "explanations": len(explanations),
            "phase4": {
                "patterns_discovered": p4_result.get("patterns_discovered", 0),
                "patterns_recognized": p4_result.get("patterns_recognized", 0),
                "knowledge_artifacts": p4_result.get("knowledge_artifacts", 0),
            },
            "advisory_status": p5_result["status"],
            "elapsed_seconds": elapsed,
        }

        # Count patterns eligible for community sharing
        result["shareable_patterns"] = self._count_shareable_patterns()

        if resolution:
            result["resolution"] = resolution

        if p5_result["status"] == "complete":
            advisory = p5_result["advisory"]
            result["advisory"] = {
                "significant_changes": advisory["summary"]["significant_changes"],
                "families_affected": advisory["summary"]["families_affected"],
                "patterns_matched": advisory["summary"]["known_patterns_matched"],
                "status": advisory.get("status", {}),
            }
            result["formats"] = p5_result.get("formats", {})

            if not json_output:
                log(f"\n{p5_result.get('human_summary', '')}")

        # ── Next steps (consolidated hints) ──
        if not json_output:
            next_steps = []
            if self._llm_gated:
                next_steps.append(
                    "AI investigation available with Pro. "
                    "Run `evo setup .` to configure, or visit https://codequal.dev/pro"
                )
            if _gated_families:
                n = len(_gated_families)
                next_steps.append(
                    f"Run `evo setup .` to unlock {n} more signal "
                    f"{'family' if n == 1 else 'families'} ({', '.join(_gated_families)})"
                )
            self._prescan_hint_collect(next_steps, active_families)

            if next_steps:
                log("\nNext steps:")
                for step in next_steps:
                    log(f"  \u2192 {step}")

        log(f"\nDone in {elapsed}s")
        return result

    # ─────────────────── Shareable Pattern Count ───────────────────

    def _count_shareable_patterns(self) -> int:
        """Count local patterns eligible for community sharing.

        A pattern is shareable if it has |correlation_strength| >= 0.3
        and occurrence_count >= 3. This matches the quality gate in
        kb_export.export_patterns().
        """
        db_path = self.evo_dir / "phase4" / "knowledge.db"
        if not db_path.exists():
            return 0
        try:
            from evolution.knowledge_store import SQLiteKnowledgeStore
            kb = SQLiteKnowledgeStore(db_path)
            count = 0
            for p in kb.list_patterns(scope="local", min_occurrences=3):
                corr = p.get("correlation_strength")
                if corr is not None and abs(corr) >= 0.3:
                    count += 1
            for ka in kb.list_knowledge(scope="local"):
                corr = ka.get("correlation_strength")
                if corr is not None and abs(corr) >= 0.3:
                    count += 1
            kb.close()
            return count
        except Exception:
            return 0

    # ─────────────────── Prescan Hint ───────────────────

    def _prescan_hint(self, log, active_families: list[str]):
        """Show a non-intrusive hint if prescan detects additional tools."""
        try:
            from evolution.prescan import SourcePrescan

            prescan = SourcePrescan(self.repo_path)
            detected = prescan.scan()
            connected_set = set(active_families)
            unconnected = [s for s in detected if s.family not in connected_set]

            if unconnected:
                names = ", ".join(s.display_name for s in unconnected[:3])
                extra = f" (+{len(unconnected) - 3} more)" if len(unconnected) > 3 else ""
                log(f"\nDetected in repo: {names}{extra}")
                log("  Run `evo sources` to see what connecting them would add.")
        except Exception:
            pass  # prescan is advisory, never block the pipeline

    def _prescan_hint_collect(self, hints: list[str], active_families: list[str]):
        """Collect prescan hints into a list instead of printing."""
        try:
            from evolution.prescan import SourcePrescan

            prescan = SourcePrescan(self.repo_path)
            detected = prescan.scan()
            connected_set = set(active_families)
            unconnected = [s for s in detected if s.family not in connected_set]

            if unconnected:
                names = ", ".join(s.display_name for s in unconnected[:3])
                extra = f" (+{len(unconnected) - 3} more)" if len(unconnected) > 3 else ""
                hints.append(f"Detected {names}{extra} — run `evo sources` for details")
        except Exception:
            pass

    # ─────────────────── Community Pattern Auto-Pull ───────────────────

    def _auto_pull_community_patterns(self, log):
        """Pull community patterns from registry if sync.auto_pull is enabled.

        Respects the 24h cache in sync_state.json — won't hit the network
        more than once per day. Non-blocking: failures are logged and ignored.
        """
        try:
            from evolution.config import EvoConfig
            cfg = EvoConfig()
            if not cfg.get("sync.auto_pull"):
                return

            # Check if we pulled recently (24h throttle)
            sync_state_path = self.evo_dir / "sync_state.json"
            if sync_state_path.exists():
                import json as _json
                state = _json.loads(sync_state_path.read_text())
                last_pull = state.get("last_pull_at")
                if last_pull:
                    from datetime import datetime, timezone
                    try:
                        last_dt = datetime.fromisoformat(last_pull)
                        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                        if elapsed < 86400:  # 24 hours
                            return
                    except (ValueError, TypeError):
                        pass

            from evolution.kb_sync import KBSync
            sync = KBSync(evo_dir=self.evo_dir, config=cfg)
            result = sync.pull()
            if result.success and result.pulled > 0:
                log(f"  Auto-pulled {result.pulled} community pattern(s)")
        except Exception as e:
            logger.debug("Auto-pull failed (non-fatal): %s", e)

    # ─────────────────── Pattern Package Import ───────────────────

    def _import_pattern_packages(self, detected_families: list[str], log) -> int:
        """Auto-fetch and import patterns from PyPI pattern packages.

        Downloads pattern data directly from wheels (no pip install),
        validates it, filters by locally-detected families, and imports.
        """
        try:
            from evolution.pattern_registry import fetch_available_patterns
            from evolution.kb_export import import_patterns

            patterns = fetch_available_patterns(detected_families)
            if not patterns:
                return 0

            db_path = self.evo_dir / "phase4" / "knowledge.db"
            if not db_path.exists():
                return 0

            # Downloaded from PyPI, validated by pattern_registry — skip quorum
            result = import_patterns(db_path, patterns, min_attestations=0)
            return result.get("imported", 0)
        except Exception as e:
            logger.debug("Pattern package import failed (non-fatal): %s", e)
            return 0

    # ─────────────────── Registry Direct Pull ───────────────────

    def _import_registry_patterns(self, detected_families: list[str], log) -> int:
        """Fetch patterns directly from the registry handler (Redis-backed).

        This provides immediate availability — patterns pushed by any user
        are available to all other users on their next `evo analyze`, without
        waiting for a PyPI snapshot.

        Non-blocking: failures are logged and ignored.
        """
        try:
            import urllib.request

            from evolution.config import EvoConfig
            from evolution.kb_export import import_patterns

            cfg = EvoConfig()
            registry_url = cfg.get("sync.registry_url", "https://codequal.dev/api")

            # Check 24h cache to avoid hitting the registry on every run
            cache_path = self.evo_dir / "registry_cache.json"
            now = time.time()
            if cache_path.exists():
                cache = json.loads(cache_path.read_text())
                if now - cache.get("last_fetched", 0) < 86400:
                    return 0

            url = f"{registry_url}/patterns"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))
            patterns = data.get("patterns", [])

            if not patterns:
                return 0

            # Filter by detected families (map legacy source names)
            _SOURCE_ALIASES = {"git": "version_control", "version_control": "git"}
            families_set = set(detected_families)
            for f in list(families_set):
                if f in _SOURCE_ALIASES:
                    families_set.add(_SOURCE_ALIASES[f])
            filtered = [
                p for p in patterns
                if any(s in families_set for s in p.get("sources", []))
            ]
            if not filtered:
                return 0

            db_path = self.evo_dir / "phase4" / "knowledge.db"
            if not db_path.exists():
                return 0

            # Registry patterns are pre-validated server-side — skip quorum
            result = import_patterns(db_path, filtered, min_attestations=0)
            imported = result.get("imported", 0)

            # Update cache timestamp
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({
                "last_fetched": now,
                "pattern_count": len(patterns),
                "imported": imported,
            }))

            return imported
        except Exception as e:
            logger.debug("Registry pattern import failed (non-fatal): %s", e)
            return 0

    # ─────────────────── Ingestion Helpers ───────────────────

    def _ingest_git(self, phase1) -> int:
        from evolution.adapters.git.git_adapter import GitSourceAdapter
        adapter = GitSourceAdapter(repo_path=str(self.repo_path))
        return phase1.ingest(adapter)

    def _ingest_walker(self, phase1, families: list[str]) -> dict[str, int]:
        from evolution.adapters.git.git_history_walker import GitHistoryWalker
        walker = GitHistoryWalker(
            repo_path=str(self.repo_path),
            target_families=families,
        )
        counts = {f: 0 for f in families}
        for commit, family, adapter, committed_at in walker.iter_commit_events():
            n = phase1.ingest(adapter, override_observed_at=committed_at)
            if n > 0:
                counts[family] += n
        return {f: c for f, c in counts.items() if c > 0}

    def _ingest_api(self, phase1, families: list[str]) -> dict[str, int]:
        """Fetch events from API adapters concurrently."""
        token = self.tokens.get("github_token") or os.environ.get("GITHUB_TOKEN")
        if not token:
            return {}

        from evolution.adapters.github_client import GitHubClient

        # Infer owner/repo from git remote
        owner, repo = self._infer_github_remote()
        if not owner or not repo:
            return {}

        client = GitHubClient(
            owner, repo, token,
            cache_dir=self.evo_dir / "api_cache",
        )

        adapters_to_fetch = {}
        if "ci" in families:
            from evolution.adapters.ci.github_actions_adapter import GitHubActionsAdapter
            adapters_to_fetch["ci"] = lambda c: GitHubActionsAdapter(client=c, max_runs=500)
        if "deployment" in families:
            from evolution.adapters.deployment.github_releases_adapter import GitHubReleasesAdapter
            adapters_to_fetch["deployment"] = lambda c: GitHubReleasesAdapter(client=c)
        if "security" in families:
            from evolution.adapters.security.github_security_adapter import GitHubSecurityAdapter
            adapters_to_fetch["security"] = lambda c: GitHubSecurityAdapter(client=c)

        counts = {}
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="api") as executor:
            futures = {}
            for name, factory in adapters_to_fetch.items():
                def _fetch(n=name, f=factory):
                    try:
                        adapter = f(client)
                        events = list(adapter.iter_events())
                        return n, events, None
                    except Exception as e:
                        return n, [], e
                futures[executor.submit(_fetch)] = name

            for future in as_completed(futures):
                name, events, error = future.result()
                if error:
                    continue
                if events:
                    class _ListAdapter:
                        def __init__(self, evts):
                            self._events = evts
                        def iter_events(self):
                            return iter(self._events)
                    count = phase1.ingest(_ListAdapter(events))
                    if count > 0:
                        counts[name] = count

        return counts

    def _ingest_plugins(self, phase1, plugin_configs: list, log) -> dict[str, int]:
        """Ingest events from Tier 3 plugin adapters.

        For each detected plugin, loads the adapter class, introspects
        its constructor to pass appropriate kwargs (path, token, etc.),
        and feeds events into Phase 1. Failures are logged but never
        block the pipeline.

        Returns:
            dict mapping family -> event count from plugins.
        """
        from evolution.adapter_validator import load_adapter_class

        counts: dict[str, int] = {}

        for config in plugin_configs:
            # Respect families_override
            if self.families_override and config.family not in self.families_override:
                continue

            try:
                cls = load_adapter_class(config.adapter_class)
            except (ImportError, AttributeError) as e:
                log(f"  [warn] Could not load {config.adapter_class}: {e}")
                continue

            # Introspect constructor to pass supported kwargs
            try:
                sig = inspect.signature(cls.__init__)
                params = set(sig.parameters.keys()) - {"self"}
            except (ValueError, TypeError):
                params = set()

            kwargs = {}
            if "path" in params or "repo_path" in params:
                key = "repo_path" if "repo_path" in params else "path"
                kwargs[key] = str(self.repo_path)
            if "token" in params:
                token = (
                    self.tokens.get(config.token_key)
                    or (os.environ.get(config.token_key.upper()) if config.token_key else None)
                )
                if token:
                    kwargs["token"] = token
            if "source_id" in params:
                kwargs["source_id"] = config.adapter_name

            try:
                adapter = cls(**kwargs)
                count = phase1.ingest(adapter)
                if count > 0:
                    counts[config.family] = counts.get(config.family, 0) + count
            except Exception as e:
                logger.warning("Plugin %s failed: %s", config.adapter_name, e)
                log(f"  [warn] Plugin {config.adapter_name} failed: {e}")

        return counts

    def _has_tier2(self, family: str) -> bool:
        """Check if a Tier 2 adapter is available for a family."""
        # Gate Tier 2 adapters behind Pro license
        if not self.license.is_pro():
            return False

        for token_key, adapters in TIER2_DETECTORS.items():
            for adapter_name, fam in adapters:
                if fam == family:
                    token = self.tokens.get(token_key) or os.environ.get(token_key.upper())
                    if token:
                        return True
        return False

    def _infer_github_remote(self) -> tuple[Optional[str], Optional[str]]:
        """Try to infer GitHub owner/repo from git remote URL."""
        try:
            import git
            repo = git.Repo(self.repo_path)
            for remote in repo.remotes:
                url = remote.url
                # SSH: git@github.com:owner/repo.git
                if "github.com:" in url:
                    parts = url.split("github.com:")[-1].rstrip(".git").split("/")
                    if len(parts) >= 2:
                        return parts[0], parts[1]
                # HTTPS: https://github.com/owner/repo.git
                if "github.com/" in url:
                    parts = url.split("github.com/")[-1].rstrip(".git").split("/")
                    if len(parts) >= 2:
                        return parts[0], parts[1]
        except Exception:
            pass
        return None, None

    def _load_previous_advisory(self) -> Optional[dict]:
        """Load the current advisory.json before it is cleaned, if it exists.

        This snapshot is used after the pipeline completes to compute
        resolution progress (loop closure for hooks).
        """
        advisory_path = self.evo_dir / "phase5" / "advisory.json"
        if not advisory_path.exists():
            return None
        try:
            return json.loads(advisory_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _compute_resolution(
        self,
        previous_advisory: Optional[dict],
        p5_result: dict,
    ) -> Optional[dict]:
        """Compare current advisory with previous to compute resolution progress.

        If a previous advisory exists and the current pipeline produced a
        complete advisory, returns a resolution dict:
            {resolved: N, persisting: N, new: N, regressions: N, total_before: N}

        Also saves the current advisory as advisory.json (already done by Phase 5)
        and auto-generates residual_prompt.txt when findings remain.

        Returns None if no previous advisory or current pipeline has no advisory.
        """
        if previous_advisory is None:
            return None
        if p5_result.get("status") != "complete" or not p5_result.get("advisory"):
            return None

        try:
            from evolution.fixer import compare_advisories

            current_advisory = p5_result["advisory"]
            diff = compare_advisories(current_advisory, previous_advisory)

            resolved_count = len(diff["resolved"])
            persisting_count = len(diff["persisting"])
            new_count = len(diff["new"])
            regression_count = len(diff["regressions"])
            total_before = len(previous_advisory.get("changes", []))

            resolution = {
                "resolved": resolved_count,
                "persisting": persisting_count,
                "new": new_count,
                "regressions": regression_count,
                "total_before": total_before,
            }

            # Auto-save residual_prompt.txt when findings remain
            remaining = persisting_count + new_count + regression_count
            if remaining > 0:
                self._save_residual_prompt(current_advisory, previous_advisory)

            return resolution
        except Exception as e:
            logger.debug("Resolution comparison failed (non-fatal): %s", e)
            return None

    def _save_residual_prompt(
        self,
        current_advisory: dict,
        previous_advisory: dict,
    ) -> None:
        """Auto-generate residual_prompt.txt for the 'Fix with AI' button.

        Uses the Fixer's _build_residual_prompt to create an iteration-aware
        prompt comparing current vs previous advisory findings.
        """
        try:
            from evolution.fixer import Fixer

            fixer = Fixer(repo_path=self.repo_path, evo_dir=self.evo_dir)

            # Load investigation text
            investigation_text = fixer._load_investigation() or "(no investigation report available)"

            prompt = fixer._build_residual_prompt(
                current_advisory, previous_advisory, investigation_text,
            )

            residual_path = self.evo_dir / "phase5" / "residual_prompt.txt"
            residual_path.parent.mkdir(parents=True, exist_ok=True)
            residual_path.write_text(prompt, encoding="utf-8")
        except Exception as e:
            logger.debug("Residual prompt generation failed (non-fatal): %s", e)

    def _clean_pipeline_data(self):
        """Clear previous pipeline outputs for a fresh analysis.

        Preserves: knowledge.db (accumulated patterns), api_cache (speeds
        up API re-fetches), history/ (run snapshots), report.html.
        """
        import shutil

        # Phase 1: events + dedup index
        for subdir in ["events", "index"]:
            p = self.evo_dir / subdir
            if p.exists():
                shutil.rmtree(p)

        # Phase 2, 3, 5: derived outputs
        for subdir in ["phase2", "phase3", "phase5"]:
            p = self.evo_dir / subdir
            if p.exists():
                shutil.rmtree(p)

        # Phase 4: clear summary but keep knowledge.db
        phase4_dir = self.evo_dir / "phase4"
        if phase4_dir.exists():
            for item in phase4_dir.iterdir():
                if item.name != "knowledge.db":
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

    @staticmethod
    def _log(msg: str):
        print(msg)
