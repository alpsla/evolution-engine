"""
CLI Tool — Primary user interface for Evolution Engine.

Usage:
    evo analyze [path]               # Detect adapters, run Phases 1-5
    evo analyze . --token ghp_xxx    # Unlock Tier 2 (CI, releases, security)
    evo analyze . --show-prompt      # Print investigation prompt after analysis
    evo sources [path]               # Show connected + detected data sources
    evo sources --what-if datadog    # Estimate impact of adding adapters
    evo accept [path] 1 3                         # Accept permanently (default)
    evo accept [path] 1 --scope commits --from abc123 --to def456
    evo accept [path] 1 --scope dates --from 2026-02-10 --to 2026-02-14
    evo accept [path] 1 --scope this-run          # Dismiss for this run only
    evo accepted list [path]          # Show all accepted deviations
    evo accepted remove [path] <key>  # Un-accept a deviation
    evo accepted clear [path]         # Remove all acceptances
    evo investigate [path]           # AI investigation of advisory findings
    evo fix [path]                   # AI fix loop (iterate until EE confirms clear)
    evo fix . --dry-run              # Preview fix prompt without modifying files
    evo fix . --dry-run --residual   # Iteration-aware prompt (current vs previous)
    evo status [path]                # Show detected adapters and last run info
    evo report [path]                # Generate HTML report
    evo patterns list                # Show KB contents
    evo patterns export              # Export anonymized pattern digests
    evo patterns import <file>       # Import community patterns
    evo patterns pull                # Fetch community patterns from registry
    evo patterns push                # Share patterns (requires privacy_level >= 1)
    evo config list                  # Show all config settings
    evo config get <key>             # Get a config value
    evo config set <key> <value>     # Set a config value
    evo setup                        # Interactive configuration wizard
    evo setup --ui                   # Browser-based settings page
    evo init [path]                  # Guided project initialization
    evo init . --path hooks          # Set up git hook integration
    evo watch [path]                 # Watch for commits and auto-analyze
    evo watch . --daemon             # Run watcher in background
    evo hooks install [path]         # Install EE git hook
    evo hooks uninstall [path]       # Remove EE git hooks
    evo hooks status [path]          # Show git hook status
    evo license status               # Show current license status
    evo license activate <key>       # Save license key
    evo verify <previous>            # Fix verification loop
    evo history list [-n 20]         # Show run snapshots
    evo history show <run>           # View a specific run's summary
    evo history diff [r1 r2]         # Compare two runs
    evo history clean [-k N]         # Delete old snapshots
"""

import json
import os
import sys
from pathlib import Path

import click

from evolution import __version__


def _open_report_with_server(evo_dir: Path, report_path: Path):
    """Launch report server as subprocess and open browser.

    Falls back to file:// URL if the server fails to start.
    """
    import subprocess
    import time
    import webbrowser

    try:
        from evolution.report_server import ReportServer
        port = ReportServer.find_available_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "evolution.report_server",
             str(evo_dir), str(report_path), str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.3)
        if proc.poll() is not None:
            raise RuntimeError("Server exited immediately")
        webbrowser.open(f"http://127.0.0.1:{port}")
    except Exception:
        webbrowser.open(report_path.resolve().as_uri())


@click.group()
@click.version_option(version=__version__, prog_name="evo")
def main():
    """Evolution Engine — Git-native codebase evolution indexer."""
    pass


# ─────────────────── evo analyze ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--token", "-t", help="GitHub token for Tier 2 adapters")
@click.option("--families", "-f", help="Comma-separated family override (e.g. git,ci,dependency)")
@click.option("--evo-dir", "-o", help="Output directory (default: <path>/.evo)")
@click.option("--json", "json_output", is_flag=True, help="Output machine-readable JSON")
@click.option("--llm", is_flag=True, help="Enable LLM-enhanced explanations")
@click.option("--scope", "-s", help="Scope identifier for the advisory")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed phase-level output")
@click.option("--show-prompt", is_flag=True, help="Print investigation prompt after analysis")
@click.option("--no-report", is_flag=True, help="Skip HTML report generation")
@click.option("--open/--no-open", "open_browser", default=None, help="Open HTML report in browser (default: auto-detect TTY)")
@click.option("--verify", is_flag=True, help="Compare results against previous run after analysis")
def analyze(path, token, families, evo_dir, json_output, llm, scope, quiet, verbose, show_prompt, no_report, open_browser, verify):
    """Analyze a repository. Detects adapters automatically."""
    from evolution.orchestrator import Orchestrator

    tokens = {}
    if token:
        tokens["github_token"] = token

    families_list = families.split(",") if families else None

    orch = Orchestrator(
        repo_path=path,
        evo_dir=evo_dir,
        tokens=tokens,
        enable_llm=llm,
        families=families_list,
    )

    result = orch.run(
        scope=scope,
        json_output=json_output,
        quiet=quiet,
        verbose=verbose,
    )

    # Telemetry: prompt on first analyze, track completion
    from evolution.telemetry import prompt_consent, track_event
    prompt_consent()

    if json_output:
        click.echo(json.dumps(result, indent=2))
    elif result["status"] == "no_events":
        click.echo(result["message"])
        sys.exit(1)
    elif result["status"] == "complete" and not quiet:
        # Show structured advisory summary
        advisory = result.get("advisory", {})
        status_info = advisory.get("status", {})
        icon = status_info.get("icon", "")
        label = status_info.get("label", "Complete")
        changes = advisory.get("significant_changes", 0)
        families = advisory.get("families_affected", [])
        patterns = advisory.get("patterns_matched", 0)

        click.echo(f"\n{icon} {label}")
        click.echo(f"  {changes} significant change(s) across {', '.join(families) or 'no families'}")
        if patterns:
            click.echo(f"  {patterns} pattern(s) matched")
        if status_info.get("level") in ("action_required", "needs_attention"):
            click.echo(f"\n  Run `evo investigate .` for AI-powered root cause analysis")
            click.echo(f"  Run `evo accept . <N>` to dismiss expected changes")

    # Track analyze completion + run counter for activation metrics
    if result["status"] == "complete":
        from evolution.config import EvoConfig
        from datetime import datetime, timezone
        try:
            cfg = EvoConfig()
            run_number = cfg.get("stats.analyze_count", 0) + 1
            now_ts = datetime.now(timezone.utc).isoformat()
            cfg.set("stats.analyze_count", run_number)
            if run_number == 1:
                cfg.set("stats.first_analyze_ts", now_ts)
            cfg.set("stats.last_analyze_ts", now_ts)
        except Exception:
            run_number = 0

        advisory = result.get("advisory", {})
        track_event("analyze_complete", {
            "families": advisory.get("families_affected", []),
            "signal_count": advisory.get("significant_changes", 0),
            "pattern_count": advisory.get("patterns_matched", 0),
            "run_number": run_number,
        })

    if show_prompt and result["status"] == "complete":
        evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
        prompt_path = evo_path / "phase5" / "investigation_prompt.txt"
        if prompt_path.exists():
            click.echo("\n" + "=" * 60)
            click.echo("INVESTIGATION PROMPT (paste into any AI coding tool)")
            click.echo("=" * 60)
            click.echo(prompt_path.read_text())

    # --verify: compare against previous run
    verify_diff = None
    if verify and result["status"] == "complete" and not json_output:
        try:
            from evolution.history import HistoryManager
            evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
            hm = HistoryManager(evo_path)
            runs = hm.list_runs(limit=2)
            if len(runs) >= 2:
                verify_diff = hm.compare(runs[1]["timestamp"], runs[0]["timestamp"])
                # Persist so `evo report` can render the banner too
                verify_path = evo_path / "phase5" / "verification.json"
                verify_path.write_text(json.dumps(verify_diff, default=str))
                click.echo()
                click.echo(verify_diff["summary_text"])
            else:
                click.echo("\nNo previous run to compare against (this is the first analysis).")
        except Exception as e:
            click.echo(f"\n[warn] Could not compare runs: {e}")

    # Auto-generate HTML report (unless --no-report or --json)
    if result["status"] == "complete" and not json_output and not no_report:
        try:
            from evolution.report_generator import generate_report

            evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
            html = generate_report(evo_path, verification=verify_diff)
            report_path = evo_path / "report.html"
            report_path.write_text(html)

            resolved = report_path.resolve()
            file_url = resolved.as_uri()  # proper file:///path on all platforms
            click.echo(f"\nReport: \033]8;;{file_url}\033\\{report_path}\033]8;;\033\\")

            # Auto-open: True if explicitly requested, or if TTY detected and not explicitly disabled
            should_open = open_browser if open_browser is not None else sys.stdout.isatty()
            if should_open:
                _open_report_with_server(evo_path, report_path)
        except Exception as e:
            if not quiet:
                click.echo(f"\n[warn] Could not generate report: {e}")

    # Version update nudge (non-blocking, uses cache)
    if result["status"] == "complete":
        try:
            from evolution.adapter_versions import check_self_update_nudge
            nudge = check_self_update_nudge()
            if nudge:
                click.echo()
                click.echo(nudge)
        except Exception:
            pass  # Never let version check break analyze

    # Notification check (adapter updates, available adapters, etc.)
    if result["status"] == "complete" and not json_output:
        try:
            from evolution.notifications import check_and_notify, format_notifications
            evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
            pending = check_and_notify(repo_path=path, evo_dir=evo_path)
            display = format_notifications(pending)
            if display:
                click.echo(display)
        except Exception:
            pass  # Never let notifications break analyze

    # Post-analyze sharing prompt (one-time, TTY only)
    if (result["status"] == "complete"
            and not json_output and not quiet
            and result.get("shareable_patterns", 0) > 0
            and sys.stdout.isatty()):
        try:
            from evolution.config import EvoConfig
            cfg = EvoConfig()
            already_prompted = cfg.get("sync.share_prompted", False)
            privacy_level = cfg.get("sync.privacy_level", 0)
            if not already_prompted and privacy_level < 1:
                n = result["shareable_patterns"]
                click.echo(f"\nFound {n} pattern(s) ready to share with the community.")
                click.echo("Sharing sends anonymized statistics only (no code leaves your machine).")
                if click.confirm("Share patterns with the community?", default=False):
                    cfg.set("sync.privacy_level", 1)
                    from evolution.kb_sync import KBSync
                    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
                    sync = KBSync(evo_dir=evo_path, config=cfg)
                    sync_result = sync.push()
                    if sync_result.success:
                        click.echo(f"Shared {sync_result.pushed} pattern(s). Thank you!")
                    else:
                        click.echo(f"Could not share patterns: {sync_result.error}")
                else:
                    click.echo("No problem. Run `evo patterns push .` anytime.")
                cfg.set("sync.share_prompted", True)
        except Exception:
            pass  # Never let sharing prompt break analyze


# ─────────────────── evo accept ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.argument("indices", nargs=-1, type=int, required=True)
@click.option("--reason", "-r", default="", help="Why this deviation is expected")
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--scope", type=click.Choice(["permanent", "commits", "dates", "this-run"]),
              default="permanent", help="Scope of acceptance")
@click.option("--from", "scope_from", default="", help="Scope start (commit SHA or date)")
@click.option("--to", "scope_to", default="", help="Scope end (commit SHA or date)")
def accept(path, indices, reason, evo_dir, scope, scope_from, scope_to):
    """Accept deviations from the latest advisory by change number.

    After running `evo analyze`, use the numbered change indices to mark
    deviations as expected. Accepted deviations are hidden from future runs.

    Examples:
        evo accept . 1 3              # Accept changes #1 and #3
        evo accept . 1 -r "Expected"  # Accept with a reason
        evo accept . 1 --scope commits --from abc123 --to def456
        evo accept . 1 --scope this-run
    """
    from evolution.accepted import AcceptedDeviations

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
    advisory_path = evo_path / "phase5" / "advisory.json"

    if not advisory_path.exists():
        click.echo("No advisory found. Run `evo analyze` first.")
        sys.exit(1)

    advisory = json.loads(advisory_path.read_text())
    changes = advisory.get("changes", [])
    advisory_id = advisory.get("advisory_id", "")

    if not changes:
        click.echo("No changes in the latest advisory.")
        return

    # Validate indices (1-based)
    invalid = [i for i in indices if i < 1 or i > len(changes)]
    if invalid:
        click.echo(f"Invalid change number(s): {', '.join(map(str, invalid))} "
                    f"(valid range: 1-{len(changes)})")
        sys.exit(1)

    ad = AcceptedDeviations(evo_path)

    # Build scope
    scope_dict = {"type": scope}
    if scope in ("commits", "dates"):
        if not scope_from:
            click.echo(f"--from is required for --scope {scope}")
            sys.exit(1)
        scope_dict["from"] = scope_from
        if scope_to:
            scope_dict["to"] = scope_to
    elif scope == "this-run":
        scope_dict["advisory_id"] = advisory_id

    accepted_items = []
    for idx in indices:
        change = changes[idx - 1]
        key = f"{change['family']}:{change['metric']}"
        if ad.add(key, change["family"], change["metric"],
                  reason=reason, advisory_id=advisory_id, scope=scope_dict):
            accepted_items.append(change)

    if accepted_items:
        click.echo(f"Accepted {len(accepted_items)} deviation(s):")
        for c in accepted_items:
            family_label = c["family"]
            metric_label = c["metric"]
            click.echo(f"  {family_label} / {metric_label}")
    else:
        click.echo("All specified deviations were already accepted.")


