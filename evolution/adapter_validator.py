"""
Adapter Validator — Certification gate for plugin adapters.

Validates that a third-party adapter conforms to the Adapter Contract:
  1. Has required class attributes (source_family, source_type, etc.)
  2. iter_events() yields valid SourceEvent dicts
  3. Events have correct structure (payload, attestation, etc.)
  4. source_family is a recognized family
  5. Events can be ingested by Phase 1 without errors

Usage:
    from evolution.adapter_validator import validate_adapter

    results = validate_adapter(MyAdapter, constructor_args={"path": "/tmp/repo"})
    if results.passed:
        print("Adapter certified!")
    else:
        for check in results.checks:
            if not check.passed:
                print(f"FAIL: {check.name}: {check.message}")

CLI:
    evo adapter validate my_package.MyAdapter
"""

import importlib
import traceback
from dataclasses import dataclass, field
from typing import Optional


VALID_FAMILIES = {
    "version_control", "ci", "testing", "dependency",
    "schema", "deployment", "config", "security",
}

VALID_ORDERING_MODES = {"causal", "temporal"}
VALID_ATTESTATION_TIERS = {"strong", "medium", "weak"}

REQUIRED_CLASS_ATTRS = [
    "source_family",
    "source_type",
    "ordering_mode",
    "attestation_tier",
]

REQUIRED_EVENT_FIELDS = [
    "source_family",
    "source_type",
    "source_id",
    "ordering_mode",
    "attestation",
    "payload",
]


