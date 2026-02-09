"""
CLI Tool — Primary user interface for Evolution Engine.

Usage:
    evo analyze [path]               # Detect adapters, run Phases 1-5
    evo analyze . --token ghp_xxx    # Unlock Tier 2 (CI, releases, security)
    evo analyze . --families git,ci  # Override auto-detected families
    evo status [path]                # Show detected adapters and last run info
    evo patterns list                # Show KB contents
    evo patterns export              # Export anonymized pattern digests
    evo patterns import <file>       # Import community patterns
    evo license status               # Show current license status
    evo license activate <key>       # Save license key
    evo verify <previous>            # Fix verification loop
"""

import json
import os
import sys
from pathlib import Path

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="evo")
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
def analyze(path, token, families, evo_dir, json_output, llm, scope, quiet):
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

    if json_output:
        click.echo(json.dumps(result, indent=2))
    elif result["status"] == "no_events":
        click.echo(result["message"])
        sys.exit(1)


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


# ─────────────────── evo adapter ───────────────────


@main.group()
def adapter():
    """Manage and validate adapter plugins."""
    pass


@adapter.command("list")
@click.argument("path", default=".", type=click.Path(exists=True))
def adapter_list(path):
    """List all detected adapters including plugins."""
    from evolution.registry import AdapterRegistry

    registry = AdapterRegistry(path)
    configs = registry.detect()
    plugins = registry.list_plugins()

    click.echo("Detected adapters:")
    for c in configs:
        tier_label = {1: "built-in", 2: "API", 3: "plugin"}
        badge = tier_label.get(c.tier, f"tier-{c.tier}")
        plugin_note = f" (from {c.plugin_name})" if c.plugin_name else ""
        click.echo(f"  [{badge}] {c.family}/{c.adapter_name}{plugin_note}")

    if plugins:
        click.echo()
        click.echo("Installed plugins:")
        for p in plugins:
            status = "detected" if p["detected"] else "not detected"
            click.echo(f"  {p['plugin_name']}: {p['family']}/{p['adapter_name']} ({status})")


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
        click.echo("Set EVO_LICENSE_KEY or visit https://evo.dev/pro")


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
    click.echo(f"Report generated: {output_path}")

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


if __name__ == "__main__":
    main()
