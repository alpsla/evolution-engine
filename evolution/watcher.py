"""
Commit watcher for Evolution Engine.

Monitors the git repository for new commits and automatically runs
analysis when changes are detected.

Usage:
    from evolution.watcher import CommitWatcher
    watcher = CommitWatcher(repo_path=".", evo_dir=".evo")
    watcher.run()                    # Foreground mode
    watcher.start_daemon()           # Background daemon
    CommitWatcher.stop_daemon(".")   # Stop daemon
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Severity levels ordered from most to least severe
SEVERITY_LEVELS = ("critical", "concern", "watch", "info")


class CommitWatcher:
    """Watch a git repository for new commits and run analysis.

    Args:
        repo_path: Path to the git repository.
        evo_dir: Path to the .evo directory (default: repo_path/.evo).
        interval: Polling interval in seconds (default 10).
        min_severity: Minimum advisory severity to notify about.
            One of "critical", "concern", "watch", "info".
        callback: Optional callable(advisory_dict) for custom notification
            when an advisory meets the severity threshold.
    """

    def __init__(
        self,
        repo_path: str = ".",
        evo_dir: Optional[str] = None,
        interval: int = 10,
        min_severity: str = "concern",
        callback: Optional[Callable] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.evo_dir = Path(evo_dir).resolve() if evo_dir else self.repo_path / ".evo"
        self.interval = max(1, interval)
        self.min_severity = min_severity if min_severity in SEVERITY_LEVELS else "concern"
        self.callback = callback

    # ─────────────────── Git Helpers ───────────────────

    def _get_current_head(self) -> str:
        """Get current HEAD commit SHA using git rev-parse."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git rev-parse HEAD failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def _get_current_branch(self) -> str:
        """Get current branch name using git rev-parse --abbrev-ref."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git rev-parse --abbrev-ref HEAD failed: {result.stderr.strip()}")
        return result.stdout.strip()

    # ─────────────────── Analysis ───────────────────

    def _run_analysis(self) -> dict:
        """Run orchestrator analysis and return the result dict."""
        # Lazy import to keep the module lightweight
        from evolution.orchestrator import Orchestrator

        orch = Orchestrator(repo_path=str(self.repo_path), evo_dir=str(self.evo_dir))
        return orch.run(quiet=True)

    def _check_threshold(self, advisory: dict) -> bool:
        """Check if an advisory result meets the minimum severity threshold.

        Args:
            advisory: The result dict from orchestrator.run(), which may contain
                an "advisory" key with a "status" sub-dict having a "level" field.

        Returns:
            True if the advisory level meets or exceeds min_severity.
        """
        from evolution.friendly import status_meets_threshold

        # Extract the status level from the advisory result
        status_info = advisory.get("advisory", {}).get("status", {})
        status_level = status_info.get("level", "all_clear")
        return status_meets_threshold(status_level, self.min_severity)

    # ─────────────────── Foreground Mode ───────────────────

    def run(self) -> dict:
        """Run the watcher in the foreground.

        Polls for new commits every `interval` seconds. When a new commit
        is detected, runs analysis and optionally triggers the callback.

        Returns:
            Dict with run stats: commits_seen, analyses_run, alerts_triggered.
        """
        stats = {"commits_seen": 0, "analyses_run": 0, "alerts_triggered": 0}

        branch = self._get_current_branch()
        last_sha = self._get_current_head()
        print(f"[evo watch] Watching {self.repo_path} (branch: {branch})")
        print(f"[evo watch] Current HEAD: {last_sha[:12]}")
        print(f"[evo watch] Polling every {self.interval}s, min severity: {self.min_severity}")
        print(f"[evo watch] Press Ctrl+C to stop.\n")

        try:
            while True:
                time.sleep(self.interval)

                try:
                    current_sha = self._get_current_head()
                except Exception as exc:
                    logger.debug("Failed to get HEAD: %s", exc)
                    continue

                if current_sha == last_sha:
                    continue

                # New commit detected
                stats["commits_seen"] += 1
                last_sha = current_sha
                print(f"[evo watch] New commit detected: {current_sha[:12]}")

                # Run analysis
                try:
                    result = self._run_analysis()
                    stats["analyses_run"] += 1
                except Exception as exc:
                    print(f"[evo watch] Analysis failed: {exc}")
                    logger.exception("Analysis failed")
                    continue

                # Print summary
                status = result.get("advisory_status", "unknown")
                advisory_info = result.get("advisory", {})
                level = advisory_info.get("status", {}).get("level", "all_clear")
                label = advisory_info.get("status", {}).get("label", "All Clear")
                sig_changes = advisory_info.get("significant_changes", 0)
                print(f"[evo watch] Analysis complete: {label} "
                      f"({sig_changes} significant change(s))")

                # Check threshold and notify
                if self._check_threshold(result):
                    stats["alerts_triggered"] += 1
                    print(f"[evo watch] *** Alert: {label} ***")
                    if self.callback:
                        try:
                            self.callback(advisory_info)
                        except Exception as exc:
                            logger.debug("Callback failed: %s", exc)

                print()  # blank line between analyses

        except KeyboardInterrupt:
            print(f"\n[evo watch] Stopped. "
                  f"Commits seen: {stats['commits_seen']}, "
                  f"Analyses run: {stats['analyses_run']}, "
                  f"Alerts triggered: {stats['alerts_triggered']}")
            return stats

    # ─────────────────── Daemon Mode ───────────────────

    def _pid_file(self) -> Path:
        """Path to the daemon PID file."""
        return self.evo_dir / "watch.pid"

    def _log_file(self) -> Path:
        """Path to the daemon log file."""
        return self.evo_dir / "watch.log"

    def start_daemon(self) -> dict:
        """Start the watcher as a background daemon.

        Forks a child process that runs the watcher loop, writing output
        to .evo/watch.log and recording its PID in .evo/watch.pid.

        Returns:
            {"ok": True, "pid": <int>} on success.
            {"ok": False, "error": <str>} on failure.
        """
        # Ensure .evo dir exists
        self.evo_dir.mkdir(parents=True, exist_ok=True)

        # Check for existing daemon
        status = CommitWatcher.daemon_status(str(self.repo_path), str(self.evo_dir))
        if status["running"]:
            return {"ok": False, "error": f"Daemon already running (PID {status['pid']})"}

        # Clean up stale PID file if present
        pid_file = self._pid_file()
        if pid_file.exists():
            pid_file.unlink()

        # Fork
        try:
            pid = os.fork()
        except OSError as exc:
            return {"ok": False, "error": f"Fork failed: {exc}"}

        if pid > 0:
            # Parent: write PID file and return
            pid_file.write_text(str(pid))
            return {"ok": True, "pid": pid}

        # ── Child process (daemon) ──
        try:
            # Create new session
            os.setsid()

            # Redirect stdout/stderr to log file
            log_path = self._log_file()
            log_fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            os.dup2(log_fd, sys.stdout.fileno())
            os.dup2(log_fd, sys.stderr.fileno())
            os.close(log_fd)

            # Close stdin
            devnull = os.open(os.devnull, os.O_RDONLY)
            os.dup2(devnull, sys.stdin.fileno())
            os.close(devnull)

            # Handle SIGTERM for graceful shutdown
            def _sigterm_handler(signum, frame):
                raise SystemExit(0)

            signal.signal(signal.SIGTERM, _sigterm_handler)

            # Write PID file (child overwrites with its own PID after setsid)
            pid_file.write_text(str(os.getpid()))

            # Run the watcher loop (KeyboardInterrupt won't happen in daemon,
            # but SystemExit from SIGTERM will be caught)
            branch = self._get_current_branch()
            last_sha = self._get_current_head()
            print(f"[evo watch daemon] Started on {self.repo_path} (branch: {branch})")
            print(f"[evo watch daemon] HEAD: {last_sha[:12]}, interval: {self.interval}s")
            sys.stdout.flush()

            while True:
                time.sleep(self.interval)
                try:
                    current_sha = self._get_current_head()
                except Exception:
                    continue

                if current_sha == last_sha:
                    continue

                last_sha = current_sha
                print(f"[evo watch daemon] New commit: {current_sha[:12]}")
                sys.stdout.flush()

                try:
                    result = self._run_analysis()
                    advisory_info = result.get("advisory", {})
                    label = advisory_info.get("status", {}).get("label", "All Clear")
                    print(f"[evo watch daemon] Analysis: {label}")

                    if self._check_threshold(result) and self.callback:
                        try:
                            self.callback(advisory_info)
                        except Exception:
                            pass

                except Exception as exc:
                    print(f"[evo watch daemon] Analysis failed: {exc}")

                sys.stdout.flush()

        except SystemExit:
            print("[evo watch daemon] Stopped.")
            sys.stdout.flush()
        finally:
            # Clean up PID file
            try:
                pid_file = self._pid_file()
                if pid_file.exists():
                    pid_file.unlink()
            except Exception:
                pass
            os._exit(0)

    # ─────────────────── Class Methods ───────────────────

    @classmethod
    def stop_daemon(cls, repo_path: str, evo_dir: str = None) -> dict:
        """Stop a running daemon.

        Args:
            repo_path: Path to the git repository.
            evo_dir: Path to the .evo directory (default: repo_path/.evo).

        Returns:
            {"ok": True} on success.
            {"ok": False, "error": <str>} on failure.
        """
        repo = Path(repo_path).resolve()
        evo = Path(evo_dir).resolve() if evo_dir else repo / ".evo"
        pid_file = evo / "watch.pid"

        if not pid_file.exists():
            return {"ok": False, "error": "No PID file found — daemon not running"}

        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError) as exc:
            return {"ok": False, "error": f"Failed to read PID file: {exc}"}

        # Check if process is running
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            # Process not running, clean up stale PID file
            pid_file.unlink(missing_ok=True)
            return {"ok": False, "error": f"Process {pid} not running (stale PID file removed)"}
        except PermissionError:
            pass  # Process exists but we don't own it — try SIGTERM anyway

        # Send SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            return {"ok": False, "error": f"Failed to send SIGTERM to {pid}: {exc}"}

        # Wait briefly for process to exit
        for _ in range(10):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break  # Process exited

        # Clean up PID file
        pid_file.unlink(missing_ok=True)

        return {"ok": True}

    @classmethod
    def daemon_status(cls, repo_path: str, evo_dir: str = None) -> dict:
        """Check if a daemon is running.

        Args:
            repo_path: Path to the git repository.
            evo_dir: Path to the .evo directory (default: repo_path/.evo).

        Returns:
            {"running": True, "pid": <int>} if daemon is running.
            {"running": False, "pid": None} otherwise.
        """
        repo = Path(repo_path).resolve()
        evo = Path(evo_dir).resolve() if evo_dir else repo / ".evo"
        pid_file = evo / "watch.pid"

        if not pid_file.exists():
            return {"running": False, "pid": None}

        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            return {"running": False, "pid": None}

        # Check if process is actually running
        try:
            os.kill(pid, 0)
            return {"running": True, "pid": pid}
        except ProcessLookupError:
            return {"running": False, "pid": None}
        except PermissionError:
            # Process exists but we can't signal it — assume running
            return {"running": True, "pid": pid}
