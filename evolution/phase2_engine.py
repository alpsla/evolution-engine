"""
Phase 2 Engine — Behavioral Baselines & Deviation Signals

Multi-family implementation.
Uses MAD-based robust deviation (resistant to outliers, no Gaussian assumption).
Emits canonical Phase 2 signals for all source families:
- version_control (git): files_touched, dispersion, cochange_novelty_ratio, change_locality
- ci:                     run_duration, run_failed
- testing:                total_tests, failure_rate, skip_rate, suite_duration
- dependency:             dependency_count, max_depth (ecosystem-gated)
- schema:                 endpoint_count, type_count, field_count, schema_churn
- deployment:             release_cadence_hours, is_prerelease, asset_count
- config:                 resource_count, resource_type_count, config_churn
- security:               vulnerability_count, critical_count, fixable_ratio

Conforms to PHASE_2_CONTRACT.md and PHASE_2_DESIGN.md.
"""

from pathlib import Path
import json
from collections import defaultdict, deque
from statistics import mean, median, pstdev
import math


def _median_absolute_deviation(values: list) -> float:
    """MAD = median(|x_i - median(x)|)."""
    med = median(values)
    return median([abs(v - med) for v in values])


def _iqr(values: list) -> float:
    """Interquartile range — fallback when MAD=0."""
    s = sorted(values)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    return q3 - q1


def compute_robust_deviation(observed: float, values: list) -> dict:
    """Compute deviation using MAD (robust to outliers), IQR fallback.

    Returns dict with: measure, unit, median, mad, degenerate.
    """
    med = median(values)
    mad = _median_absolute_deviation(values)

    if mad > 0:
        # 0.6745 = normal distribution 75th percentile (consistency constant)
        measure = 0.6745 * (observed - med) / mad
        return {"measure": round(measure, 6), "unit": "modified_zscore",
                "median": med, "mad": mad, "degenerate": False}

    iqr_val = _iqr(values)
    if iqr_val > 0:
        measure = (observed - med) / (iqr_val / 1.35)
        return {"measure": round(measure, 6), "unit": "iqr_normalized",
                "median": med, "mad": 0.0, "degenerate": False}

    # Constant series — both MAD and IQR are 0
    if observed == med:
        return {"measure": 0.0, "unit": "degenerate",
                "median": med, "mad": 0.0, "degenerate": True}
    else:
        # Value changed from a constant baseline. Flag but don't fabricate sigma.
        return {"measure": None, "unit": "degenerate",
                "median": med, "mad": 0.0, "degenerate": True}