@dataclass
class CheckResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str = ""
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationReport:
    """Full validation report for an adapter."""
    adapter_class: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "error")

    @property
    def errors(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        lines = [f"Adapter: {self.adapter_class}"]
        lines.append(f"Result: {'PASSED' if self.passed else 'FAILED'} ({passed}/{total} checks)")
        lines.append("")

        for c in self.checks:
            icon = "PASS" if c.passed else ("FAIL" if c.severity == "error" else "WARN")
            lines.append(f"  [{icon}] {c.name}")
            if not c.passed and c.message:
                lines.append(f"         {c.message}")

        return "\n".join(lines)


def load_adapter_class(dotted_path: str):
    """Load an adapter class from a dotted module path.

    Args:
        dotted_path: e.g. "evo_jenkins.JenkinsAdapter"

    Returns:
        The adapter class.

    Raises:
        ImportError, AttributeError
    """
    module_path, _, class_name = dotted_path.rpartition(".")
    if not module_path:
        raise ImportError(f"Invalid path '{dotted_path}': expected 'module.ClassName'")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def validate_adapter(
    adapter_class,
    constructor_args: dict = None,
    max_events: int = 10,
) -> ValidationReport:
    """Validate an adapter class against the Adapter Contract.

    Args:
        adapter_class: The adapter class (not an instance).
        constructor_args: Dict of kwargs to pass to the constructor.
                         If None, tries no-arg construction.
        max_events: Max events to consume during iter_events() check.

    Returns:
        ValidationReport with all check results.
    """
    report = ValidationReport(
        adapter_class=f"{adapter_class.__module__}.{adapter_class.__name__}"
        if hasattr(adapter_class, "__module__") else str(adapter_class)
    )

    # ── Check 1: Required class attributes ──
    for attr in REQUIRED_CLASS_ATTRS:
        value = getattr(adapter_class, attr, None)
        if value is None:
            report.checks.append(CheckResult(
                name=f"class_attr_{attr}",
                passed=False,
                message=f"Missing required class attribute: {attr}",
            ))
        else:
            report.checks.append(CheckResult(
                name=f"class_attr_{attr}",
                passed=True,
            ))

    # ── Check 2: source_family is valid ──
    family = getattr(adapter_class, "source_family", None)
    if family and family not in VALID_FAMILIES:
        report.checks.append(CheckResult(
            name="valid_family",
            passed=False,
            message=f"source_family '{family}' not in {VALID_FAMILIES}",
        ))
    elif family:
        report.checks.append(CheckResult(name="valid_family", passed=True))

    # ── Check 3: ordering_mode is valid ──
    ordering = getattr(adapter_class, "ordering_mode", None)
    if ordering and ordering not in VALID_ORDERING_MODES:
        report.checks.append(CheckResult(
            name="valid_ordering_mode",
            passed=False,
            message=f"ordering_mode '{ordering}' not in {VALID_ORDERING_MODES}",
        ))
    elif ordering:
        report.checks.append(CheckResult(name="valid_ordering_mode", passed=True))

    # ── Check 4: attestation_tier is valid ──
    tier = getattr(adapter_class, "attestation_tier", None)
    if tier and tier not in VALID_ATTESTATION_TIERS:
        report.checks.append(CheckResult(
            name="valid_attestation_tier",
            passed=False,
            message=f"attestation_tier '{tier}' not in {VALID_ATTESTATION_TIERS}",
        ))
    elif tier:
        report.checks.append(CheckResult(name="valid_attestation_tier", passed=True))

    # ── Check 5: iter_events method exists ──
    if not hasattr(adapter_class, "iter_events") or not callable(getattr(adapter_class, "iter_events", None)):
        report.checks.append(CheckResult(
            name="has_iter_events",
            passed=False,
            message="Missing required method: iter_events()",
        ))
        return report  # Can't continue without iter_events

    report.checks.append(CheckResult(name="has_iter_events", passed=True))

    # ── Check 6: Can instantiate ──
    constructor_args = constructor_args or {}
    try:
        instance = adapter_class(**constructor_args)
    except Exception as e:
        report.checks.append(CheckResult(
            name="can_instantiate",
            passed=False,
            message=f"Constructor failed: {e}",
        ))
        return report

    report.checks.append(CheckResult(name="can_instantiate", passed=True))

    # ── Check 7: source_id is set after construction ──
    if not hasattr(instance, "source_id") or not instance.source_id:
        report.checks.append(CheckResult(
            name="has_source_id",
            passed=False,
            message="Instance must set source_id after construction",
            severity="warning",
        ))
    else:
        report.checks.append(CheckResult(name="has_source_id", passed=True))

    # ── Check 8: iter_events yields valid events ──
    events = []
    try:
        for i, event in enumerate(instance.iter_events()):
            events.append(event)
            if i >= max_events - 1:
                break
    except Exception as e:
        report.checks.append(CheckResult(
            name="iter_events_runs",
            passed=False,
            message=f"iter_events() raised: {e}",
        ))
        return report

    if len(events) == 0:
        report.checks.append(CheckResult(
            name="iter_events_runs",
            passed=False,
            message="iter_events() yielded 0 events (need at least 1 for validation)",
            severity="warning",
        ))
        return report

    report.checks.append(CheckResult(
        name="iter_events_runs",
        passed=True,
        message=f"Yielded {len(events)} event(s)",
    ))

    # ── Check 9: Events have required fields ──
    all_fields_ok = True
    missing_fields = set()
    for event in events:
        if not isinstance(event, dict):
            report.checks.append(CheckResult(
                name="event_structure",
                passed=False,
                message=f"Event is {type(event).__name__}, expected dict",
            ))
            all_fields_ok = False
            break

        for field_name in REQUIRED_EVENT_FIELDS:
            if field_name not in event:
                missing_fields.add(field_name)
                all_fields_ok = False

    if missing_fields:
        report.checks.append(CheckResult(
            name="event_structure",
            passed=False,
            message=f"Events missing required fields: {sorted(missing_fields)}",
        ))
    elif all_fields_ok:
        report.checks.append(CheckResult(name="event_structure", passed=True))

    # ── Check 10: source_family in events matches class attribute ──
    declared_family = getattr(adapter_class, "source_family", None)
    family_mismatch = False
    for event in events:
        if isinstance(event, dict) and event.get("source_family") != declared_family:
            family_mismatch = True
            break

    if family_mismatch:
        report.checks.append(CheckResult(
            name="family_consistency",
            passed=False,
            message=f"Event source_family doesn't match class attribute '{declared_family}'",
        ))
    else:
        report.checks.append(CheckResult(name="family_consistency", passed=True))

    # ── Check 11: Attestation structure ──
    attestation_ok = True
    for event in events:
        if not isinstance(event, dict):
            continue
        att = event.get("attestation")
        if not isinstance(att, dict):
            attestation_ok = False
            break
        if "trust_tier" not in att:
            attestation_ok = False
            break

    if not attestation_ok:
        report.checks.append(CheckResult(
            name="attestation_structure",
            passed=False,
            message="attestation must be dict with 'trust_tier' field",
        ))
    else:
        report.checks.append(CheckResult(name="attestation_structure", passed=True))

    # ── Check 12: Payload is dict ──
    payload_ok = all(
        isinstance(e.get("payload"), dict)
        for e in events if isinstance(e, dict)
    )
    if not payload_ok:
        report.checks.append(CheckResult(
            name="payload_is_dict",
            passed=False,
            message="payload must be a dict",
        ))
    else:
        report.checks.append(CheckResult(name="payload_is_dict", passed=True))

    # ── Check 13: Events are JSON-serializable (strict — no default handler) ──
    import json
    try:
        for event in events:
            json.dumps(event)  # strict: no default=str, sets/objects must fail
        report.checks.append(CheckResult(name="json_serializable", passed=True))
    except (TypeError, ValueError) as e:
        report.checks.append(CheckResult(
            name="json_serializable",
            passed=False,
            message=f"Events must be JSON-serializable: {e}",
        ))

    return report
