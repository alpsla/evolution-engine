"""
CLI Tool — Primary user interface for Evolution Engine.

Usage:
    evo analyze [path]               # Detect adapters, run Phases 1-5
    evo analyze . --token ghp_xxx    # Unlock Tier 2 (CI, releases, security)
    evo analyze . --show-prompt      # Print investigation prompt after analysis
    evo sources [path]               # Show connected + detected data sources
    evo sources --what-if datadog    # Estimate impact of adding adapters
    evo investigate [path]           # AI investigation of advisory findings
    evo fix [path]                   # AI fix loop (iterate until EE confirms clear)
    evo fix . --dry-run              # Preview fix prompt without modifying files
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
    evo license status               # Show current license status
    evo license activate <key>       # Save license key
    evo verify <previous>            # Fix verification loop
"""

import json
import os
import sys
from pathlib import Path

import click

from evolution import __version__


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
@click.option("--show-prompt", is_flag=True, help="Print investigation prompt after analysis")
def analyze(path, token, families, evo_dir, json_output, llm, scope, quiet, show_prompt):
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
    )

    # Telemetry: prompt on first analyze, track completion
    from evolution.telemetry import prompt_consent, track_event
    prompt_consent()

    if json_output:
        click.echo(json.dumps(result, indent=2))
    elif result["status"] == "no_events":
        click.echo(result["message"])
        sys.exit(1)

    # Track analyze completion
    if result["status"] == "complete":
        summary = result.get("summary", {})
        track_event("analyze_complete", {
            "adapter_count": summary.get("adapters_detected", 0),
            "families": summary.get("families_affected", []),
            "signal_count": summary.get("significant_changes", 0),
            "pattern_count": summary.get("known_patterns_matched", 0),
        })

    if show_prompt and result["status"] == "complete":
        evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"
        prompt_path = evo_path / "phase5" / "investigation_prompt.txt"
        if prompt_path.exists():
            click.echo("\n" + "=" * 60)
            click.echo("INVESTIGATION PROMPT (paste into any AI coding tool)")
            click.echo("=" * 60)
            click.echo(prompt_path.read_text())


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
    """Run AI investigation on the latest advisory.

    Feeds the Phase 5 advisory into an AI agent to identify root causes,
    assess risk, and suggest fixes.

    Examples:
        evo investigate .                    # auto-detect AI backend
        evo investigate . --show-prompt      # print prompt for manual use
        evo investigate . --agent anthropic  # force Anthropic API
    """
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

    agent = get_agent(prefer=agent_type, model=model) if agent_type else None
    report = inv.run(agent=agent)

    if not report.success:
        click.echo(f"Investigation failed: {report.error}")
        sys.exit(1)

    click.echo(f"Investigation complete (agent: {report.agent_name})")
    click.echo(f"Saved to: {evo_path / 'investigation'}")
    click.echo()
    click.echo(report.text)

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
def fix(path, evo_dir, dry_run, max_iterations, branch, agent_type, scope, yes, interactive):
    """Apply AI fixes and verify with EE in a loop.

    Creates a branch, asks an AI agent to fix the flagged issues,
    re-runs EE to verify, and iterates until the advisory clears
    or max iterations are reached.

    Examples:
        evo fix . --dry-run              # preview what would be fixed
        evo fix .                        # fix with auto-detected agent
        evo fix . --max-iterations 5     # allow more attempts
        evo fix . --branch my-fix        # custom branch name
        evo fix . --yes                  # skip confirmation prompt
        evo fix . --interactive          # review changes after each iteration
    """
    import subprocess as _subprocess

    from evolution.agents.base import get_agent
    from evolution.fixer import Fixer

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"

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
        branch_name=branch,
        scope=scope,
        interactive_callback=interactive_callback,
    )

    if dry_run:
        click.echo("DRY RUN — no files modified\n")
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


@patterns.command("sync")
@click.argument("path", default=".", type=click.Path(exists=True))
def patterns_sync(path):
    """Sync universal patterns into local knowledge base.

    Imports bundled universal patterns (shipped with the package) into
    your local KB. Patterns already present are skipped automatically.
    This also runs automatically during `evo analyze`.
    """
    from evolution.kb_export import import_patterns

    db_path = Path(path) / ".evo" / "phase4" / "knowledge.db"
    if not db_path.exists():
        click.echo("No knowledge base found. Run `evo analyze` first.")
        return

    # Load bundled universal patterns
    data_dir = Path(__file__).parent / "data"
    universal_path = data_dir / "universal_patterns.json"
    if not universal_path.exists():
        click.echo("No bundled universal patterns found.")
        return

    data = json.loads(universal_path.read_text())
    patterns_to_import = data.get("import_ready", [])

    if not patterns_to_import:
        click.echo("No universal patterns available to import.")
        return

    click.echo(f"Syncing {len(patterns_to_import)} universal pattern(s)...")
    result = import_patterns(db_path, patterns_to_import)
    click.echo(f"  New: {result['imported']}, Already present: {result['skipped']}, "
               f"Rejected: {result['rejected']}")

    if result["imported"] > 0:
        click.echo(f"\n{result['imported']} new pattern(s) added to your knowledge base.")
    else:
        click.echo("\nKnowledge base is up to date.")


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

    # Detected but not connected
    click.echo()
    if unconnected:
        click.echo("DETECTED (found in your repo — not yet connected):")
        for s in unconnected:
            evidence_str = "; ".join(s.evidence[:2])
            hint = _install_hint(s)
            click.echo(f"  \U0001f50d {s.display_name:20s} {evidence_str}")
            if hint:
                click.echo(f"     {hint}")
    else:
        if detected:
            click.echo("All detected tools are already connected.")
        else:
            click.echo("No additional tools detected in this repo.")

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

    # Missing tokens hint
    missing = registry.explain_missing(tokens)
    if missing:
        click.echo()
        for msg in missing:
            click.echo(f"  {msg}")