class Phase2Engine:
    def __init__(self, evo_dir: Path, window_size: int = 50, min_baseline: int = 5):
        self.evo_dir = evo_dir
        self.events_path = evo_dir / "events"
        self.output_path = evo_dir / "phase2"
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.window_size = window_size
        self.min_baseline = min_baseline

    def _load_events(self, source_family: str = None, source_type: str = None):
        """Load events, optionally filtered by family or type.

        Events are sorted chronologically by observed_at to ensure
        deterministic sliding-window baselines.
        """
        events = []
        for p in sorted(self.events_path.glob("*.json")):
            with open(p, "r", encoding="utf-8") as f:
                ev = json.load(f)
            if source_family and ev.get("source_family") != source_family:
                continue
            if source_type and ev.get("source_type") != source_type:
                continue
            events.append(ev)
        events.sort(key=lambda e: e.get("observed_at", ""))
        return events

    def _emit_signals(self, events, engine_id, source_type, metric_fn, window_data_fn):
        """
        Generic signal emitter used by all family engines.

        Args:
            events: list of Phase 1 events for this family
            engine_id: identifier for the engine (e.g., 'git', 'ci', 'testing')
            source_type: source type string
            metric_fn: fn(event) -> dict of metric_name -> value
            window_data_fn: fn(event, metrics) -> dict of window state to store
        """
        window = deque(maxlen=self.window_size)
        signals = []

        for e in events:
            metrics = metric_fn(e)

            if len(window) >= self.min_baseline:
                for metric_name, observed in metrics.items():
                    if observed is None:
                        continue
                    history = [w["metrics"][metric_name] for w in window
                               if metric_name in w["metrics"]
                               and w["metrics"][metric_name] is not None]
                    if len(history) < self.min_baseline:
                        continue

                    baseline_mean = mean(history)
                    baseline_std = pstdev(history) if len(history) > 1 else 0.0
                    robust = compute_robust_deviation(observed, history)

                    signal = {
                        "engine_id": engine_id,
                        "source_type": source_type,
                        "metric": metric_name,
                        "window": {"type": "rolling", "size": self.window_size},
                        "baseline": {
                            "mean": baseline_mean, "stddev": baseline_std,
                            "median": robust["median"], "mad": robust["mad"],
                        },
                        "observed": observed,
                        "deviation": {
                            "measure": robust["measure"] if robust["measure"] is not None else 0.0,
                            "unit": robust["unit"],
                            "degenerate": robust["degenerate"],
                        },
                        "confidence": {
                            "sample_count": len(history),
                            "status": "sufficient" if len(history) >= self.window_size else "accumulating",
                        },
                        "event_ref": e.get("event_id", ""),
                    }
                    signals.append(signal)

            window_entry = {"metrics": metrics}
            extra = window_data_fn(e, metrics)
            if extra:
                window_entry.update(extra)
            window.append(window_entry)

        return signals

    # =============== Git (Version Control) ===============

    def _git_metrics(self, event):
        files = set(event["payload"].get("files", []))
        return {
            "files_touched": len(files),
            "dispersion": self._dispersion(files),
        }

    def _git_extended_metrics(self, event, metrics, window):
        """Compute metrics that need window state (co-change, locality)."""
        files = set(event["payload"].get("files", []))
        current_pairs = self._cochange_pairs(files)
        recent_files = set().union(*(w["files"] for w in window)) if window else set()
        locality = len(files & recent_files) / len(files) if files else 0.0

        metrics["change_locality"] = locality
        metrics["cochange_novelty_ratio"] = 1.0

        if window:
            historical_pairs = set().union(*(w["pairs"] for w in window))
            if current_pairs:
                unseen = current_pairs - historical_pairs
                metrics["cochange_novelty_ratio"] = len(unseen) / len(current_pairs)

        return metrics

    def _dispersion(self, files):
        if not files:
            return 0.0
        buckets = defaultdict(int)
        for f in files:
            top = Path(f).parts[0] if Path(f).parts else "_root"
            buckets[top] += 1
        total = sum(buckets.values())
        entropy = 0.0
        for count in buckets.values():
            p = count / total
            entropy -= p * math.log2(p)
        return entropy

    def _cochange_pairs(self, files):
        pairs = set()
        fl = sorted(files)
        for i in range(len(fl)):
            for j in range(i + 1, len(fl)):
                pairs.add((fl[i], fl[j]))
        return pairs

    def run_git(self):
        """Git-specific engine with co-change and locality metrics."""
        events = self._load_events(source_type="git")
        window = deque(maxlen=self.window_size)
        signals = []

        for e in events:
            files = set(e["payload"].get("files", []))
            metrics = {
                "files_touched": len(files),
                "dispersion": self._dispersion(files),
            }

            # Cap pair tracking for mega-commits (>30 files) to prevent
            # quadratic pair explosion that makes novelty trivially high
            MAX_PAIR_FILES = 30
            if len(files) <= MAX_PAIR_FILES:
                current_pairs = self._cochange_pairs(files)
            else:
                current_pairs = set()

            recent_files = set().union(*(w["files"] for w in window)) if window else set()
            locality = len(files & recent_files) / len(files) if files else 0.0

            metrics["change_locality"] = locality

            if current_pairs and window:
                historical_pairs = set()
                for w in window:
                    historical_pairs.update(w.get("pairs", set()))
                unseen = current_pairs - historical_pairs
                metrics["cochange_novelty_ratio"] = len(unseen) / len(current_pairs)
            elif current_pairs:
                metrics["cochange_novelty_ratio"] = 1.0
            # else: skip novelty metric for mega-commits (None excluded by _emit_signals)

            if len(window) >= self.min_baseline:
                for metric_name, observed in metrics.items():
                    if observed is None:
                        continue
                    history = [w["metrics"][metric_name] for w in window
                               if w["metrics"].get(metric_name) is not None]
                    if len(history) < self.min_baseline:
                        continue
                    baseline_mean = mean(history)
                    baseline_std = pstdev(history) if len(history) > 1 else 0.0
                    robust = compute_robust_deviation(observed, history)

                    signal = {
                        "engine_id": "git",
                        "source_type": "git",
                        "metric": metric_name,
                        "window": {"type": "rolling", "size": self.window_size},
                        "baseline": {
                            "mean": baseline_mean, "stddev": baseline_std,
                            "median": robust["median"], "mad": robust["mad"],
                        },
                        "observed": observed,
                        "deviation": {
                            "measure": robust["measure"] if robust["measure"] is not None else 0.0,
                            "unit": robust["unit"],
                            "degenerate": robust["degenerate"],
                        },
                        "confidence": {
                            "sample_count": len(window),
                            "status": "sufficient" if len(window) >= self.window_size else "accumulating",
                        },
                        "event_ref": e["event_id"],
                    }
                    signals.append(signal)

            window.append({
                "files": files,
                "pairs": current_pairs,
                "metrics": metrics,
            })

        out_file = self.output_path / "git_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)

        return signals

    # =============== CI ===============

    def run_ci(self):
        events = self._load_events(source_family="ci")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            duration = payload.get("timing", {}).get("duration_seconds", 0.0)
            conclusion = payload.get("conclusion", payload.get("status", ""))
            return {
                "run_duration": duration,
                "run_failed": 1.0 if conclusion == "failure" else 0.0,
            }

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "ci", "github_actions", metric_fn, window_fn)

        out_file = self.output_path / "ci_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Testing ===============

    def run_testing(self):
        events = self._load_events(source_family="testing")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            summary = payload.get("summary", {})
            total = summary.get("total", 0)
            return {
                "total_tests": total,
                "failure_rate": summary.get("failed", 0) / max(total, 1),
                "skip_rate": summary.get("skipped", 0) / max(total, 1),
                "suite_duration": payload.get("execution", {}).get("duration_seconds", 0.0),
            }

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "testing", "junit_xml", metric_fn, window_fn)

        out_file = self.output_path / "testing_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Coverage ===============

    def run_coverage(self):
        events = self._load_events(source_family="coverage")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            return {
                "line_rate": payload.get("line_rate", 0.0),
                "branch_rate": payload.get("branch_rate", 0.0),
            }

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "coverage", "coverage_xml", metric_fn, window_fn)

        out_file = self.output_path / "coverage_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Dependency ===============

    def run_dependency(self):
        events = self._load_events(source_family="dependency")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            snap = payload.get("snapshot", {})
            metrics = {
                "dependency_count": snap.get("total_count", 0),
            }
            # Only emit max_depth for ecosystems with transitive resolution
            ecosystem = payload.get("ecosystem", "")
            if ecosystem in ("npm", "go", "cargo", "bundler"):
                metrics["max_depth"] = snap.get("max_depth", 1)
            return metrics

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "dependency", "pip", metric_fn, window_fn)

        out_file = self.output_path / "dependency_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Schema ===============

    def run_schema(self):
        events = self._load_events(source_family="schema")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            structure = payload.get("structure", {})
            diff = payload.get("diff", {})
            total_endpoints = max(structure.get("endpoint_count", 0), 1)
            churn = (
                diff.get("endpoints_added", 0) + diff.get("endpoints_removed", 0) +
                diff.get("fields_added", 0) + diff.get("fields_removed", 0) +
                diff.get("types_added", 0) + diff.get("types_removed", 0)
            )
            return {
                "endpoint_count": structure.get("endpoint_count", 0),
                "type_count": structure.get("type_count", 0),
                "field_count": structure.get("field_count", 0),
                "schema_churn": churn / total_endpoints,
            }

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "schema", "openapi", metric_fn, window_fn)

        out_file = self.output_path / "schema_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Deployment ===============

    def run_deployment(self):
        events = self._load_events(source_family="deployment")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            timing = payload.get("timing", {})
            cadence = timing.get("since_previous_seconds")
            metrics = {
                "is_prerelease": 1.0 if payload.get("is_prerelease", False) else 0.0,
                "asset_count": payload.get("asset_count", 0),
            }
            # release_cadence_hours: None for the first release (no previous)
            if cadence is not None:
                metrics["release_cadence_hours"] = cadence / 3600.0
            return metrics

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "deployment", "github_releases", metric_fn, window_fn)

        out_file = self.output_path / "deployment_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Config ===============

    def run_config(self):
        events = self._load_events(source_family="config")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            structure = payload.get("structure", {})
            diff = payload.get("diff", {})
            churn = (
                diff.get("resources_added", 0) +
                diff.get("resources_removed", 0) +
                diff.get("resources_modified", 0)
            )
            return {
                "resource_count": structure.get("resource_count", 0),
                "resource_type_count": structure.get("resource_types", 0),
                "config_churn": churn,
            }

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "config", "terraform", metric_fn, window_fn)

        out_file = self.output_path / "config_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Error Tracking ===============

    def run_error_tracking(self):
        events = self._load_events(source_family="error_tracking")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            stats = payload.get("stats", {})
            return {
                "event_count": stats.get("event_count", 0),
                "user_count": stats.get("user_count", 0),
                "is_unhandled": 1.0 if payload.get("is_unhandled", False) else 0.0,
            }

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "error_tracking", "sentry", metric_fn, window_fn)

        out_file = self.output_path / "error_tracking_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Security ===============

    def run_security(self):
        events = self._load_events(source_family="security")
        if not events:
            return []

        def metric_fn(e):
            payload = e["payload"]
            summary = payload.get("summary", {})
            findings = payload.get("findings", [])
            total = summary.get("total", 0)
            fixable = sum(1 for f in findings if f.get("fixed_version"))
            return {
                "vulnerability_count": total,
                "critical_count": summary.get("critical", 0),
                "fixable_ratio": fixable / max(total, 1),
            }

        def window_fn(e, m):
            return None

        signals = self._emit_signals(events, "security", "trivy", metric_fn, window_fn)

        out_file = self.output_path / "security_signals.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2)
        return signals

    # =============== Run All ===============

    def run_all(self):
        """Run Phase 2 for all families sequentially. Returns dict of family -> signals."""
        results = {}
        results["git"] = self.run_git()
        results["ci"] = self.run_ci()
        results["testing"] = self.run_testing()
        results["coverage"] = self.run_coverage()
        results["dependency"] = self.run_dependency()
        results["schema"] = self.run_schema()
        results["deployment"] = self.run_deployment()
        results["config"] = self.run_config()
        results["security"] = self.run_security()
        results["error_tracking"] = self.run_error_tracking()
        return results

    def run_all_parallel(self, max_workers: int = 4):
        """Run Phase 2 for all families concurrently. Returns dict of family -> signals.

        Each family reads its own events and writes its own signal file,
        so they are safe to run in parallel.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        runners = {
            "git": self.run_git,
            "ci": self.run_ci,
            "testing": self.run_testing,
            "coverage": self.run_coverage,
            "dependency": self.run_dependency,
            "schema": self.run_schema,
            "deployment": self.run_deployment,
            "config": self.run_config,
            "security": self.run_security,
            "error_tracking": self.run_error_tracking,
        }

        results = {}
        with ThreadPoolExecutor(max_workers=max_workers,
                                thread_name_prefix="p2") as executor:
            future_to_family = {
                executor.submit(fn): name for name, fn in runners.items()
            }
            for future in as_completed(future_to_family):
                family = future_to_family[future]
                try:
                    results[family] = future.result()
                except Exception as e:
                    print(f"  [Phase 2] {family} failed: {e}")
                    results[family] = []

        return results
