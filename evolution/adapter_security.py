"""
Adapter Security Scanner — Static analysis of adapter source for dangerous patterns.

Scans adapter `.py` files using regex-based checks and AST analysis to detect
potentially dangerous code before installation.

Usage:
    from evolution.adapter_security import scan_adapter_source
    report = scan_adapter_source("evo_jenkins")  # dotted module name
    report = scan_adapter_source("/path/to/adapter/")  # directory path

    if report.passed:
        print("No critical issues found")
    for finding in report.findings:
        print(f"[{finding.severity}] {finding.check}: {finding.message}")

CLI:
    evo adapter security-check evo_jenkins
    evo adapter security-check /path/to/adapter/
    evo adapter validate evo_jenkins.JenkinsAdapter --security
"""

import ast
import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SecurityFinding:
    """A single finding from the security scan."""
    check: str
    severity: str  # "critical", "warning", "info"
    message: str
    file: str = ""
    line: int = 0


@dataclass
class SecurityReport:
    """Full security scan report for an adapter."""
    target: str
    findings: list[SecurityFinding] = field(default_factory=list)
    files_scanned: int = 0
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        """True if no critical findings."""
        return not any(f.severity == "critical" for f in self.findings)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "info")

    def summary(self) -> str:
        lines = [f"Security scan: {self.target}"]
        lines.append(f"Files scanned: {self.files_scanned}")
        lines.append(f"Result: {'PASSED' if self.passed else 'FAILED'}")
        lines.append(f"  Critical: {self.critical_count}, "
                     f"Warnings: {self.warning_count}, "
                     f"Info: {self.info_count}")

        if self.findings:
            lines.append("")
            for f in self.findings:
                loc = f""
                if f.file:
                    loc = f" ({f.file}"
                    if f.line:
                        loc += f":{f.line}"
                    loc += ")"
                lines.append(f"  [{f.severity.upper()}] {f.check}{loc}")
                lines.append(f"           {f.message}")

        return "\n".join(lines)


# ─── Regex-based Checks ───

REGEX_CHECKS: list[tuple[str, str, str, str]] = [
    # (check_name, severity, pattern, message)
    ("eval_call", "critical",
     r"\beval\s*\(", "eval() can execute arbitrary code"),
    ("exec_call", "critical",
     r"\bexec\s*\(", "exec() can execute arbitrary code"),
    ("os_system", "critical",
     r"\bos\.system\s*\(", "os.system() runs shell commands"),
    ("os_popen", "critical",
     r"\bos\.popen\s*\(", "os.popen() runs shell commands"),
    ("pickle_load", "critical",
     r"\bpickle\.loads?\s*\(", "pickle deserialization can execute arbitrary code"),
    ("yaml_unsafe_load", "critical",
     r"\byaml\.unsafe_load\s*\(", "yaml.unsafe_load can execute arbitrary code"),
    ("marshal_load", "critical",
     r"\bmarshal\.loads?\s*\(", "marshal deserialization can execute arbitrary code"),
    ("hardcoded_secret", "critical",
     r"(?:api_key|secret|password|token)\s*=\s*['\"][A-Za-z0-9]{16,}['\"]",
     "Possible hardcoded secret detected"),
    ("subprocess_usage", "warning",
     r"\bsubprocess\b", "subprocess module allows command execution"),
    ("compile_call", "warning",
     r"\bcompile\s*\(", "compile() can create code objects dynamically"),
    ("dunder_import", "warning",
     r"\b__import__\s*\(", "__import__() allows dynamic module loading"),
    ("path_traversal", "warning",
     r"['\"]\.\.[\\/]", "Path traversal pattern detected"),
    ("absolute_system_path", "info",
     r"['\"]\/(?:etc|tmp|usr)[\\/]", "Reference to absolute system path"),
]


# ─── AST-based Checks ───

NETWORK_MODULES = {"requests", "urllib", "httpx", "socket", "aiohttp"}