def _install_hint(svc) -> str:
    """Generate install hint for a detected service."""
    # Built-in adapters that just need a token
    builtin_token = {
        "ci": "Set GITHUB_TOKEN to connect",
        "deployment": "Set GITHUB_TOKEN to connect",
        "security": "Set GITHUB_TOKEN to connect",
    }
    if svc.family in builtin_token:
        return builtin_token[svc.family]
    return f"Install: pip install {svc.adapter}"


# ─────────────────── evo adapter ───────────────────


@main.group()
def adapter():
    """Manage and validate adapter plugins."""
    pass


@adapter.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
@click.option("--token", "-t", help="GitHub token for Tier 2 adapters")
def adapter_list(path, token):
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

    click.echo("Connected adapters:")
    if configs:
        for c in configs:
            tier_label = {1: "built-in", 2: "API", 3: "plugin"}
            badge = tier_label.get(c.tier, f"tier-{c.tier}")
            plugin_note = f" (from {c.plugin_name})" if c.plugin_name else ""
            click.echo(f"  \u2705 [{badge}] {c.family}/{c.adapter_name}{plugin_note}")
    else:
        click.echo("  (none)")

    if plugins:
        click.echo()
        click.echo("Installed plugins:")
        for p in plugins:
            status = "detected" if p["detected"] else "not detected"
            click.echo(f"  {p['plugin_name']}: {p['family']}/{p['adapter_name']} ({status})")

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


@adapter.command("validate")
@click.argument("adapter_path")
@click.option("--args", "constructor_args", help="JSON constructor args (e.g. '{\"path\": \"/tmp\"}')")
@click.option("--max-events", default=10, help="Max events to consume during validation")
def adapter_validate(adapter_path, constructor_args, max_events):
    """Validate a plugin adapter against the Adapter Contract.

    ADAPTER_PATH is a dotted Python path like 'my_package.MyAdapter'.

    Example:
        evo adapter validate evo_jenkins.JenkinsAdapter
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
def report(path, output, evo_dir, title, open_browser):
    """Generate an HTML report from the latest advisory."""
    from evolution.report_generator import generate_report

    evo_path = Path(evo_dir) if evo_dir else Path(path) / ".evo"

    if not (evo_path / "phase5" / "advisory.json").exists():
        click.echo("No advisory found. Run `evo analyze` first.")
        sys.exit(1)

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
    file_url = f"file://{output_path.resolve()}"
    # OSC 8 hyperlink: clickable in modern terminals (iTerm2, VS Code, etc.)
    click.echo(f"Report generated: \033]8;;{file_url}\033\\{output_path}\033]8;;\033\\")

    from evolution.telemetry import track_event
    track_event("cli_command", {"command": "report"})

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{output_path.resolve()}")


# ─────────────────── evo verify ───────────────────


@main.command()
@click.argument("previous", type=click.Path(exists=True))
@click.option("--path", default=".", type=click.Path(exists=True), help="Repository path")
@click.option("--scope", "-s", help="Scope identifier")
def verify(previous, path, scope):
    """Compare current state against a previous advisory."""
    from evolution.phase5_engine import Phase5Engine

    evo_dir = Path(path) / ".evo"
    scope = scope or Path(path).resolve().name

    phase5 = Phase5Engine(evo_dir)
    result = phase5.verify(scope=scope, previous_advisory_path=previous)

    if result["status"] == "verified":
        click.echo(result["verification_text"])
    else:
        click.echo(f"Status: {result['status']}")
        click.echo(result.get("message", ""))


# ─────────────────── evo config ───────────────────


@main.group()
def config():
    """Manage Evolution Engine settings."""
    pass


@config.command("list")
def config_list():
    """Show all configuration settings with defaults."""
    from evolution.config import EvoConfig

    cfg = EvoConfig()
    overrides = cfg.user_overrides()

    click.echo(f"Config file: {cfg.path}")
    click.echo()
    for key, value in sorted(cfg.all().items()):
        marker = " *" if key in overrides else ""
        click.echo(f"  {key} = {value}{marker}")
    click.echo()
    click.echo("  (* = user override, all others are defaults)")


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
        evo config set sync.privacy_level 2

    Privacy levels:
        0 = Nothing shared (default)
        1 = Advisory metadata only
        2 = Anonymized pattern digests
    """
    from evolution.kb_sync import KBSync

    evo_dir = Path(path) / ".evo"
    sync = KBSync(evo_dir=evo_dir)

    if sync.privacy_level < 1:
        click.echo("Sharing is disabled (privacy_level=0).")
        click.echo()
        click.echo("To enable, set your privacy level:")
        click.echo("  evo config set sync.privacy_level 1   # metadata only")
        click.echo("  evo config set sync.privacy_level 2   # anonymized patterns")
        sys.exit(1)

    click.echo(f"Pushing to {sync.registry_url} (level {sync.privacy_level})...")
    result = sync.push()

    if not result.success:
        click.echo(f"Error: {result.error}")
        sys.exit(1)

    click.echo(f"  Patterns shared: {result.pushed}")


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


if __name__ == "__main__":
    main()