# ─────────────────── evo accepted ───────────────────


@main.group(invoke_without_command=True)
@click.pass_context
def accepted(ctx):
    """Manage accepted deviations."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(accepted_list, path=".")


@accepted.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--evo-dir", help="Override .evo directory path")
def accepted_list(path, evo_dir):
    """List all accepted deviations."""
    from datetime import datetime, timezone

    from evolution.accepted import AcceptedDeviations

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
    ad = AcceptedDeviations(evo_path)
    entries = ad.load()

    if not entries:
        click.echo("No accepted deviations.")
        return

    now = datetime.now(timezone.utc)
    click.echo(f"{len(entries)} accepted deviation(s):\n")
    for e in entries:
        age = ""
        try:
            accepted_dt = datetime.fromisoformat(e["accepted_at"])
            days = (now - accepted_dt).days
            if days == 0:
                age = "today"
            elif days == 1:
                age = "1 day ago"
            else:
                age = f"{days} days ago"
        except (ValueError, KeyError):
            pass

        line = f"  {e['family']} / {e['metric']}"
        if age:
            line += f" — accepted {age}"
        if e.get("reason"):
            line += f' — "{e["reason"]}"'
        scope_info = e.get("scope", {})
        scope_type = scope_info.get("type", "permanent")
        if scope_type != "permanent":
            scope_str = f" [{scope_type}"
            if scope_info.get("from"):
                scope_str += f": {scope_info['from']}"
                if scope_info.get("to"):
                    scope_str += f"..{scope_info['to']}"
            scope_str += "]"
            line += scope_str
        click.echo(line)


@accepted.command("remove")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.argument("key")
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--scope-type", type=click.Choice(["permanent", "commits", "dates", "this-run"]),
              help="Remove only acceptances with this scope type")
def accepted_remove(path, key, evo_dir, scope_type):
    """Remove an accepted deviation by family:metric key.

    Example:
        evo accepted remove . git:dispersion
        evo accepted remove . git:dispersion --scope-type this-run
    """
    from evolution.accepted import AcceptedDeviations

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
    ad = AcceptedDeviations(evo_path)

    if scope_type:
        if ad.remove_scoped(key, scope_type):
            click.echo(f"Removed: {key} (scope: {scope_type})")
        else:
            click.echo(f"Not found: {key} with scope {scope_type}")
            sys.exit(1)
    else:
        if ad.remove(key):
            click.echo(f"Removed: {key}")
        else:
            click.echo(f"Not found: {key}")
            sys.exit(1)


@accepted.command("clear")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def accepted_clear(path, evo_dir, yes):
    """Remove all accepted deviations.

    Example:
        evo accepted clear .
    """
    from evolution.accepted import AcceptedDeviations

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
    ad = AcceptedDeviations(evo_path)
    entries = ad.load()

    if not entries:
        click.echo("No accepted deviations to clear.")
        return

    if not yes:
        click.confirm(f"Remove {len(entries)} accepted deviation(s)?", abort=True)

    count = ad.clear()
    click.echo(f"Cleared {count} accepted deviation(s).")


# ─────────────────── evo investigate ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--show-prompt", is_flag=True, help="Just print the prompt (no AI call)")
@click.option("--agent", "agent_type",
              type=click.Choice(["anthropic", "cli", "show-prompt"]),
              help="Force a specific AI backend")
@click.option("--model", help="Override AI model name")
def investigate(path, evo_dir, show_prompt, agent_type, model):
    """Run AI investigation on the latest advisory. [Pro]

    Feeds the Phase 5 advisory into an AI agent to identify root causes,
    assess risk, and suggest fixes. This command uses AI (Claude by Anthropic).
    AI-generated content should be reviewed before acting on recommendations.

    Examples:
        evo investigate .                    # auto-detect AI backend
        evo investigate . --show-prompt      # print prompt for manual use
        evo investigate . --agent anthropic  # force Anthropic API
    """
    from evolution.license import ProFeatureError, require_pro

    try:
        require_pro("AI Investigation", repo_path=path)
    except ProFeatureError as e:
        click.echo(str(e))
        sys.exit(1)

    from evolution.agents.base import get_agent
    from evolution.investigator import Investigator

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"

    try:
        inv = Investigator(evo_dir=evo_path)
    except FileNotFoundError as e:
        click.echo(str(e))
        sys.exit(1)

    if show_prompt:
        report = inv.run(show_prompt=True)
        click.echo(report.text)
        return

    click.echo("Note: This feature uses AI to analyze development patterns. No source code is sent.")
    agent = get_agent(prefer=agent_type, model=model) if agent_type else None
    report = inv.run(agent=agent)

    if not report.success:
        click.echo(f"Investigation failed: {report.error}")
        sys.exit(1)

    click.echo(f"Investigation complete (agent: {report.agent_name})")
    click.echo(f"Saved to: {evo_path / 'investigation'}")
    click.echo()
    click.echo(report.text)
    click.echo()
    click.echo("[AI Disclosure] This report was generated with the assistance of artificial intelligence (Claude by Anthropic). The analysis is based on your repository's metrics and may contain errors. Please review findings before taking action.")

    from evolution.telemetry import track_event
    track_event("cli_command", {"command": "investigate", "agent": report.agent_name})


# ─────────────────── evo fix ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--dry-run", is_flag=True, help="Preview fix prompt without modifying files")
@click.option("--max-iterations", default=3, help="Max fix-verify cycles (default: 3)")
@click.option("--branch", help="Branch name for fixes (default: evo/fix-<timestamp>)")
@click.option("--agent", "agent_type",
              type=click.Choice(["cli", "show-prompt"]),
              help="Force a specific AI backend (must support file editing)")
@click.option("--scope", "-s", help="Scope identifier")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--interactive", "-i", is_flag=True,
              help="Review git diff after each iteration and confirm before continuing")
@click.option("--residual", is_flag=True,
              help="Generate iteration-aware prompt comparing current vs previous advisory")
def fix(path, evo_dir, dry_run, max_iterations, branch, agent_type, scope, yes, interactive, residual):
    """Apply AI fixes and verify with EE in a loop. [Pro]

    Creates a branch, asks an AI agent to fix the flagged issues,
    re-runs EE to verify, and iterates until the advisory clears
    or max iterations are reached. This command uses AI (Claude by Anthropic)
    to generate code suggestions that should be carefully reviewed before merging.

    Examples:
        evo fix . --dry-run              # preview what would be fixed
        evo fix . --dry-run --residual   # iteration-aware prompt (current vs previous)
        evo fix .                        # fix with auto-detected agent
        evo fix . --max-iterations 5     # allow more attempts
        evo fix . --branch my-fix        # custom branch name
        evo fix . --yes                  # skip confirmation prompt
        evo fix . --interactive          # review changes after each iteration
    """
    from evolution.license import ProFeatureError, require_pro

    try:
        require_pro("AI Fix Loop", repo_path=path)
    except ProFeatureError as e:
        click.echo(str(e))
        sys.exit(1)

    import subprocess as _subprocess

    from evolution.agents.base import get_agent
    from evolution.fixer import Fixer

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"

    click.echo("Note: This feature uses AI to analyze development patterns. No source code is sent.")
    fixer = Fixer(repo_path=path, evo_dir=evo_path)

    agent = None
    if agent_type:
        agent = get_agent(prefer=agent_type)
    elif dry_run:
        agent = get_agent(prefer="show-prompt")

    if not dry_run and not yes:
        branch_display = branch or f"evo/fix-<timestamp>"
        click.echo(f"\nThis will modify files on a new branch '{branch_display}'.")
        click.echo(f"  - Max iterations: {max_iterations}")
        click.echo(f"  - Agent: {agent.name if agent else 'auto-detect'}")
        click.echo(f"  - Path: {Path(path).resolve()}")
        if interactive:
            click.echo(f"  - Interactive: yes (will prompt after each iteration)")
        click.echo()
        if not click.confirm("Proceed?"):
            click.echo("Aborted.")
            return

    # Build interactive callback if --interactive is set
    interactive_callback = None
    if interactive:
        repo_abs = str(Path(path).resolve())

        def _interactive_review(iteration):
            """Show git diff and prompt user to continue or abort."""
            click.echo(f"\n{'=' * 60}")
            click.echo(f"ITERATION {iteration.iteration} COMPLETE — Review changes")
            click.echo(f"{'=' * 60}")

            # Show the full git diff
            try:
                proc = _subprocess.run(
                    ["git", "diff"],
                    cwd=repo_abs,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                diff_output = proc.stdout.strip()
                if diff_output:
                    click.echo("\ngit diff:")
                    click.echo(diff_output)
                else:
                    click.echo("\n(no uncommitted changes)")
            except (OSError, _subprocess.TimeoutExpired):
                click.echo("\n(could not capture git diff)")

            click.echo(f"\n  Resolved: {iteration.resolved}, "
                        f"Persisting: {iteration.persisting}, "
                        f"New: {iteration.new_issues}, "
                        f"Regressions: {iteration.regressions}")

            if iteration.all_clear:
                click.echo("\nAll issues resolved!")
                return True

            return click.confirm("\nContinue to next iteration?")

        interactive_callback = _interactive_review

    result = fixer.run(
        agent=agent,
        max_iterations=max_iterations,
        dry_run=dry_run,
        residual=residual,
        branch_name=branch,
        scope=scope,
        interactive_callback=interactive_callback,
    )

    if dry_run:
        label = "DRY RUN (residual)" if residual else "DRY RUN"
        click.echo(f"{label} — no files modified\n")
        if result.iterations:
            click.echo(result.iterations[0].agent_response)
        return

    # Report results
    status_messages = {
        "all_clear": "All advisory items resolved!",
        "partial": "Some issues resolved, some remain.",
        "no_progress": "Fix loop stopped — no progress detected.",
        "max_iterations": f"Max iterations ({max_iterations}) reached.",
        "error": "Fix loop encountered an error.",
        "aborted": "Fix loop aborted by user.",
    }
    click.echo(status_messages.get(result.status, f"Status: {result.status}"))

    if result.branch:
        click.echo(f"Branch: {result.branch}")
    click.echo(f"Iterations: {len(result.iterations)}")
    click.echo(f"Resolved: {result.total_resolved}")
    click.echo(f"Remaining: {result.total_remaining}")

    for it in result.iterations:
        click.echo(f"\n--- Iteration {it.iteration} ---")
        click.echo(f"  Resolved: {it.resolved}, Persisting: {it.persisting}, "
                    f"New: {it.new_issues}, Regressions: {it.regressions}")
    click.echo("\nAI-generated code suggestions should be carefully reviewed before merging.")

    from evolution.telemetry import track_event
    track_event("cli_command", {
        "command": "fix",
        "iterations": len(result.iterations),
        "resolved": result.total_resolved,
        "status": result.status,
    })

    # Save fix result
    output_dir = evo_path / "fix"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "fix_result.json", "w") as f:
        json.dump(result.to_dict(), f, indent=2)
    click.echo(f"\nFull results saved to: {output_dir / 'fix_result.json'}")


# ─────────────────── evo status ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--token", "-t", help="GitHub token to check Tier 2 availability")
def status(path, token):
    """Show detected adapters and last run info."""
    from evolution.registry import AdapterRegistry

    registry = AdapterRegistry(path)
    tokens = {"github_token": token} if token else {}
    summary = registry.summary(tokens)

    click.echo(f"Repository: {summary['repo_path']}")
    click.echo(f"Adapters detected: {summary['adapters_detected']} "
               f"(Tier 1: {summary['tier1_count']}, Tier 2: {summary['tier2_count']})")
    click.echo()

    for family, adapters in summary["families"].items():
        click.echo(f"  {family}:")
        for a in adapters:
            tier_badge = f"[T{a['tier']}]"
            source = f" ({a['source']})" if a.get("source") else ""
            click.echo(f"    {tier_badge} {a['adapter']}{source}")

    if summary["missing_tokens"]:
        click.echo()
        click.echo("Unlock more data:")
        for msg in summary["missing_tokens"]:
            click.echo(f"  {msg}")

    # Show last run info if available
    evo_dir = Path(path) / ".evo"
    advisory_path = evo_dir / "phase5" / "advisory.json"
    if advisory_path.exists():
        try:
            advisory = json.loads(advisory_path.read_text())
            click.echo()
            click.echo(f"Last advisory: {advisory.get('generated_at', 'unknown')}")
            s = advisory.get("summary", {})
            click.echo(f"  Significant changes: {s.get('significant_changes', 0)}")
            click.echo(f"  Families: {', '.join(s.get('families_affected', []))}")
            click.echo(f"  Patterns matched: {s.get('known_patterns_matched', 0)}")
        except (json.JSONDecodeError, KeyError):
            pass


# ─────────────────── evo patterns ───────────────────


@main.group()
def patterns():
    """Manage pattern knowledge base."""
    pass


@patterns.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--scope", help="Filter by scope (local, community, universal)")
def patterns_list(path, scope):
    """List patterns in the knowledge base."""
    from evolution.knowledge_store import SQLiteKnowledgeStore

    db_path = Path(path) / ".evo" / "phase4" / "knowledge.db"
    if not db_path.exists():
        click.echo("No knowledge base found. Run `evo analyze` first.")
        return

    kb = SQLiteKnowledgeStore(db_path)

    click.echo("Patterns:")
    pats = kb.list_patterns(scope=scope)
    if not pats:
        click.echo("  (none)")
    for p in pats:
        sources = ", ".join(p["sources"])
        metrics = ", ".join(p["metrics"])
        corr = p.get("correlation_strength", 0)
        click.echo(f"  [{p['confidence_tier']}] {sources}: {metrics} "
                    f"(r={corr:.2f}, seen={p['occurrence_count']}x)")

    click.echo()
    click.echo("Knowledge Artifacts:")
    kas = kb.list_knowledge(scope=scope)
    if not kas:
        click.echo("  (none)")
    for ka in kas:
        sources = ", ".join(ka["sources"])
        metrics = ", ".join(ka["metrics"])
        click.echo(f"  {sources}: {metrics} (support={ka['support_count']})")
        if ka.get("description_semantic"):
            click.echo(f"    {ka['description_semantic'][:100]}")

    kb.close()


@patterns.command("export")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output file (default: stdout)")
@click.option("--dry-run", is_flag=True, help="Show what would be exported")
def patterns_export(path, output, dry_run):
    """Export anonymized pattern digests."""
    from evolution.kb_export import export_patterns

    db_path = Path(path) / ".evo" / "phase4" / "knowledge.db"
    if not db_path.exists():
        click.echo("No knowledge base found. Run `evo analyze` first.")
        return

    digests = export_patterns(db_path)

    if dry_run:
        click.echo(f"Would export {len(digests)} pattern(s)")
        for d in digests:
            click.echo(f"  {d['fingerprint']}: {', '.join(d['metrics'])}")
        return

    result = json.dumps(digests, indent=2)
    if output:
        Path(output).write_text(result)
        click.echo(f"Exported {len(digests)} patterns to {output}")
    else:
        click.echo(result)


@patterns.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--path", default=".", type=click.Path(exists=True), help="Repository path")
def patterns_import(file, path):
    """Import community patterns from a file."""
    from evolution.kb_export import import_patterns

    db_path = Path(path) / ".evo" / "phase4" / "knowledge.db"
    if not db_path.exists():
        click.echo("No knowledge base found. Run `evo analyze` first.")
        return

    data = json.loads(Path(file).read_text())
    if not isinstance(data, list):
        click.echo("Error: file must contain a JSON array of patterns")
        sys.exit(1)

    result = import_patterns(db_path, data)
    click.echo(f"Imported: {result['imported']}, Skipped: {result['skipped']}, "
               f"Rejected: {result['rejected']}")
    for err in result.get("errors", []):
        click.echo(f"  Error: {err}")


# ─────────────────── evo sources ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--token", "-t", help="GitHub token for Tier 2 adapters")
@click.option("--what-if", "what_if_adapters", multiple=True,
              help="Estimate impact of adding adapters (e.g. --what-if datadog --what-if pagerduty)")
@click.option("--json", "json_output", is_flag=True, help="Output machine-readable JSON")
def sources(path, token, what_if_adapters, json_output):
    """Show connected and detected data sources.

    Scans your repo for tools you already use (CI configs, SDK packages
    in lockfiles, import statements) and shows what connecting them would add.

    Examples:
        evo sources
        evo sources --what-if datadog --what-if pagerduty
        evo sources --json
    """
    from evolution.prescan import SourcePrescan
    from evolution.registry import AdapterRegistry

    tokens = {"github_token": token} if token else {}
    registry = AdapterRegistry(path)
    prescan = SourcePrescan(path)

    # Get connected families from registry
    connected = registry.detect(tokens)
    connected_families = sorted(set(c.family for c in connected))

    # Get detected services from prescan
    detected = prescan.scan()

    # Filter out services whose family is already connected
    connected_family_set = set(connected_families)
    unconnected = [s for s in detected if s.family not in connected_family_set]

    if what_if_adapters:
        result = prescan.what_if(
            current_families=connected_families,
            additional_adapters=list(what_if_adapters),
        )
        if json_output:
            click.echo(json.dumps(result, indent=2))
            return

        click.echo(f"Current:   {len(result['current_families'])} families "
                    f"→ {result['current_combinations']} cross-family combination(s)")
        click.echo(f"Proposed:  {len(result['proposed_families'])} families "
                    f"→ {result['proposed_combinations']} cross-family combination(s)")
        if result["added_families"]:
            click.echo(f"New families: {', '.join(result['added_families'])}")
        click.echo()
        if result["new_questions"]:
            click.echo("New questions EE could answer:")
            for q in result["new_questions"]:
                fams = " × ".join(q["families"])
                click.echo(f"  ? {fams:30s} {q['question']}")
        else:
            click.echo("No new cross-family combinations from these adapters.")
        click.echo()
        click.echo("Try it and compare — you can always disconnect adapters later.")
        return

    if json_output:
        click.echo(json.dumps({
            "connected": [
                {"family": c.family, "adapter": c.adapter_name, "tier": c.tier}
                for c in connected
            ],
            "detected": [
                {
                    "service": s.service,
                    "display_name": s.display_name,
                    "family": s.family,
                    "adapter": s.adapter,
                    "detection_layers": s.detection_layers,
                    "evidence": s.evidence,
                }
                for s in detected
            ],
            "current_families": connected_families,
            "current_combinations": len(connected_families) * (len(connected_families) - 1) // 2,
        }, indent=2))
        return

    # Connected families
    click.echo("CONNECTED (active signal families):")
    if connected:
        for c in connected:
            source = f" ({c.source_file})" if c.source_file else ""
            click.echo(f"  \u2705 {c.family:20s} {c.adapter_name}{source}")
    else:
        click.echo("  (none)")

    # Detected but not connected (third-party services from prescan)
    click.echo()
    if unconnected:
        click.echo("DETECTED (found in your repo — not yet connected):")
        for s in unconnected:
            evidence_str = "; ".join(s.evidence[:2])
            click.echo(f"  \U0001f50d {s.display_name:20s} {evidence_str}")

        # Third-party adapter availability (PyPI check)
        click.echo()
        from evolution.adapter_versions import check_pypi_version as _sources_pypi_check
        for s in unconnected:
            pkg = s.adapter
            latest = _sources_pypi_check(pkg, use_cache=True)
            if latest:
                click.echo(f"  Install: pip install {pkg}  \u2190 {s.display_name} ({s.family})")
            else:
                click.echo(
                    f"  {s.display_name}: community adapter in development "
                    f"\u2014 or build your own: evo adapter new {s.service} --family {s.family}"
                )
    else:
        if detected:
            click.echo("All detected tools are already connected.")
        else:
            click.echo("No additional tools detected in this repo.")

    # Token hints for built-in (Tier 2) adapters
    from evolution.registry import TIER2_DETECTORS
    token_hints = []
    for token_key, adapters in TIER2_DETECTORS.items():
        env_var = token_key.upper()
        if os.environ.get(env_var):
            continue  # token already set
        families = sorted(set(family for _, family in adapters))
        token_hints.append(f"  Set {env_var} to unlock: {', '.join(families)}")
    if token_hints:
        click.echo()
        for hint in token_hints:
            click.echo(hint)

    # Summary
    click.echo()
    n_current = len(set(connected_families))
    n_detected = len(set(s.family for s in unconnected))
    n_total = n_current + n_detected
    combos_current = n_current * (n_current - 1) // 2
    combos_total = n_total * (n_total - 1) // 2

    click.echo(f"Current: {n_current} families → {combos_current} cross-family combination(s)")
    if n_detected > 0:
        click.echo(f"With all detected: {n_total} families "
                    f"→ {combos_total} combination(s) "
                    f"({combos_total}x more patterns)" if combos_current > 0
                    else f"With all detected: {n_total} families "
                         f"→ {combos_total} combination(s)")


# ─────────────────── evo adapter ───────────────────


@main.group()
def adapter():
    """Manage and validate adapter plugins."""
    pass


@adapter.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--token", "-t", help="GitHub token for Tier 2 adapters")
@click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON")
def adapter_list(path, token, as_json):
    """List all detected adapters including plugins and prescanned tools."""
    from evolution.prescan import SourcePrescan
    from evolution.registry import AdapterRegistry

    tokens = {"github_token": token} if token else {}
    registry = AdapterRegistry(path)
    configs = registry.detect(tokens)
    plugins = registry.list_plugins()
    prescan = SourcePrescan(path)
    detected_services = prescan.scan()

    # Build a set of connected families for status display
    connected_families = set(c.family for c in configs)

    if as_json:
        data = {
            "connected": [
                {
                    "tier": c.tier,
                    "trust_level": c.trust_level,
                    "family": c.family,
                    "adapter_name": c.adapter_name,
                    "plugin_name": c.plugin_name or None,
                }
                for c in configs
            ],
            "plugins": [
                {
                    "plugin_name": p["plugin_name"],
                    "family": p["family"],
                    "adapter_name": p["adapter_name"],
                    "detected": p["detected"],
                }
                for p in plugins
            ],
            "detected": [
                {
                    "display_name": s.display_name,
                    "family": s.family,
                    "adapter": s.adapter,
                    "detection_layers": list(s.detection_layers),
                }
                for s in detected_services
                if s.family not in connected_families
            ],
            "blocked": registry.get_blocked(),
        }
        click.echo(json.dumps(data, indent=2))
        return

    click.echo("Connected adapters:")
    if configs:
        for c in configs:
            badge = c.trust_level or {1: "built-in", 2: "built-in", 3: "plugin"}.get(c.tier, f"tier-{c.tier}")
            plugin_note = f"  (from {c.plugin_name})" if c.plugin_name else ""
            click.echo(f"  [{badge:10s}] {c.family}/{c.adapter_name}{plugin_note}")
    else:
        click.echo("  (none)")

    # Show blocked adapters
    blocked = registry.get_blocked()
    if blocked:
        click.echo()
        click.echo("Blocked adapters:")
        for b in blocked:
            reason = f" — {b['reason']}" if b.get("reason") else ""
            click.echo(f"  \u26d4 {b['family']}/{b['adapter_name']}{reason}")

    if plugins:
        click.echo()
        click.echo("Installed plugins:")
        # Check for updates (uses 24h cache, no extra latency)
        try:
            import importlib.metadata
            from evolution.adapter_versions import check_pypi_version
            _update_cache = {}
            for p in plugins:
                try:
                    cur = importlib.metadata.version(p["plugin_name"])
                    latest = check_pypi_version(p["plugin_name"])
                    if latest and latest != cur:
                        _update_cache[p["plugin_name"]] = latest
                except Exception:
                    pass
        except Exception:
            _update_cache = {}
        for p in plugins:
            status = "detected" if p["detected"] else "not detected"
            update_note = ""
            if p["plugin_name"] in _update_cache:
                update_note = f" — update available: {_update_cache[p['plugin_name']]}"
            click.echo(f"  {p['plugin_name']}: {p['family']}/{p['adapter_name']} ({status}){update_note}")

    # Show prescan-detected tools not yet connected
    unconnected = [s for s in detected_services if s.family not in connected_families]
    if unconnected:
        click.echo()
        click.echo("Detected in repo (not yet connected):")
        for s in unconnected:
            layers = ", ".join(s.detection_layers)
            click.echo(f"  \U0001f50d {s.display_name:20s} [{layers}] → {s.adapter}")
            for ev in s.evidence[:2]:
                click.echo(f"     {ev}")

    # Version update nudge (non-blocking, uses cache)
    try:
        from evolution.adapter_versions import check_self_update_nudge
        nudge = check_self_update_nudge()
        if nudge:
            click.echo()
            click.echo(nudge)
    except Exception:
        pass


@adapter.command("validate")
@click.argument("adapter_path")
@click.option("--args", "constructor_args", help="JSON constructor args (e.g. '{\"path\": \"/tmp\"}')")
@click.option("--max-events", default=10, help="Max events to consume during validation")
@click.option("--security", is_flag=True, help="Also run security scan on adapter source")
def adapter_validate(adapter_path, constructor_args, max_events, security):
    """Validate a plugin adapter against the Adapter Contract.

    ADAPTER_PATH is a dotted Python path like 'my_package.MyAdapter'.

    Example:
        evo adapter validate evo_jenkins.JenkinsAdapter
        evo adapter validate evo_jenkins.JenkinsAdapter --security
        evo adapter validate evo_jenkins.JenkinsAdapter --args '{"url": "http://ci"}'
    """
    from evolution.adapter_validator import load_adapter_class, validate_adapter

    # Load the adapter class
    try:
        adapter_cls = load_adapter_class(adapter_path)
    except (ImportError, AttributeError) as e:
        click.echo(f"Error loading adapter: {e}")
        sys.exit(1)

    # Parse constructor args
    kwargs = {}
    if constructor_args:
        try:
            kwargs = json.loads(constructor_args)
        except json.JSONDecodeError as e:
            click.echo(f"Invalid --args JSON: {e}")
            sys.exit(1)

    # Run validation
    report = validate_adapter(adapter_cls, constructor_args=kwargs, max_events=max_events)

    click.echo(report.summary())
    click.echo()

    if report.passed:
        click.echo("Adapter is certified. Ready to publish as a pip package.")
    else:
        click.echo(f"{len(report.errors)} error(s) must be fixed before publishing.")
        sys.exit(1)

    # Optional security scan
    if security:
        from evolution.adapter_security import scan_adapter_source

        # Derive module name from dotted path (strip class name)
        module_path = adapter_path.rpartition(".")[0]
        click.echo()
        click.echo("Running security scan...")
        sec_report = scan_adapter_source(module_path)
        click.echo(sec_report.summary())
        if not sec_report.passed:
            click.echo()
            click.echo("Security scan found critical issues.")
            sys.exit(1)


@adapter.command("guide")
def adapter_guide():
    """Show how to build, test, and publish a plugin adapter."""
    from evolution.adapter_scaffold import print_guide
    print_guide()


@adapter.command("prompt")
@click.argument("name")
@click.option("--family", "-f", required=True,
              type=click.Choice([
                  "ci", "testing", "dependency", "schema",
                  "deployment", "config", "security",
              ]),
              help="Source family this adapter belongs to")
@click.option("--description", "-d", default="",
              help="What the adapter should do")
@click.option("--data-source", default="",
              help="Where the data comes from (API URL, file format, etc.)")
@click.option("--copy", "copy_to_clipboard", is_flag=True,
              help="Copy prompt to clipboard (macOS/Linux)")
def adapter_prompt(name, family, description, data_source, copy_to_clipboard):
    """Generate an AI prompt to build an adapter for you.

    Produces a complete prompt with the adapter contract, examples,
    and validation checklist. Paste it into Claude, ChatGPT, Cursor,
    or any AI coding assistant.

    Example:
        evo adapter prompt jenkins --family ci
        evo adapter prompt jenkins --family ci -d "Fetch builds from Jenkins API"
        evo adapter prompt jenkins --family ci --copy
    """
    from evolution.adapter_scaffold import generate_ai_prompt

    prompt = generate_ai_prompt(
        name=name,
        family=family,
        description=description,
        data_source=data_source,
    )

    if copy_to_clipboard:
        try:
            import subprocess
            process = subprocess.Popen(
                ["pbcopy"] if sys.platform == "darwin" else ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
            )
            process.communicate(prompt.encode("utf-8"))
            click.echo(f"Prompt copied to clipboard ({len(prompt)} chars)")
            click.echo()
            click.echo("Paste it into Claude, ChatGPT, Cursor, or any AI coding assistant.")
        except (FileNotFoundError, OSError):
            click.echo("Could not copy to clipboard. Printing instead:")
            click.echo()
            click.echo(prompt)
    else:
        click.echo(prompt)


@adapter.command("new")
@click.argument("name")
@click.option("--family", "-f", required=True,
              type=click.Choice([
                  "ci", "testing", "dependency", "schema",
                  "deployment", "config", "security",
              ]),
              help="Source family this adapter belongs to")
@click.option("--output", "-o", default=".",
              type=click.Path(), help="Directory to create the package in")
def adapter_new(name, family, output):
    """Scaffold a new adapter plugin package.

    Creates a ready-to-publish pip package with boilerplate code,
    pyproject.toml, tests, and README.

    Example:
        evo adapter new jenkins --family ci
        evo adapter new bitbucket-pipelines --family ci --output ~/projects
    """
    from evolution.adapter_scaffold import scaffold_adapter

    result = scaffold_adapter(name, family, output_dir=output)
    click.echo(f"Created adapter package: {result['package_dir']}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. cd {result['package_dir']}")
    click.echo(f"  2. Edit {result['adapter_file']} with your adapter logic")
    click.echo(f"  3. pip install -e .")
    click.echo(f"  4. evo adapter validate {result['adapter_class_path']}")
    click.echo(f"  5. pip install build && python -m build")
    click.echo(f"  6. pip install twine && twine upload dist/*")


@adapter.command("request")
@click.argument("description")
@click.option("--family", "-f", help="Source family (ci, deployment, etc.)")
def adapter_request(description, family):
    """Request an adapter to be built by the community or team.

    This saves your request locally. Popular requests will be prioritized
    for inclusion in the core package.

    Example:
        evo adapter request "Bitbucket Pipelines CI adapter" --family ci
        evo adapter request "Azure DevOps deployment tracking"
    """
    import datetime

    requests_dir = Path.home() / ".evo" / "adapter_requests"
    requests_dir.mkdir(parents=True, exist_ok=True)

    request_data = {
        "description": description,
        "family": family,
        "requested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    # Append to requests log
    requests_file = requests_dir / "requests.json"
    existing = []
    if requests_file.exists():
        try:
            existing = json.loads(requests_file.read_text())
        except json.JSONDecodeError:
            pass

    existing.append(request_data)
    requests_file.write_text(json.dumps(existing, indent=2))

    click.echo(f"Request recorded: {description}")
    if family:
        click.echo(f"Family: {family}")
    click.echo()
    click.echo("To submit this to the community:")
    click.echo("  https://github.com/evolution-engine/evolution-engine/issues/new")
    click.echo("  Use the 'adapter-request' label")
    click.echo()
    click.echo("Or build it yourself:")
    safe_name = description.lower().split()[0] if description else "my-adapter"
    click.echo(f"  evo adapter new {safe_name} --family {family or 'ci'}")
    click.echo("  evo adapter guide")


@adapter.command("requests")
def adapter_requests():
    """List pending local adapter requests.

    Shows all requests saved via 'evo adapter request', with date,
    family, and description.

    Example:
        evo adapter requests
    """
    requests_file = Path.home() / ".evo" / "adapter_requests" / "requests.json"
    if not requests_file.exists():
        click.echo("No adapter requests saved yet.")
        click.echo()
        click.echo("Submit one with:")
        click.echo('  evo adapter request "Jenkins CI adapter" --family ci')
        return

    try:
        data = json.loads(requests_file.read_text())
    except json.JSONDecodeError:
        click.echo("No adapter requests saved yet.")
        return

    if not data:
        click.echo("No adapter requests saved yet.")
        return

    click.echo(f"Pending adapter requests ({len(data)}):")
    click.echo()
    for i, req in enumerate(data, 1):
        family = req.get("family") or "unspecified"
        desc = req.get("description", "")
        date = req.get("requested_at", "")[:10]  # ISO date portion
        click.echo(f"  {i}. [{family}] {desc}")
        if date:
            click.echo(f"     Requested: {date}")

    click.echo()
    click.echo("To submit to the community:")
    click.echo("  https://github.com/evolution-engine/evolution-engine/issues/new")
    click.echo("  Use the 'adapter-request' label")


@adapter.command("security-check")
@click.argument("target")
def adapter_security_check(target):
    """Run security scan on adapter source code.

    TARGET is a dotted module path (e.g. 'evo_jenkins') or a directory path.

    Example:
        evo adapter security-check evo_jenkins
        evo adapter security-check /path/to/evo-adapter-jenkins/
    """
    from evolution.adapter_security import scan_adapter_source

    report = scan_adapter_source(target)

    if report.error:
        click.echo(f"Error: {report.error}")
        sys.exit(1)

    click.echo(report.summary())
    click.echo()

    if report.passed:
        click.echo("No critical security issues found.")
    else:
        click.echo(f"{report.critical_count} critical issue(s) must be fixed.")
        sys.exit(1)


@adapter.command("block")
@click.argument("name")
@click.option("--reason", "-r", default="", help="Reason for blocking this adapter")
def adapter_block(name, reason):
    """Block an adapter from being detected.

    Adds the adapter to your local blocklist (~/.evo/blocklist.json).
    Blocked adapters are hidden from detection results.

    Example:
        evo adapter block bad-adapter -r "Known vulnerability"
    """
    from evolution.registry import AdapterRegistry

    if AdapterRegistry.block_adapter(name, reason=reason):
        click.echo(f"Blocked: {name}")
        if reason:
            click.echo(f"Reason: {reason}")
    else:
        click.echo(f"Already blocked: {name}")


@adapter.command("unblock")
@click.argument("name")
def adapter_unblock(name):
    """Unblock a previously blocked adapter.

    Removes the adapter from your local blocklist.

    Example:
        evo adapter unblock bad-adapter
    """
    from evolution.registry import AdapterRegistry

    if AdapterRegistry.unblock_adapter(name):
        click.echo(f"Unblocked: {name}")
    else:
        click.echo(f"Not found in blocklist: {name}")
        sys.exit(1)


@adapter.command("check-updates")
def adapter_check_updates():
    """Check for updates to installed adapter plugins.

    Queries PyPI for the latest versions of all installed adapter plugins
    and evolution-engine itself.

    Example:
        evo adapter check-updates
    """
    from importlib.metadata import entry_points as _eps

    from evolution.adapter_versions import check_pypi_version

    click.echo("Checking for updates...")
    click.echo()

    # Check evolution-engine itself
    from evolution import __version__ as current_version
    latest = check_pypi_version("evolution-engine", use_cache=False)
    if latest and latest != current_version:
        click.echo(f"  evolution-engine: {current_version} → {latest} (update available)")
    elif latest:
        click.echo(f"  evolution-engine: {current_version} (up to date)")
    else:
        click.echo(f"  evolution-engine: {current_version} (could not check)")

    # Check installed plugins
    try:
        eps = _eps(group="evo.adapters")
    except TypeError:
        eps = []

    if not eps:
        click.echo()
        click.echo("No adapter plugins installed.")
        return

    import importlib.metadata
    for ep in eps:
        try:
            current = importlib.metadata.version(ep.name)
        except Exception:
            current = "unknown"
        latest = check_pypi_version(ep.name, use_cache=False)
        if latest and latest != current:
            click.echo(f"  {ep.name}: {current} → {latest} (update available)")
        elif latest:
            click.echo(f"  {ep.name}: {current} (up to date)")
        else:
            click.echo(f"  {ep.name}: {current} (could not check)")


@adapter.command("report")
@click.argument("adapter_name")
@click.option("--category", "-c",
              type=click.Choice(["crashes", "wrong-data", "security-concern", "other"]),
              help="Report category (prompted if not provided)")
@click.option("--description", "-d", default="", help="Description of the issue")
def adapter_report(adapter_name, category, description):
    """Report a broken or malicious adapter.

    Saves a report locally with diagnostic information. If GITHUB_BOT_TOKEN
    is set, also files a GitHub issue with the adapter-report label.

    Example:
        evo adapter report evo-adapter-bad --category security-concern
        evo adapter report evo-adapter-bad -c crashes -d "Fails on Python 3.12"
    """
    import datetime

    if not category:
        category = click.prompt(
            "Category",
            type=click.Choice(["crashes", "wrong-data", "security-concern", "other"]),
        )

    if not description:
        description = click.prompt("Description", default="")

    report_data = {
        "adapter_name": adapter_name,
        "category": category,
        "description": description,
        "reported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evo_version": __version__,
        "python_version": sys.version,
    }

    # Save locally
    reports_dir = Path.home() / ".evo" / "adapter_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"{adapter_name}_{timestamp}.json"
    report_file.write_text(json.dumps(report_data, indent=2))

    click.echo(f"Report saved: {report_file}")

    # Try to file GitHub issue if token is available
    gh_token = os.environ.get("GITHUB_BOT_TOKEN")
    if gh_token:
        click.echo("Filing GitHub issue...")
        try:
            import urllib.request
            import urllib.error

            issue_data = json.dumps({
                "title": f"Adapter Report: {adapter_name} ({category})",
                "body": (f"**Adapter:** {adapter_name}\n"
                         f"**Category:** {category}\n"
                         f"**Description:** {description}\n"
                         f"**EE Version:** {report_data['evo_version']}\n"
                         f"**Python:** {report_data['python_version']}"),
                "labels": ["adapter-report"],
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.github.com/repos/evolution-engine/evolution-engine/issues",
                data=issue_data,
                headers={
                    "Authorization": f"token {gh_token}",
                    "Accept": "application/vnd.github+json",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                click.echo(f"Issue created: {result.get('html_url', 'unknown')}")
        except Exception as e:
            click.echo(f"Could not file GitHub issue: {e}")
            click.echo("Report saved locally — you can file it manually:")
            click.echo("  https://github.com/evolution-engine/evolution-engine/issues/new")
    else:
        click.echo()
        click.echo("To submit this report to the community:")
        click.echo("  https://github.com/evolution-engine/evolution-engine/issues/new")
        click.echo("  Use the 'adapter-report' label")


@adapter.command("discover")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def adapter_discover(path, json_output):
    """Discover adapters available for tools detected in your repo.

    Scans the repo for known tools (via prescan), then checks PyPI
    for matching adapter packages that aren't installed yet.

    Example:
        evo adapter discover .
    """
    import importlib.metadata
    from evolution.prescan import SourcePrescan
    from evolution.adapter_versions import check_pypi_version

    prescan = SourcePrescan(path)
    detected = prescan.scan()

    if not detected:
        click.echo("No external tools detected in this repo.")
        click.echo("Run `evo sources` for detailed prescan output.")
        return

    # Get installed adapter packages
    installed = set()
    eps = importlib.metadata.entry_points()
    if hasattr(eps, "select"):
        adapter_eps = eps.select(group="evo.adapters")
    else:
        adapter_eps = eps.get("evo.adapters", [])
    for ep in adapter_eps:
        if hasattr(ep, "dist") and ep.dist:
            installed.add(ep.dist.name)

    # Check each detected tool
    available = []
    already_installed = []
    not_published = []

    for svc in detected:
        pkg = svc.adapter
        if not pkg:
            continue

        if pkg in installed:
            already_installed.append(svc)
            continue

        latest = check_pypi_version(pkg, use_cache=True)
        if latest:
            available.append({"service": svc, "version": latest})
        else:
            not_published.append(svc)

    if json_output:
        click.echo(json.dumps({
            "available": [
                {"package": a["service"].adapter, "version": a["version"],
                 "tool": a["service"].display_name, "family": a["service"].family}
                for a in available
            ],
            "installed": [
                {"package": s.adapter, "tool": s.display_name, "family": s.family}
                for s in already_installed
            ],
            "not_published": [
                {"package": s.adapter, "tool": s.display_name, "family": s.family}
                for s in not_published
            ],
        }, indent=2))
        return

    if available:
        click.echo("Available adapters (install via pip):\n")
        for a in available:
            svc = a["service"]
            click.echo(f"  {svc.adapter:30s} v{a['version']:8s} "
                        f"← {svc.display_name} ({svc.family})")
        click.echo()
        if len(available) == 1:
            click.echo(f"  Install: pip install {available[0]['service'].adapter}")
        else:
            names = " ".join(a["service"].adapter for a in available)
            click.echo(f"  Install all: pip install {names}")

    if already_installed:
        click.echo()
        click.echo("Already installed:")
        for svc in already_installed:
            click.echo(f"  {svc.adapter:30s} ← {svc.display_name}")

    if not_published:
        click.echo()
        click.echo("Community adapters \u2014 request or build your own:")
        for svc in not_published:
            click.echo(f"  {svc.adapter:30s} ← {svc.display_name} ({svc.family})")
            click.echo(f"    Scaffold: evo adapter new {svc.service} --family {svc.family}")

    if not available and not not_published:
        click.echo("All detected tools already have adapters installed.")


@adapter.command("publish")
@click.argument("path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Run checks and build, but skip upload")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def adapter_publish(path, dry_run, yes):
    """Validate, build, and publish an adapter to PyPI.

    PATH is the adapter project directory (must contain pyproject.toml).

    Runs the full publish pipeline:
      1. Discover adapter class from entry points
      2. Validate against the Adapter Contract (16 checks)
      3. Security scan source code
      4. Check for version conflicts on PyPI
      5. Build wheel + sdist
      6. Upload to PyPI

    Example:
        evo adapter publish examples/evo-adapter-pytest-cov
        evo adapter publish . --dry-run
    """
    import subprocess
    from pathlib import Path as _Path

    project_dir = _Path(path).resolve()
    pyproject = project_dir / "pyproject.toml"

    # ── Step 0: Verify project structure ──
    if not pyproject.exists():
        click.echo(f"Error: No pyproject.toml found in {project_dir}")
        sys.exit(1)

    # Parse package name and version from pyproject.toml
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            click.echo("Error: Python 3.11+ or 'tomli' package required")
            sys.exit(1)

    with open(pyproject, "rb") as f:
        pyproject_data = tomllib.load(f)

    project_meta = pyproject_data.get("project", {})
    pkg_name = project_meta.get("name")
    pkg_version = project_meta.get("version")
    if not pkg_name or not pkg_version:
        click.echo("Error: pyproject.toml must have project.name and project.version")
        sys.exit(1)

    # Find the adapter entry point
    entry_points = pyproject_data.get("project", {}).get("entry-points", {})
    evo_adapters = entry_points.get("evo.adapters", {})
    if not evo_adapters:
        click.echo("Error: No [project.entry-points.\"evo.adapters\"] found")
        click.echo("  Adapters must register via entry points. See: evo adapter guide")
        sys.exit(1)

    # Resolve the adapter class from the register() function
    ep_name, ep_value = next(iter(evo_adapters.items()))
    # ep_value is "module:function" or "module.function"
    if ":" in ep_value:
        module_name, func_name = ep_value.split(":", 1)
    else:
        module_name = ep_value.rsplit(".", 1)[0]
        func_name = ep_value.rsplit(".", 1)[-1]

    click.echo(f"Publishing {pkg_name} v{pkg_version}")
    click.echo(f"  Module: {module_name}")
    click.echo()

    # ── Step 1: Validate adapter contract ──
    click.echo("[1/5] Validating adapter contract...")

    # Find the adapter class by loading the register() function
    old_sys_path = sys.path[:]
    sys.path.insert(0, str(project_dir))
    try:
        import importlib
        mod = importlib.import_module(module_name)
        register_fn = getattr(mod, func_name, None)
        if register_fn is None:
            click.echo(f"  Error: Could not find {func_name}() in {module_name}")
            sys.exit(1)
        reg_result = register_fn()
        # register() returns a list of dicts or a single dict
        if isinstance(reg_result, list):
            adapter_class_path = reg_result[0].get("adapter_class", "") if reg_result else ""
        elif isinstance(reg_result, dict):
            adapter_class_path = reg_result.get("adapter_class", "")
        else:
            adapter_class_path = ""
    finally:
        sys.path[:] = old_sys_path

    if not adapter_class_path:
        click.echo("  Error: register() did not return adapter_class")
        sys.exit(1)

    from evolution.adapter_validator import load_adapter_class, validate_adapter
    try:
        adapter_cls = load_adapter_class(adapter_class_path)
    except (ImportError, AttributeError) as e:
        click.echo(f"  Error loading adapter class: {e}")
        sys.exit(1)

    report = validate_adapter(adapter_cls)
    passed = sum(1 for c in report.checks if c.passed)
    total = len(report.checks)
    if report.passed:
        click.echo(f"  PASSED ({passed}/{total} checks)")
    else:
        click.echo(report.summary())
        click.echo(f"  FAILED — {len(report.errors)} error(s) must be fixed")
        sys.exit(1)

    # ── Step 2: Security scan ──
    click.echo("[2/5] Scanning for security issues...")
    from evolution.adapter_security import scan_adapter_source
    sec_report = scan_adapter_source(str(project_dir))
    if sec_report.passed:
        click.echo(f"  PASSED ({sec_report.files_scanned} files scanned, "
                    f"0 critical)")
    else:
        click.echo(sec_report.summary())
        click.echo("  FAILED — critical security issues found")
        sys.exit(1)

    # ── Step 3: Check PyPI for version conflict ──
    click.echo("[3/5] Checking PyPI for version conflicts...")
    from evolution.adapter_versions import check_pypi_version
    existing_version = check_pypi_version(pkg_name, use_cache=False)
    if existing_version:
        from packaging.version import Version
        try:
            if Version(pkg_version) <= Version(existing_version):
                click.echo(f"  CONFLICT — v{existing_version} already on PyPI, "
                           f"bump version above {existing_version}")
                sys.exit(1)
        except Exception:
            pass
        click.echo(f"  OK — upgrading from v{existing_version} to v{pkg_version}")
    else:
        click.echo(f"  OK — new package, first publish")

    # ── Step 4: Build ──
    click.echo("[4/5] Building wheel + sdist...")

    # Clean old dist/
    dist_dir = project_dir / "dist"
    if dist_dir.exists():
        import shutil
        shutil.rmtree(dist_dir)

    result = subprocess.run(
        [sys.executable, "-m", "build"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo("  Build FAILED:")
        click.echo(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        sys.exit(1)

    artifacts = list(dist_dir.glob("*"))
    click.echo(f"  Built {len(artifacts)} artifact(s):")
    for a in artifacts:
        click.echo(f"    {a.name}")

    # ── Step 5: Upload ──
    if dry_run:
        click.echo("[5/5] Upload SKIPPED (--dry-run)")
        click.echo()
        click.echo(f"Dry run complete. To publish for real:")
        click.echo(f"  evo adapter publish {path}")
        return

    click.echo("[5/5] Uploading to PyPI...")

    if not yes:
        click.confirm(f"  Upload {pkg_name} v{pkg_version} to PyPI?", abort=True)

    # Token from env
    twine_password = os.environ.get("TWINE_PASSWORD") or os.environ.get("PYPI_API_TOKEN")
    twine_env = os.environ.copy()
    if twine_password:
        twine_env["TWINE_USERNAME"] = "__token__"
        twine_env["TWINE_PASSWORD"] = twine_password

    # Find all dist files explicitly (avoid shell glob)
    dist_files = [str(f) for f in (project_dir / "dist").glob("*")]
    result = subprocess.run(
        [sys.executable, "-m", "twine", "upload"] + dist_files,
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        env=twine_env,
    )
    if result.returncode != 0:
        stderr = result.stderr
        if "403" in stderr:
            click.echo("  FAILED — authentication error. Set PYPI_API_TOKEN env var")
            click.echo("  or configure ~/.pypirc")
        else:
            click.echo("  Upload FAILED:")
            click.echo(stderr[-500:] if len(stderr) > 500 else stderr)
        sys.exit(1)

    click.echo(f"  Published!")
    click.echo()
    click.echo(f"  https://pypi.org/project/{pkg_name}/{pkg_version}/")
    click.echo()
    click.echo(f"Install: pip install {pkg_name}")


# ─────────────────── evo license ───────────────────


@main.group()
def license():
    """Manage Evolution Engine license."""
    pass


@license.command("status")
@click.option("--path", default=".", type=click.Path(exists=True), help="Repository path")
def license_status(path):
    """Show current license status."""
    from evolution.license import get_license

    lic = get_license(path)

    click.echo(f"License: {lic.tier.upper()}")
    click.echo(f"Status: {'Valid' if lic.valid else 'Invalid'}")
    click.echo(f"Source: {lic.source}")

    if lic.email:
        click.echo(f"Email: {lic.email}")
    if lic.issued:
        click.echo(f"Issued: {lic.issued}")
    if lic.expires:
        click.echo(f"Expires: {lic.expires}")

    click.echo()
    click.echo("Features:")
    for feature, enabled in lic.features.items():
        status = "✓" if enabled else "✗"
        click.echo(f"  {status} {feature}")

    if lic.tier == "free":
        click.echo()
        click.echo("Upgrade to Pro for:")
        click.echo("  - CI, deployment, and security adapters")
        click.echo("  - LLM-enhanced explanations and semantic patterns")
        click.echo("  - Community knowledge base sync (coming soon)")
        click.echo()
        click.echo("Set EVO_LICENSE_KEY or visit https://codequal.dev/pro")


@license.command("activate")
@click.argument("key")
def license_activate(key):
    """Save license key to ~/.evo/license.json."""
    from evolution.license import get_license

    # Test the key first
    os_env_backup = os.environ.get("EVO_LICENSE_KEY")
    os.environ["EVO_LICENSE_KEY"] = key
    lic = get_license()
    if os_env_backup:
        os.environ["EVO_LICENSE_KEY"] = os_env_backup
    else:
        os.environ.pop("EVO_LICENSE_KEY", None)

    if not lic.valid:
        click.echo("Error: Invalid license key")
        sys.exit(1)

    # Save to ~/.evo/license.json
    evo_home = Path.home() / ".evo"
    evo_home.mkdir(exist_ok=True)
    license_file = evo_home / "license.json"

    license_file.write_text(json.dumps({"license_key": key}, indent=2))
    click.echo(f"License activated: {lic.tier.upper()}")
    click.echo(f"Saved to {license_file}")


# ─────────────────── evo report ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output file (default: <evo-dir>/report.html)")
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--title", help="Custom report title")
@click.option("--open", "open_browser", is_flag=True, help="Open in browser after generating")
@click.option("--serve", is_flag=True, help="Start local server for interactive report (blocking)")
@click.option("--verify", is_flag=True, help="Include verification banner comparing last two runs")
def report(path, output, evo_dir, title, open_browser, serve, verify):
    """Generate an HTML report from the latest advisory."""
    from evolution.report_generator import generate_report

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"

    if not (evo_path / "phase5" / "advisory.json").exists():
        click.echo("No advisory found. Run `evo analyze` first.")
        sys.exit(1)

    # --verify: compare last two runs and persist verification.json
    if verify:
        try:
            from evolution.history import HistoryManager
            hm = HistoryManager(evo_path)
            runs = hm.list_runs(limit=2)
            if len(runs) >= 2:
                verify_diff = hm.compare(runs[1]["timestamp"], runs[0]["timestamp"])
                verify_path = evo_path / "phase5" / "verification.json"
                verify_path.write_text(json.dumps(verify_diff, default=str))
        except Exception:
            pass  # non-fatal — report renders without verification banner

    # Load calibration result if available
    cal = None
    cal_path = evo_path.parent / "calibration_result.json"
    if cal_path.exists():
        try:
            cal = json.loads(cal_path.read_text())
        except (json.JSONDecodeError, KeyError):
            pass

    html = generate_report(evo_path, title=title, calibration_result=cal)

    output_path = Path(output) if output else evo_path / "report.html"
    output_path.write_text(html)
    file_url = output_path.resolve().as_uri()  # proper file:///path
    # OSC 8 hyperlink: clickable in modern terminals (iTerm2, VS Code, etc.)
    click.echo(f"Report generated: \033]8;;{file_url}\033\\{output_path}\033]8;;\033\\")

    from evolution.telemetry import track_event
    track_event("cli_command", {"command": "report"})

    if serve:
        from evolution.report_server import ReportServer
        srv = ReportServer(evo_path, output_path)
        click.echo(f"Serving report at http://127.0.0.1:{srv.port} (Ctrl+C to stop)")
        srv.serve()
    elif open_browser:
        _open_report_with_server(evo_path, output_path)


# ─────────────────── evo verify ───────────────────


@main.command()
@click.argument("previous", type=click.Path(exists=True))
@click.option("--path", default=".", type=click.Path(exists=True), help="Repository path")
@click.option("--scope", "-s", help="Scope identifier")
@click.option("--quiet", "-q", is_flag=True, help="Suppress output, write verification JSON only")
def verify(previous, path, scope, quiet):
    """Compare current state against a previous advisory."""
    from evolution.phase5_engine import Phase5Engine

    evo_dir = Path(path) / ".evo"
    scope = scope or Path(path).resolve().name

    phase5 = Phase5Engine(evo_dir)
    result = phase5.verify(scope=scope, previous_advisory_path=previous)

    # Save verification JSON (always, for CI consumption)
    verification_path = Path(evo_dir) / "phase5" / "verification.json"
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verification_path.write_text(
        json.dumps(result.get("verification", {}), indent=2), encoding="utf-8"
    )

    if quiet:
        # Exit with code 0 if all resolved, 1 if issues remain
        v = result.get("verification", {})
        summary = v.get("summary", {})
        remaining = summary.get("persisting", 0) + summary.get("new", 0)
        sys.exit(1 if remaining > 0 else 0)

    if result["status"] == "verified":
        click.echo(result["verification_text"])

        verification = result.get("verification", {})
        summary = verification.get("summary", {})
        total_before = summary.get("total_before", 0)
        resolved_count = summary.get("resolved", 0)
        persisting_count = summary.get("persisting", 0)
        new_count = summary.get("new", 0)
        remaining = persisting_count + new_count

        if remaining > 0 and total_before > 0:
            # Calculate and display resolution progress
            pct = int(resolved_count / total_before * 100)
            click.echo(f"\nResolved: {resolved_count} of {total_before} ({pct}%)")

            # Build and save residual prompt
            from evolution.fixer import Fixer
            fixer = Fixer(repo_path=path, evo_dir=evo_dir)
            current_advisory = result.get("advisory", {})
            previous_advisory = phase5._load_previous_advisory(
                Path(previous)
            )
            investigation_text = _load_investigation_text(evo_dir)
            prompt = fixer._build_residual_prompt(
                current_advisory, previous_advisory, investigation_text,
            )
            residual_path = Path(evo_dir) / "phase5" / "residual_prompt.txt"
            residual_path.parent.mkdir(parents=True, exist_ok=True)
            residual_path.write_text(prompt, encoding="utf-8")

            click.echo(f"Residual prompt saved to {residual_path}")
            click.echo("Copy to your AI tool to continue fixing.")
        elif total_before > 0:
            click.echo("\nAll findings resolved — no residual prompt needed.")
    else:
        click.echo(f"Status: {result['status']}")
        click.echo(result.get("message", ""))


def _load_investigation_text(evo_dir: Path) -> str:
    """Load investigation text from .evo/investigation/ if available."""
    inv_path = evo_dir / "investigation" / "investigation.txt"
    if inv_path.exists():
        return inv_path.read_text(encoding="utf-8")
    return "(no investigation report available)"


# ─────────────────── evo config ───────────────────


@main.group()
def config():
    """Manage Evolution Engine settings."""
    pass


@config.command("list")
@click.option("--flat", is_flag=True, help="Show flat key=value format (legacy)")
def config_list(flat):
    """Show all configuration settings grouped by category."""
    from evolution.config import EvoConfig, config_groups, config_keys_for_group, config_metadata

    cfg = EvoConfig()
    overrides = cfg.user_overrides()

    click.echo(f"Config file: {cfg.path}")

    if flat:
        click.echo()
        for key, value in sorted(cfg.all().items()):
            marker = " *" if key in overrides else ""
            click.echo(f"  {key} = {value}{marker}")
        click.echo()
        click.echo("  (* = user override, all others are defaults)")
        return

    # Grouped display
    groups = config_groups()
    for group_key, group_info in groups.items():
        keys = config_keys_for_group(group_key)
        if not keys:
            continue
        click.echo()
        click.echo(f"  {group_info['label']}")
        for key in keys:
            meta = config_metadata(key)
            value = cfg.get(key)
            marker = " *" if key in overrides else ""
            desc = meta.get("description", "")
            labels = meta.get("allowed_labels", {})
            display_val = labels.get(value, value) if labels else value
            click.echo(f"    {key} = {display_val}{marker}")
            if desc:
                click.echo(f"      {desc}")
    click.echo()
    click.echo("  (* = user override)")
    click.echo("  Run `evo config set <key> <value>` to change a setting.")
    click.echo("  Run `evo setup --ui` to edit in browser.")


@config.command("get")
@click.argument("key")
def config_get(key):
    """Get a configuration value."""
    from evolution.config import EvoConfig

    cfg = EvoConfig()
    value = cfg.get(key)
    if value is None:
        click.echo(f"Unknown key: {key}")
        sys.exit(1)
    click.echo(value)


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a configuration value."""
    from evolution.config import EvoConfig, _parse_value

    cfg = EvoConfig()
    parsed = _parse_value(value)
    cfg.set(key, parsed)
    click.echo(f"{key} = {parsed}")


