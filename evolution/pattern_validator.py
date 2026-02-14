"""
Pattern Validator — Validate pattern packages before publish.

Checks that patterns in a package pass security validation, have required
fields, use community scope, and have unique fingerprints.

Usage:
    from evolution.pattern_validator import validate_pattern_package

    report = validate_pattern_package(patterns)
    if report.passed:
        print("Package valid!")

CLI:
    evo patterns validate <path>
"""

from dataclasses import dataclass, field

from evolution.kb_security import PatternValidationError, validate_pattern


@dataclass
class CheckResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str = ""
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationReport:
    """Full validation report for a pattern package."""
    package_name: str
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
        passed_count = sum(1 for c in self.checks if c.passed)
        lines = [f"Pattern Package: {self.package_name}"]
        lines.append(f"Result: {'PASSED' if self.passed else 'FAILED'} "
                      f"({passed_count}/{total} checks)")
        lines.append("")

        for c in self.checks:
            icon = "PASS" if c.passed else ("FAIL" if c.severity == "error" else "WARN")
            lines.append(f"  [{icon}] {c.name}")
            if not c.passed and c.message:
                lines.append(f"         {c.message}")

        return "\n".join(lines)


REQUIRED_FIELDS = [
    "fingerprint", "sources", "metrics", "pattern_type", "discovery_method",
]


def validate_pattern_package(
    patterns: list[dict],
    package_name: str = "unknown",
) -> ValidationReport:
    """Validate a list of patterns from a package.

    Checks:
      1. Package has at least one pattern
      2. Each pattern passes kb_security.validate_pattern()
      3. Required fields present: fingerprint, sources, metrics, pattern_type, discovery_method
      4. Scope is "community" (not "local")
      5. Fingerprints are unique within the package
      6. correlation_strength is set

    Args:
        patterns: List of pattern dicts to validate.
        package_name: Name for the report header.

    Returns:
        ValidationReport with all check results.
    """
    report = ValidationReport(package_name=package_name)

    # Check 1: Non-empty
    if not patterns:
        report.checks.append(CheckResult(
            name="has_patterns",
            passed=False,
            message="Package contains no patterns",
        ))
        return report

    report.checks.append(CheckResult(
        name="has_patterns",
        passed=True,
        message=f"{len(patterns)} pattern(s)",
    ))

    # Check 2: Each pattern passes security validation
    all_valid = True
    validation_errors = []
    for i, p in enumerate(patterns):
        try:
            validate_pattern(p, require_external_scope=True)
        except PatternValidationError as e:
            all_valid = False
            validation_errors.append(f"Pattern {i}: {e.field} — {e.reason}")

    if all_valid:
        report.checks.append(CheckResult(
            name="security_validation",
            passed=True,
            message=f"All {len(patterns)} patterns pass security checks",
        ))
    else:
        report.checks.append(CheckResult(
            name="security_validation",
            passed=False,
            message="; ".join(validation_errors[:5]),
        ))

    # Check 3: Required fields present
    missing_fields = []
    for i, p in enumerate(patterns):
        for f in REQUIRED_FIELDS:
            if f not in p or not p[f]:
                missing_fields.append(f"Pattern {i}: missing {f}")

    if not missing_fields:
        report.checks.append(CheckResult(
            name="required_fields",
            passed=True,
        ))
    else:
        report.checks.append(CheckResult(
            name="required_fields",
            passed=False,
            message="; ".join(missing_fields[:5]),
        ))

    # Check 4: Scope is community
    bad_scopes = []
    for i, p in enumerate(patterns):
        scope = p.get("scope", "community")
        if scope not in ("community", "universal"):
            bad_scopes.append(f"Pattern {i}: scope={scope}")

    if not bad_scopes:
        report.checks.append(CheckResult(
            name="scope_community",
            passed=True,
        ))
    else:
        report.checks.append(CheckResult(
            name="scope_community",
            passed=False,
            message="; ".join(bad_scopes),
        ))

    # Check 5: Unique fingerprints
    fingerprints = [p.get("fingerprint", "") for p in patterns]
    unique_fps = set(fingerprints)
    if len(unique_fps) == len(fingerprints):
        report.checks.append(CheckResult(
            name="unique_fingerprints",
            passed=True,
        ))
    else:
        dupes = [fp for fp in unique_fps if fingerprints.count(fp) > 1]
        report.checks.append(CheckResult(
            name="unique_fingerprints",
            passed=False,
            message=f"Duplicate fingerprints: {', '.join(dupes[:3])}",
        ))

    # Check 6: correlation_strength is set
    missing_corr = []
    for i, p in enumerate(patterns):
        if p.get("correlation_strength") is None:
            missing_corr.append(f"Pattern {i}")

    if not missing_corr:
        report.checks.append(CheckResult(
            name="has_correlation_strength",
            passed=True,
        ))
    else:
        report.checks.append(CheckResult(
            name="has_correlation_strength",
            passed=False,
            message=f"Missing correlation_strength: {', '.join(missing_corr[:3])}",
            severity="warning",
        ))

    return report