class _InitNetworkVisitor(ast.NodeVisitor):
    """AST visitor that detects network calls inside __init__ methods."""

    def __init__(self, filename: str):
        self.filename = filename
        self.findings: list[SecurityFinding] = []
        self._in_init = False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name == "__init__":
            self._in_init = True
            self.generic_visit(node)
            self._in_init = False
        else:
            self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if self._in_init:
            # Check for module.function() calls like requests.get()
            if isinstance(node.value, ast.Name) and node.value.id in NETWORK_MODULES:
                self.findings.append(SecurityFinding(
                    check="network_in_init",
                    severity="warning",
                    message=f"Network call ({node.value.id}.{node.attr}) in __init__; "
                            f"move to iter_events()",
                    file=self.filename,
                    line=node.lineno,
                ))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        if self._in_init:
            for alias in node.names:
                if alias.name.split(".")[0] in NETWORK_MODULES:
                    self.findings.append(SecurityFinding(
                        check="network_in_init",
                        severity="warning",
                        message=f"Network module import ({alias.name}) inside __init__; "
                                f"move to iter_events()",
                        file=self.filename,
                        line=node.lineno,
                    ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if self._in_init and node.module:
            if node.module.split(".")[0] in NETWORK_MODULES:
                self.findings.append(SecurityFinding(
                    check="network_in_init",
                    severity="warning",
                    message=f"Network module import (from {node.module}) inside __init__; "
                            f"move to iter_events()",
                    file=self.filename,
                    line=node.lineno,
                ))
        self.generic_visit(node)


def _resolve_target(target: str) -> Optional[Path]:
    """Resolve a target to a directory path.

    Accepts:
      - A directory path (returns as-is if exists)
      - A dotted module name (resolves via importlib)
    """
    # Try as directory first
    p = Path(target)
    if p.is_dir():
        return p

    # Try as a dotted module path
    try:
        # For "module.ClassName", strip the class name
        parts = target.split(".")
        for i in range(len(parts), 0, -1):
            module_name = ".".join(parts[:i])
            spec = importlib.util.find_spec(module_name)
            if spec and spec.origin:
                origin = Path(spec.origin)
                # If it's a package (__init__.py), return the directory
                if origin.name == "__init__.py":
                    return origin.parent
                # If it's a single module, return its parent
                return origin.parent
    except (ModuleNotFoundError, ValueError):
        pass

    return None


def _scan_file_regex(filepath: Path, findings: list[SecurityFinding]):
    """Run regex-based checks on a single file."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return

    rel_path = filepath.name
    for check_name, severity, pattern, message in REGEX_CHECKS:
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count("\n") + 1
            findings.append(SecurityFinding(
                check=check_name,
                severity=severity,
                message=message,
                file=rel_path,
                line=line_num,
            ))


def _scan_file_ast(filepath: Path, findings: list[SecurityFinding]):
    """Run AST-based checks on a single file."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (OSError, SyntaxError):
        return

    visitor = _InitNetworkVisitor(filepath.name)
    visitor.visit(tree)
    findings.extend(visitor.findings)


def scan_adapter_source(target: str) -> SecurityReport:
    """Scan adapter source code for security issues.

    Args:
        target: A dotted module path (e.g. "evo_jenkins") or a directory path.

    Returns:
        SecurityReport with all findings.
    """
    report = SecurityReport(target=target)

    resolved = _resolve_target(target)
    if resolved is None:
        report.error = f"Could not resolve target: {target}"
        return report

    # Find all .py files
    py_files = list(resolved.rglob("*.py"))
    report.files_scanned = len(py_files)

    for py_file in py_files:
        _scan_file_regex(py_file, report.findings)
        _scan_file_ast(py_file, report.findings)

    # Sort: critical first, then warning, then info
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    report.findings.sort(key=lambda f: (severity_order.get(f.severity, 9), f.file, f.line))

    return report