@config.command("reset")
@click.argument("key")
def config_reset(key):
    """Reset a configuration value to its default."""
    from evolution.config import EvoConfig

    cfg = EvoConfig()
    if cfg.delete(key):
        click.echo(f"Reset {key} to default")
    else:
        click.echo(f"{key} was already at default")


# ─────────────────── evo setup ───────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--reset", is_flag=True, help="Reset all settings to defaults first")
@click.option("--ui", is_flag=True, help="Open browser-based settings page")
@click.option("--port", default=8484, type=int, help="Port for --ui server (default: 8484)")
def setup(path, reset, ui, port):
    """Smart setup wizard — auto-detects sources, checks tokens, asks key preferences.

    Use --ui to open a browser-based settings page instead.

    Examples:
        evo setup .
        evo setup . --reset
        evo setup --ui
        evo setup --ui --port 9090
    """
    from evolution.config import EvoConfig, config_groups, config_keys_for_group, config_metadata, _parse_value

    cfg = EvoConfig()

    if ui:
        from evolution.setup_ui import SetupUI
        click.echo(f"Opening settings in browser on http://localhost:{port} ...")
        setup_ui = SetupUI(port=port, config=cfg)
        setup_ui.serve()
        click.echo("Settings saved.")
        return

    if reset:
        if click.confirm("Reset all settings to defaults?"):
            for key in list(cfg.user_overrides()):
                cfg.delete(key)
            click.echo("Settings reset to defaults.\n")

    click.echo("Evolution Engine Setup")
    click.echo("=" * 40)

    # ── Step 1: Auto-detect sources ──
    click.echo("\nDetecting signal sources...")
    try:
        from evolution.prescan import SourcePrescan
        prescan = SourcePrescan(path)
        detected = prescan.scan()
        if detected:
            for svc in detected:
                click.echo(f"  \u2713 {svc.display_name} ({svc.family})")
            click.echo("  Run 'evo sources' to see how connecting these tools enriches analysis")
        else:
            click.echo("  No additional sources detected (git is always available)")
    except Exception:
        click.echo("  (prescan skipped)")

    # ── Step 2: Check for GitHub token ──
    changed = 0
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not github_token:
        click.echo("\nNo GITHUB_TOKEN found in environment.")
        try:
            raw = click.prompt(
                "  GitHub token (for CI/deployment data, or Enter to skip)",
                default="", show_default=False,
            ).strip()
            if raw:
                os.environ["GITHUB_TOKEN"] = raw
                click.echo("  \u2713 Token set for this session")
                click.echo("  To persist: export GITHUB_TOKEN=<token> in your shell profile")
        except (EOFError, click.Abort):
            pass
    else:
        click.echo(f"\n  \u2713 GITHUB_TOKEN detected")

    # ── Step 3: Key preferences only ──
    click.echo("\nPreferences (Enter to keep default):\n")

    # Privacy level
    meta = config_metadata("sync.privacy_level")
    current = cfg.get("sync.privacy_level")
    labels = meta.get("allowed_labels", {})
    allowed = meta.get("allowed", [0, 1])
    click.echo("  Community pattern sharing:")
    for opt in allowed:
        label = labels.get(opt, str(opt))
        marker = " <-" if opt == current else ""
        click.echo(f"    {opt}. {label}{marker}")
    try:
        raw = click.prompt("  Choice", default="", show_default=False).strip()
        if raw and raw.isdigit():
            value = int(raw)
            if value in allowed and value != current:
                cfg.set("sync.privacy_level", value)
                changed += 1
    except (EOFError, click.Abort):
        pass

    # Auto-open report
    current_open = cfg.get("hooks.auto_open")
    try:
        raw = click.prompt(
            f"\n  Auto-open HTML report after analysis? [{'yes' if current_open else 'no'}]",
            default="", show_default=False,
        ).strip()
        if raw:
            value = raw.lower() in ("true", "yes", "y", "1")
            if value != current_open:
                cfg.set("hooks.auto_open", value)
                changed += 1
    except (EOFError, click.Abort):
        pass

    click.echo(f"\nSetup complete. {changed} setting(s) changed.")
    click.echo(f"Config: {cfg.path}")
    click.echo("\nRun `evo analyze .` to start, or `evo config list` to see all settings.")


