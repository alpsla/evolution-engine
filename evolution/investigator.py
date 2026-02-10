"""
Investigator — AI-powered root cause analysis from EE advisory.

Reads the Phase 5 advisory and investigation prompt, feeds them to an
AI agent, and produces a structured investigation report.

Usage:
    investigator = Investigator(evo_dir=".evo")
    report = investigator.run()             # auto-detect agent
    report = investigator.run(agent=agent)  # specific agent

CLI:
    evo investigate .                       # run with auto-detected agent
    evo investigate . --show-prompt         # print prompt for manual use
    evo investigate . --agent anthropic     # force specific backend
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from evolution.agents.base import AgentResult, BaseAgent, get_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a senior software engineer investigating anomalies detected by \
Evolution Engine, a development process monitoring tool. You receive a \
structural analysis of a repository showing metrics that deviate significantly \
from historical baselines.

Your task:
1. Analyze each flagged change and determine the most likely root cause.
2. Assess whether the deviation represents a real problem or an expected change.
3. For each problem, suggest a specific, minimal fix.
4. Prioritize findings by risk (Critical > High > Medium > Low).

Output format — use this exact structure:

INVESTIGATION REPORT

## Finding 1: [metric name]
Risk: [Critical|High|Medium|Low]
Root cause: [1-2 sentence explanation]
Assessment: [problem|expected|needs-review]
Suggested fix: [specific action, file, or code change]

## Finding 2: ...
(repeat for each flagged change)

## Summary
- Total findings: N
- Problems requiring fixes: N
- Expected changes (no action): N
- Items needing human review: N

## Recommended fix order
1. [highest priority fix]
2. ...

Keep explanations concise. Reference specific files and line numbers when possible.\
"""


class InvestigationReport:
    """Structured investigation report from AI agent."""

    def __init__(
        self,
        text: str,
        advisory_id: str,
        scope: str,
        agent_name: str,
        success: bool = True,
        error: Optional[str] = None,
    ):
        self.text = text
        self.advisory_id = advisory_id
        self.scope = scope
        self.agent_name = agent_name
        self.success = success
        self.error = error
        self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "investigation_id": self.advisory_id,
            "scope": self.scope,
            "agent": self.agent_name,
            "generated_at": self.generated_at,
            "success": self.success,
            "error": self.error,
            "report": self.text,
        }


class Investigator:
    """Run AI investigation on a Phase 5 advisory.

    Args:
        evo_dir: Path to the .evo directory containing phase5/advisory.json.
    """

    def __init__(self, evo_dir: str | Path):
        self.evo_dir = Path(evo_dir)
        self.phase5_dir = self.evo_dir / "phase5"

    def get_prompt(self) -> tuple[str, dict]:
        """Load advisory and return the investigation prompt + advisory data.

        Returns:
            Tuple of (investigation_prompt_text, advisory_dict).

        Raises:
            FileNotFoundError: If advisory.json doesn't exist.
        """
        advisory_path = self.phase5_dir / "advisory.json"
        if not advisory_path.exists():
            raise FileNotFoundError(
                f"No advisory found at {advisory_path}. Run `evo analyze` first."
            )

        advisory = json.loads(advisory_path.read_text())

        # Use the pre-built investigation prompt if available
        prompt_path = self.phase5_dir / "investigation_prompt.txt"
        if prompt_path.exists():
            prompt = prompt_path.read_text()
        else:
            # Fallback: build from advisory data
            prompt = self._build_prompt(advisory)

        # Append pattern context if available
        pattern_context = self._format_patterns(advisory)
        if pattern_context:
            prompt += "\n" + pattern_context

        return prompt, advisory

    def run(
        self,
        agent: BaseAgent = None,
        show_prompt: bool = False,
    ) -> InvestigationReport:
        """Execute the investigation.

        Args:
            agent: Agent to use (auto-detected if None).
            show_prompt: If True, use ShowPromptAgent (just return the prompt).

        Returns:
            InvestigationReport with findings.
        """
        prompt, advisory = self.get_prompt()
        advisory_id = advisory.get("advisory_id", "unknown")
        scope = advisory.get("scope", "unknown")

        if show_prompt:
            return InvestigationReport(
                text=f"--- SYSTEM PROMPT ---\n{SYSTEM_PROMPT}\n\n--- USER PROMPT ---\n{prompt}",
                advisory_id=advisory_id,
                scope=scope,
                agent_name="show-prompt",
            )

        if agent is None:
            agent = get_agent()

        logger.info("Running investigation with agent: %s", agent.name)
        result = agent.complete(prompt, system=SYSTEM_PROMPT)

        report = InvestigationReport(
            text=result.text,
            advisory_id=advisory_id,
            scope=scope,
            agent_name=agent.name,
            success=result.success,
            error=result.error,
        )

        # Save outputs
        self._save(report)
        return report

    def _save(self, report: InvestigationReport):
        """Save investigation report to .evo directory."""
        output_dir = self.evo_dir / "investigation"
        output_dir.mkdir(parents=True, exist_ok=True)

        # JSON report
        with open(output_dir / "investigation.json", "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        # Human-readable text
        with open(output_dir / "investigation.txt", "w") as f:
            f.write(report.text)

    def _build_prompt(self, advisory: dict) -> str:
        """Fallback prompt builder from raw advisory data."""
        scope = advisory.get("scope", "repository")
        period = advisory.get("period", {})

        lines = [
            f"Here is a structural analysis of {scope} over the period "
            f"{period.get('from', '?')[:10]} to {period.get('to', '?')[:10]}.",
            "",
            "CHANGES DETECTED:",
        ]

        for c in advisory.get("changes", []):
            normal = c.get("normal", {})
            lines.append(
                f"- {c['family']} / {c['metric']}: normally {normal.get('mean', 0):.4g}, "
                f"now {c.get('current', 0):.4g} ({abs(c.get('deviation_stddev', 0)):.1f} stddev)"
            )

        lines.extend([
            "",
            "Based on this evidence:",
            "1. What is the most likely root cause of the observed changes?",
            "2. Which specific files should be reviewed first?",
            "3. Are there any dependency or configuration changes that may explain the test failures?",
        ])

        return "\n".join(lines)

    @staticmethod
    def _format_patterns(advisory: dict) -> str:
        """Format pattern matches for additional context."""
        sections = []

        known = advisory.get("pattern_matches", [])
        if known:
            sections.append("KNOWN PATTERNS MATCHED:")
            for p in known[:5]:
                desc = p.get("description", "")[:200]
                sources = ", ".join(p.get("sources", []))
                sections.append(f"  [{sources}] {desc}")

        candidates = advisory.get("candidate_patterns", [])
        if candidates:
            sections.append("CANDIDATE PATTERNS:")
            for p in candidates[:5]:
                desc = p.get("description", "")[:200]
                families = ", ".join(p.get("families", []))
                sections.append(f"  [{families}] {desc}")

        return "\n".join(sections) if sections else ""