# ─────────────────── evo hooks ───────────────────


@main.group()
def hooks():
    """Manage git hook integration."""
    pass


@hooks.command("install")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--trigger", type=click.Choice(["post-commit", "pre-push"]),
              help="Hook trigger (default: from config)")
def hooks_install(path, trigger):
    """Install EE git hook for automatic analysis. [Pro]

    The hook runs `evo analyze` after each commit (or before push)
    and notifies you when findings exceed your configured threshold.

    Examples:
        evo hooks install .
        evo hooks install . --trigger pre-push
    """
    from evolution.license import ProFeatureError, require_pro

    try:
        require_pro("Git Hooks", repo_path=path)
    except ProFeatureError as e:
        click.echo(str(e))
        sys.exit(1)

    from evolution.hooks import HookManager

    hm = HookManager(path)
    result = hm.install(trigger=trigger)

    if result["ok"]:
        click.echo(f"Hook installed: {result['hook_path']}")
        click.echo(f"Trigger: {result['trigger']}")
        status = hm.status()
        click.echo(f"Threshold: {status['config']['min_severity']}")
        click.echo()
        click.echo("EE will now analyze your code automatically.")
        click.echo("Configure with: evo config set hooks.<key> <value>")
        # Notification setup hint (macOS needs terminal-notifier + permission)
        if status["config"].get("notify") and sys.platform == "darwin":
            import shutil
            if not shutil.which("terminal-notifier"):
                click.echo()
                click.echo("Tip: For desktop notifications on macOS, install terminal-notifier:")
                click.echo("  brew install terminal-notifier")
                click.echo("  Then enable notifications in System Settings > Notifications.")
            else:
                click.echo()
                click.echo("Tip: Ensure notifications are enabled for terminal-notifier")
                click.echo("  in System Settings > Notifications.")
    else:
        click.echo(f"Error: {result.get('error', 'unknown')}")
        sys.exit(1)


@hooks.command("uninstall")
@click.argument("path", default=".", type=click.Path(exists=True))
def hooks_uninstall(path):
    """Remove EE git hooks."""
    from evolution.hooks import HookManager

    hm = HookManager(path)
    result = hm.uninstall()

    if result["ok"]:
        removed = result.get("removed", [])
        if removed:
            for r in removed:
                click.echo(f"Removed: {r}")
        else:
            click.echo("No EE hooks found.")
    else:
        click.echo(f"Error: {result.get('error', 'unknown')}")
        sys.exit(1)


@hooks.command("status")
@click.argument("path", default=".", type=click.Path(exists=True))
def hooks_status(path):
    """Show git hook status."""
    from evolution.hooks import HookManager

    hm = HookManager(path)
    s = hm.status()

    if s["installed"]:
        click.echo(f"Hook: installed")
        click.echo(f"Trigger: {s['trigger']}")
        click.echo(f"Path: {s['hook_path']}")
    else:
        click.echo("Hook: not installed")
        click.echo("Run `evo hooks install .` to enable automatic analysis.")

    cfg = s["config"]
    click.echo()
    click.echo("Configuration:")
    click.echo(f"  Trigger: {cfg['trigger']}")
    click.echo(f"  Threshold: {cfg['min_severity']}")
    click.echo(f"  Background: {cfg['background']}")
    click.echo(f"  Notify: {cfg['notify']}")
    click.echo(f"  Auto-open: {cfg['auto_open']}")


# ─────────────────── evo init ───────────────────


@main.command("init")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--path", "integration_path",
              type=click.Choice(["cli", "hooks", "action", "all"]),
              help="Integration path to set up")
@click.option("--families", "-f", default="", help="Comma-separated family filter")
@click.option("--license-key", help="License key for GitHub Action workflow")
def init(path, evo_dir, integration_path, families, license_key):
    """Initialize Evolution Engine for this project.

    Detects your environment and sets up the right integration:
      cli    — manual analysis with evo analyze / evo report
      hooks  — auto-analyze on commit or push
      action — GitHub Action with PR comments
      all    — everything above

    Without --path, shows environment info and suggests a path.

    Examples:
        evo init .                       # detect and suggest
        evo init . --path hooks          # install git hooks
        evo init . --path action         # generate GitHub Action workflow
        evo init . --path all            # set up everything
    """
    from evolution.init import ProjectInit

    evo_path = Path(evo_dir) if evo_dir else None
    pi = ProjectInit(repo_path=path, evo_dir=evo_path)
    env = pi.detect_environment()

    if not integration_path:
        # Show environment info and suggestion
        click.echo("Evolution Engine — Project Init\n")
        click.echo(f"  Git repo:       {'yes' if env['is_git_repo'] else 'no'}")
        click.echo(f"  GitHub:         {'yes' if env['has_github'] else 'no'}")
        click.echo(f"  Workflows:      {'yes' if env['has_workflows'] else 'no'}")
        click.echo(f"  GitLab CI:      {'yes' if env.get('has_gitlab') else 'no'}")
        click.echo(f"  EE configured:  {'yes' if env['has_evo'] else 'no'}")
        click.echo(f"  EE in CI:       {'yes' if env['has_evo_action'] or env.get('has_evo_gitlab') else 'no'}")
        if env.get("repo_name"):
            click.echo(f"  Repository:     {env['repo_name']}")
        click.echo()
        suggested = env.get("suggested_path", "cli")
        ci_label = (
            "GitLab CI with MR comments"
            if env.get("ci_provider") == "gitlab"
            else "GitHub Action with PR comments"
        )
        paths = [
            ("cli", "Manual analysis with evo analyze / evo report"),
            ("hooks", "Auto-analyze on every commit"),
            ("action", ci_label),
            ("all", "All of the above"),
        ]
        click.echo("Available paths:")
        for i, (name, desc) in enumerate(paths, 1):
            marker = " <-- suggested" if name == suggested else ""
            click.echo(f"  {i}. {name:8s} — {desc}{marker}")

        click.echo()
        choice = click.prompt(
            "Choose a path (1-4, or Enter for suggested)",
            default=str([n for n, _ in paths].index(suggested) + 1),
            show_default=False,
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(paths):
                integration_path = paths[idx][0]
            else:
                click.echo("Invalid choice.")
                return
        except ValueError:
            click.echo("Invalid choice.")
            return

    # Gate Pro-only integration paths
    if integration_path in ("hooks", "action", "all"):
        from evolution.license import ProFeatureError, require_pro

        feature_labels = {
            "hooks": "Git Hooks",
            "action": "CI Integration",
            "all": "CI Integration & Git Hooks",
        }
        try:
            require_pro(feature_labels[integration_path], repo_path=path)
        except ProFeatureError as e:
            click.echo(str(e))
            sys.exit(1)

    result = pi.setup(integration_path, families=families)

    if not result["ok"]:
        click.echo(f"Error: {result['error']}")
        sys.exit(1)

    click.echo(f"Integration path: {integration_path}")
    for action in result.get("actions", []):
        click.echo(f"  {action}")

    # If action path, remind user to commit the workflow
    if integration_path in ("action", "all"):
        if env.get("ci_provider") == "gitlab":
            click.echo("\nCommit and push .gitlab-ci.yml to activate.")
            click.echo("Set GITLAB_TOKEN in CI/CD variables (Settings > CI/CD > Variables).")
        else:
            click.echo("\nCommit and push the workflow file to activate.")

    # Show first-run hint
    hint = pi.first_run_hint()
    if hint:
        click.echo(f"\n{hint}")

    from evolution.telemetry import track_event
    track_event("cli_command", {
        "command": "init",
        "path": integration_path,
    })


# ─────────────────── evo watch ───────────────────


@main.command("watch")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--evo-dir", help="Override .evo directory path")
@click.option("--interval", default=10, type=int, help="Polling interval in seconds (default: 10)")
@click.option("--min-severity",
              type=click.Choice(["critical", "concern", "watch", "info"]),
              default="concern", help="Minimum severity for alerts (default: concern)")
@click.option("--daemon", "-d", is_flag=True, help="Run in background as a daemon")
@click.option("--stop", is_flag=True, help="Stop the background daemon")
@click.option("--status", "show_status", is_flag=True, help="Show daemon status")
def watch(path, evo_dir, interval, min_severity, daemon, stop, show_status):
    """Watch for new commits and auto-analyze. [Pro]

    In foreground mode, polls for new commits and runs analysis when
    changes are detected. Use --daemon to run in the background.

    Examples:
        evo watch .                      # foreground — Ctrl+C to stop
        evo watch . --interval 30        # check every 30 seconds
        evo watch . --daemon             # background daemon
        evo watch . --stop               # stop the daemon
        evo watch . --status             # check if daemon is running
    """
    from evolution.license import ProFeatureError, require_pro

    try:
        require_pro("Commit Watcher", repo_path=path)
    except ProFeatureError as e:
        click.echo(str(e))
        sys.exit(1)

    from evolution.watcher import CommitWatcher

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"

    if show_status:
        info = CommitWatcher.daemon_status(path, evo_dir=str(evo_path))
        if info["running"]:
            click.echo(f"Watcher running (PID {info['pid']})")
        else:
            click.echo("Watcher not running.")
        return

    if stop:
        result = CommitWatcher.stop_daemon(path, evo_dir=str(evo_path))
        if result["ok"]:
            click.echo(f"Watcher stopped (PID {result.get('pid', '?')}).")
        else:
            click.echo(result.get("error", "Could not stop watcher."))
        return

    watcher = CommitWatcher(
        repo_path=path,
        evo_dir=str(evo_path),
        interval=interval,
        min_severity=min_severity,
    )

    if daemon:
        result = watcher.start_daemon()
        if result.get("ok"):
            click.echo(f"Watcher started in background (PID {result['pid']}).")
            click.echo(f"Log: {result.get('log_path', evo_path / 'watch.log')}")
            click.echo("Stop with: evo watch . --stop")
        else:
            click.echo(f"Error: {result.get('error', 'unknown')}")
            sys.exit(1)
        return

    click.echo(f"Watching {Path(path).resolve()} for new commits...")
    click.echo(f"Interval: {interval}s | Threshold: {min_severity}")
    click.echo("Press Ctrl+C to stop.\n")

    try:
        stats = watcher.run()
        click.echo(f"\nWatcher stopped. Commits analyzed: {stats.get('commits_analyzed', 0)}")
    except KeyboardInterrupt:
        click.echo("\nWatcher stopped.")

    from evolution.telemetry import track_event
    track_event("cli_command", {
        "command": "watch",
        "mode": "daemon" if daemon else "foreground",
    })


# ─────────────────── evo patterns pull/push ───────────────────


@patterns.command("pull")
@click.argument("path", default=".", type=click.Path(exists=True))
def patterns_pull(path):
    """Fetch community patterns from the remote registry.

    Downloads new patterns and imports them through the security
    validation pipeline. Safe to run at any time.
    """
    from evolution.kb_sync import KBSync

    evo_dir = Path(path) / ".evo"
    sync = KBSync(evo_dir=evo_dir)

    click.echo(f"Pulling from {sync.registry_url}...")
    result = sync.pull()

    if not result.success:
        click.echo(f"Error: {result.error}")
        sys.exit(1)

    click.echo(f"  New patterns: {result.pulled}")
    click.echo(f"  Already present: {result.skipped}")
    if result.rejected:
        click.echo(f"  Rejected (security): {result.rejected}")


@patterns.command("push")
@click.argument("path", default=".", type=click.Path(exists=True))
def patterns_push(path):
    """Share anonymized patterns with the community registry.

    Requires sync.privacy_level >= 1. Configure with:
        evo config set sync.privacy_level 1
    """
    from evolution.kb_sync import KBSync

    evo_dir = Path(path) / ".evo"
    sync = KBSync(evo_dir=evo_dir)

    if sync.privacy_level < 1:
        click.echo("Sharing is disabled (privacy_level=0).")
        click.echo()
        click.echo("To enable:")
        click.echo("  evo config set sync.privacy_level 1")
        sys.exit(1)

    click.echo(f"Pushing to {sync.registry_url} (level {sync.privacy_level})...")
    result = sync.push()

    if not result.success:
        click.echo(f"Error: {result.error}")
        sys.exit(1)

    click.echo(f"  Patterns shared: {result.pushed}")


@patterns.command("new")
@click.argument("name")
@click.option("--description", "-d", default="", help="Package description")
@click.option("--output", "-o", default=".", help="Output directory")
def patterns_new(name, description, output):
    """Scaffold a new pattern package.

    Creates a pip-installable package skeleton at evo-patterns-<NAME>/.

    Example:
        evo patterns new web-security
        evo patterns new ci-metrics -d "CI metric patterns"
    """
    from evolution.pattern_scaffold import scaffold_pattern_pack

    result = scaffold_pattern_pack(name, description=description, output_dir=output)
    click.echo(f"Created pattern package: {result['package_name']}")
    click.echo(f"  Path: {result['path']}")
    click.echo(f"  Module: {result['module_name']}")
    click.echo(f"  Files: {len(result['files_created'])}")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  1. Edit {result['module_name']}/patterns.json with your patterns")
    click.echo(f"  2. Validate: evo patterns validate {result['path']}")
    click.echo(f"  3. Publish: evo patterns publish {result['path']}")


@patterns.command("validate")
@click.argument("path", type=click.Path(exists=True))
def patterns_validate(path):
    """Validate a pattern package.

    PATH is the pattern package directory (must contain a module with patterns.json).

    Example:
        evo patterns validate examples/evo-patterns-example
        evo patterns validate .
    """
    from evolution.pattern_validator import validate_pattern_package

    project_dir = Path(path).resolve()

    # Find patterns.json: check for evo_patterns_*/patterns.json
    patterns_file = None
    for subdir in project_dir.iterdir():
        if subdir.is_dir() and subdir.name.startswith("evo_patterns_"):
            candidate = subdir / "patterns.json"
            if candidate.exists():
                patterns_file = candidate
                break

    # Also check root patterns.json
    if not patterns_file:
        root_pj = project_dir / "patterns.json"
        if root_pj.exists():
            patterns_file = root_pj

    if not patterns_file:
        click.echo(f"Error: No patterns.json found in {project_dir}")
        click.echo("  Expected: evo_patterns_<name>/patterns.json")
        sys.exit(1)

    try:
        patterns_data = json.loads(patterns_file.read_text())
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in {patterns_file}: {e}")
        sys.exit(1)

    # Determine package name from pyproject.toml or directory name
    pkg_name = project_dir.name
    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                tomllib = None
        if tomllib:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            pkg_name = data.get("project", {}).get("name", pkg_name)

    report = validate_pattern_package(patterns_data, package_name=pkg_name)
    click.echo(report.summary())

    if not report.passed:
        sys.exit(1)


@patterns.command("packages")
def patterns_packages():
    """List known pattern packages and their cache status.

    Shows bundled and user-added pattern packages with version info.
    """
    from evolution.pattern_registry import list_pattern_packages

    packages = list_pattern_packages()
    if not packages:
        click.echo("No pattern packages configured.")
        click.echo("  Add one with: evo patterns add <package-name>")
        return

    click.echo("Pattern Packages:")
    for pkg in packages:
        status_parts = []
        if pkg["blocked"]:
            status_parts.append("BLOCKED")
        elif pkg["cached_version"]:
            status_parts.append(f"v{pkg['cached_version']}")
            status_parts.append(f"{pkg['pattern_count']} patterns")
            if pkg["families"]:
                status_parts.append(f"families: {', '.join(pkg['families'])}")
        else:
            status_parts.append("not cached")

        source_tag = f"[{pkg['source']}]"
        click.echo(f"  {pkg['name']} {source_tag} — {', '.join(status_parts)}")


@patterns.command("publish")
@click.argument("path", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Run checks and build, but skip upload")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def patterns_publish(path, dry_run, yes):
    """Validate, build, and publish a pattern package to PyPI.

    PATH is the pattern package directory (must contain pyproject.toml).

    Example:
        evo patterns publish examples/evo-patterns-example
        evo patterns publish . --dry-run
    """
    import subprocess

    project_dir = Path(path).resolve()
    pyproject = project_dir / "pyproject.toml"

    if not pyproject.exists():
        click.echo(f"Error: No pyproject.toml found in {project_dir}")
        sys.exit(1)

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            click.echo("Error: Python 3.11+ or 'tomli' package required")
            sys.exit(1)

    with open(pyproject, "rb") as f:
        pyproject_data = tomllib.load(f)

    project_meta = pyproject_data.get("project", {})
    pkg_name = project_meta.get("name")
    pkg_version = project_meta.get("version")
    if not pkg_name or not pkg_version:
        click.echo("Error: pyproject.toml must have project.name and project.version")
        sys.exit(1)

    click.echo(f"Publishing {pkg_name} v{pkg_version}")

    # Step 1: Validate patterns
    click.echo("\n[1/4] Validating patterns...")
    from evolution.pattern_validator import validate_pattern_package

    patterns_file = None
    for subdir in project_dir.iterdir():
        if subdir.is_dir() and subdir.name.startswith("evo_patterns_"):
            candidate = subdir / "patterns.json"
            if candidate.exists():
                patterns_file = candidate
                break

    if not patterns_file:
        click.echo("  Error: No patterns.json found")
        sys.exit(1)

    patterns_data = json.loads(patterns_file.read_text())
    report = validate_pattern_package(patterns_data, package_name=pkg_name)
    if report.passed:
        passed = sum(1 for c in report.checks if c.passed)
        click.echo(f"  PASSED ({passed}/{len(report.checks)} checks)")
    else:
        click.echo(report.summary())
        sys.exit(1)

    # Step 2: Check PyPI for version conflict
    click.echo("[2/4] Checking PyPI for version conflicts...")
    from evolution.adapter_versions import check_pypi_version
    existing_version = check_pypi_version(pkg_name, use_cache=False)
    if existing_version:
        from packaging.version import Version
        try:
            if Version(pkg_version) <= Version(existing_version):
                click.echo(f"  CONFLICT — v{existing_version} already on PyPI, "
                           f"bump version above {existing_version}")
                sys.exit(1)
        except Exception:
            pass
        click.echo(f"  OK — upgrading from v{existing_version} to v{pkg_version}")
    else:
        click.echo(f"  OK — new package, first publish")

    # Step 3: Build
    click.echo("[3/4] Building wheel + sdist...")
    import shutil

    dist_dir = project_dir / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    result = subprocess.run(
        [sys.executable, "-m", "build"],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo("  Build FAILED:")
        click.echo(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        sys.exit(1)

    artifacts = list(dist_dir.glob("*"))
    click.echo(f"  Built {len(artifacts)} artifact(s)")

    # Step 4: Upload
    if dry_run:
        click.echo("[4/4] Upload SKIPPED (--dry-run)")
        click.echo(f"\nDry run complete. To publish: evo patterns publish {path}")
        return

    click.echo("[4/4] Uploading to PyPI...")
    if not yes:
        click.confirm(f"  Upload {pkg_name} v{pkg_version} to PyPI?", abort=True)

    twine_password = os.environ.get("TWINE_PASSWORD") or os.environ.get("PYPI_API_TOKEN")
    twine_env = os.environ.copy()
    if twine_password:
        twine_env["TWINE_USERNAME"] = "__token__"
        twine_env["TWINE_PASSWORD"] = twine_password

    dist_files = [str(f) for f in (project_dir / "dist").glob("*")]
    result = subprocess.run(
        [sys.executable, "-m", "twine", "upload"] + dist_files,
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        env=twine_env,
    )
    if result.returncode != 0:
        click.echo("  Upload FAILED:")
        click.echo(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        sys.exit(1)

    click.echo(f"  Published {pkg_name} v{pkg_version} to PyPI")


@patterns.command("add")
@click.argument("package")
def patterns_add(package):
    """Add a pattern package to your sources.

    The package will be auto-fetched on the next `evo analyze`.

    Example:
        evo patterns add evo-patterns-web-security
    """
    from evolution.pattern_registry import add_pattern_source

    if add_pattern_source(package):
        click.echo(f"Added {package} to pattern sources")
        click.echo("  Patterns will be auto-fetched on next `evo analyze`")
    else:
        click.echo(f"{package} is already in pattern sources")


@patterns.command("remove")
@click.argument("package")
def patterns_remove(package):
    """Remove a pattern package from your sources.

    Example:
        evo patterns remove evo-patterns-web-security
    """
    from evolution.pattern_registry import remove_pattern_source

    if remove_pattern_source(package):
        click.echo(f"Removed {package} from pattern sources")
    else:
        click.echo(f"{package} not found in pattern sources")


@patterns.command("block")
@click.argument("name")
@click.option("--reason", "-r", default="", help="Reason for blocking")
def patterns_block(name, reason):
    """Block a pattern package.

    Blocked packages are skipped during auto-fetch.

    Example:
        evo patterns block bad-patterns --reason "malicious"
    """
    from evolution.pattern_registry import block_pattern_package

    if block_pattern_package(name, reason=reason):
        click.echo(f"Blocked pattern package: {name}")
        if reason:
            click.echo(f"  Reason: {reason}")
    else:
        click.echo(f"{name} is already blocked")


@patterns.command("unblock")
@click.argument("name")
def patterns_unblock(name):
    """Unblock a pattern package.

    Example:
        evo patterns unblock previously-blocked-pkg
    """
    from evolution.pattern_registry import unblock_pattern_package

    if unblock_pattern_package(name):
        click.echo(f"Unblocked pattern package: {name}")
    else:
        click.echo(f"{name} is not blocked")


# ─────────────────── evo telemetry ───────────────────


@main.group()
def telemetry():
    """Manage anonymous usage telemetry."""
    pass


@telemetry.command("on")
def telemetry_on():
    """Enable anonymous usage telemetry."""
    from evolution.config import EvoConfig

    cfg = EvoConfig()
    cfg.set("telemetry.enabled", True)
    cfg.set("telemetry.prompted", True)
    click.echo("Telemetry enabled. Anonymous usage stats will be collected.")
    click.echo("Disable anytime with: evo telemetry off")


@telemetry.command("off")
def telemetry_off():
    """Disable anonymous usage telemetry."""
    from evolution.config import EvoConfig

    cfg = EvoConfig()
    cfg.set("telemetry.enabled", False)
    cfg.set("telemetry.prompted", True)
    click.echo("Telemetry disabled. No usage stats will be collected.")


@telemetry.command("status")
def telemetry_status():
    """Show current telemetry status."""
    from evolution.config import EvoConfig

    cfg = EvoConfig()
    enabled = cfg.get("telemetry.enabled", False)
    click.echo(f"Telemetry: {'enabled' if enabled else 'disabled'}")
    if enabled:
        click.echo("Anonymous usage stats are being collected.")
        click.echo("Disable with: evo telemetry off")
    else:
        click.echo("No usage stats are collected.")
        click.echo("Enable with: evo telemetry on")


# ─────────────────── evo history ───────────────────


@main.group(invoke_without_command=True)
@click.pass_context
def history(ctx):
    """View and compare analysis run history."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(history_list)


@history.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("-n", "--limit", type=int, default=None, help="Max runs to show")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def history_list(path, limit, json_output):
    """List advisory snapshots, newest first."""
    from evolution.history import HistoryManager

    evo_dir = Path(path) / ".evo"
    hm = HistoryManager(evo_dir)
    runs = hm.list_runs(limit=limit)

    if json_output:
        click.echo(json.dumps(runs, indent=2))
        return

    if not runs:
        click.echo("No run history found. Run `evo analyze` to create snapshots.")
        return

    click.echo(f"Run history ({len(runs)} snapshot{'s' if len(runs) != 1 else ''}):\n")
    for r in runs:
        families = ", ".join(r["families"]) if r["families"] else "none"
        click.echo(f"  {r['timestamp']}  {r['changes_count']} changes  [{families}]"
                    f"  scope={r['scope']}")


@history.command("show")
@click.argument("run")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def history_show(run, path, json_output):
    """View a specific run's advisory (supports prefix match)."""
    from evolution.history import HistoryManager

    evo_dir = Path(path) / ".evo"
    hm = HistoryManager(evo_dir)

    try:
        snapshot = hm.load_run(run)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if json_output:
        click.echo(json.dumps(snapshot, indent=2))
        return

    advisory = snapshot.get("advisory", {})
    click.echo(f"Snapshot: {snapshot.get('timestamp')}")
    click.echo(f"Scope:    {snapshot.get('scope')}")
    click.echo(f"Saved:    {snapshot.get('saved_at')}")
    click.echo()

    changes = advisory.get("changes", [])
    if not changes:
        click.echo("No significant changes in this run.")
        return

    click.echo(f"{len(changes)} significant change(s):\n")
    for c in changes:
        dev = c.get("deviation_stddev", 0)
        click.echo(f"  {c['family']} / {c['metric']}  "
                    f"deviation={dev:.1f}  observed={c.get('observed', '?')}")


@history.command("diff")
@click.argument("r1", default=None, required=False)
@click.argument("r2", default=None, required=False)
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def history_diff(r1, r2, path, json_output):
    """Compare two runs (default: latest vs previous)."""
    from evolution.history import HistoryManager

    evo_dir = Path(path) / ".evo"
    hm = HistoryManager(evo_dir)

    if r1 is None or r2 is None:
        runs = hm.list_runs(limit=2)
        if len(runs) < 2:
            click.echo("Need at least 2 runs to compare. "
                        "Run `evo analyze` again to create another snapshot.")
            sys.exit(1)
        # Default: compare previous (before) vs latest (after)
        r1 = r1 or runs[1]["timestamp"]  # older = before
        r2 = r2 or runs[0]["timestamp"]  # newer = after

    try:
        diff = hm.compare(r1, r2)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if json_output:
        # Remove summary_text for clean JSON
        out = {k: v for k, v in diff.items() if k != "summary_text"}
        click.echo(json.dumps(out, indent=2))
        return

    click.echo(diff["summary_text"])


@history.command("clean")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("-k", "--keep", type=int, default=None,
              help="Keep the N most recent snapshots")
@click.option("--before", type=str, default=None,
              help="Delete snapshots before this timestamp")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--json", "json_output", is_flag=True, help="Output JSON")
def history_clean(path, keep, before, yes, json_output):
    """Delete old snapshots."""
    from evolution.history import HistoryManager

    evo_dir = Path(path) / ".evo"
    hm = HistoryManager(evo_dir)

    if keep is None and before is None:
        click.echo("Specify --keep N or --before TIMESTAMP.")
        sys.exit(1)

    # Preview what would be deleted
    runs = hm.list_runs()
    if keep is not None:
        to_delete = len(runs) - keep if len(runs) > keep else 0
    else:
        to_delete = sum(1 for r in runs if r["timestamp"] < before)

    if to_delete == 0:
        click.echo("Nothing to delete.")
        return

    if not yes and not json_output:
        click.confirm(f"Delete {to_delete} snapshot(s)?", abort=True)

    deleted = hm.clean(keep=keep, before=before)

    if json_output:
        click.echo(json.dumps({"deleted": deleted}))
    else:
        click.echo(f"Deleted {deleted} snapshot(s).")


# ─────────────────── evo notifications ───────────────────


@main.group(invoke_without_command=True)
@click.pass_context
def notifications(ctx):
    """View and manage update notifications."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(notifications_list)


@notifications.command("list")
def notifications_list():
    """Show pending notifications."""
    from evolution.notifications import get_pending

    pending = get_pending()
    if not pending:
        click.echo("No pending notifications.")
        return

    click.echo(f"{len(pending)} notification(s):\n")
    for n in pending:
        click.echo(f"  [{n['type']}] {n['message']}")


@notifications.command("dismiss")
@click.argument("key", default="all")
def notifications_dismiss(key):
    """Dismiss notifications (default: all).

    Examples:
        evo notifications dismiss          # Dismiss all
        evo notifications dismiss update:evo-adapter-jest-cov:0.2.0
    """
    from evolution.notifications import dismiss, dismiss_all

    if key == "all":
        dismiss_all()
        click.echo("All notifications dismissed.")
    else:
        dismiss(key)
        click.echo(f"Dismissed: {key}")


@notifications.command("check")
@click.argument("path", default=".", type=click.Path(exists=True))
def notifications_check(path):
    """Force a notification check (ignores 24h cache).

    Checks for adapter updates, available adapters, and pattern updates.
    """
    from evolution.notifications import (
        _load_notifications, _prune_expired, _save_notifications,
        check_adapter_updates, check_adapter_discovery,
        format_notifications,
    )

    state = _load_notifications()
    state = _prune_expired(state)

    click.echo("Checking for updates...")
    check_adapter_updates(state)
    check_adapter_discovery(state, repo_path=path)
    state["last_check"] = __import__("time").time()
    _save_notifications(state)

    pending = [n for n in state["items"] if not n.get("dismissed")]
    if pending:
        click.echo(format_notifications(pending))
    else:
        click.echo("Everything is up to date.")


if __name__ == "__main__":
    main()
