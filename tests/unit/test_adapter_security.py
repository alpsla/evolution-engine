"""
Unit tests for adapter security scanning (evolution/adapter_security.py).

Tests regex-based and AST-based checks for dangerous patterns in adapter source.
"""

import textwrap

import pytest

from evolution.adapter_security import (
    SecurityFinding,
    SecurityReport,
    scan_adapter_source,
    _scan_file_regex,
    _scan_file_ast,
)


# ─── SecurityReport dataclass ───


class TestSecurityReport:
    def test_passed_when_no_findings(self):
        report = SecurityReport(target="test", findings=[])
        assert report.passed is True

    def test_passed_with_warnings_only(self):
        report = SecurityReport(target="test", findings=[
            SecurityFinding(check="subprocess_usage", severity="warning", message="test"),
        ])
        assert report.passed is True

    def test_failed_with_critical(self):
        report = SecurityReport(target="test", findings=[
            SecurityFinding(check="eval_call", severity="critical", message="test"),
        ])
        assert report.passed is False

    def test_counts(self):
        report = SecurityReport(target="test", findings=[
            SecurityFinding(check="a", severity="critical", message=""),
            SecurityFinding(check="b", severity="critical", message=""),
            SecurityFinding(check="c", severity="warning", message=""),
            SecurityFinding(check="d", severity="info", message=""),
        ])
        assert report.critical_count == 2
        assert report.warning_count == 1
        assert report.info_count == 1

    def test_summary_format(self):
        report = SecurityReport(target="my-adapter", files_scanned=3)
        s = report.summary()
        assert "my-adapter" in s
        assert "PASSED" in s


# ─── Regex-based checks ───


class TestRegexChecks:
    def test_detects_eval(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("result = eval(user_input)\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "eval_call" and f.severity == "critical" for f in findings)

    def test_detects_exec(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("exec(code_string)\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "exec_call" for f in findings)

    def test_detects_os_system(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("import os\nos.system('rm -rf /')\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "os_system" for f in findings)

    def test_detects_os_popen(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("os.popen('ls')\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "os_popen" for f in findings)

    def test_detects_pickle_load(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("data = pickle.load(fp)\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "pickle_load" for f in findings)

    def test_detects_yaml_unsafe_load(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("data = yaml.unsafe_load(content)\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "yaml_unsafe_load" for f in findings)

    def test_detects_marshal_load(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("data = marshal.loads(raw)\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "marshal_load" for f in findings)

    def test_detects_hardcoded_secret(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("api_key = 'ABCDEF1234567890XXXX'\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "hardcoded_secret" for f in findings)

    def test_detects_subprocess(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text("import subprocess\nsubprocess.run(['ls'])\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "subprocess_usage" and f.severity == "warning" for f in findings)

    def test_detects_compile(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text("code = compile(source, '<string>', 'exec')\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "compile_call" for f in findings)

    def test_detects_dunder_import(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text("mod = __import__('os')\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "dunder_import" for f in findings)

    def test_detects_path_traversal(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text("path = '../../../etc/passwd'\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "path_traversal" for f in findings)

    def test_detects_absolute_system_path(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text("path = '/etc/shadow'\n")
        findings = []
        _scan_file_regex(f, findings)
        assert any(f.check == "absolute_system_path" and f.severity == "info" for f in findings)

    def test_clean_file_has_no_findings(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text(textwrap.dedent("""\
            import json
            from pathlib import Path

            class MyAdapter:
                source_family = "ci"
                def iter_events(self):
                    data = json.loads(Path("data.json").read_text())
                    yield {"source_family": "ci", "payload": data}
        """))
        findings = []
        _scan_file_regex(f, findings)
        assert len(findings) == 0

    def test_line_numbers_are_correct(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("line1\nline2\nresult = eval(x)\nline4\n")
        findings = []
        _scan_file_regex(f, findings)
        assert findings[0].line == 3


# ─── AST-based checks ───


class TestASTChecks:
    def test_detects_network_in_init(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text(textwrap.dedent("""\
            import requests

            class MyAdapter:
                def __init__(self):
                    self.data = requests.get("https://api.example.com")
        """))
        findings = []
        _scan_file_ast(f, findings)
        assert any(f.check == "network_in_init" for f in findings)

    def test_allows_network_outside_init(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text(textwrap.dedent("""\
            import requests

            class MyAdapter:
                def __init__(self):
                    self.url = "https://api.example.com"

                def iter_events(self):
                    data = requests.get(self.url)
                    yield data
        """))
        findings = []
        _scan_file_ast(f, findings)
        assert len(findings) == 0

    def test_detects_import_in_init(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text(textwrap.dedent("""\
            class MyAdapter:
                def __init__(self):
                    import requests
                    self.data = requests.get("https://api.example.com")
        """))
        findings = []
        _scan_file_ast(f, findings)
        assert any(f.check == "network_in_init" for f in findings)

    def test_detects_from_import_in_init(self, tmp_path):
        f = tmp_path / "adapter.py"
        f.write_text(textwrap.dedent("""\
            class MyAdapter:
                def __init__(self):
                    from urllib.request import urlopen
                    self.data = urlopen("https://example.com")
        """))
        findings = []
        _scan_file_ast(f, findings)
        assert any(f.check == "network_in_init" for f in findings)

    def test_syntax_error_file_is_skipped(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def broken(\n")
        findings = []
        _scan_file_ast(f, findings)
        assert len(findings) == 0


# ─── Integration: scan_adapter_source ───


class TestScanAdapterSource:
    def test_scans_directory(self, tmp_path):
        mod_dir = tmp_path / "my_adapter"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text("result = eval('1+1')\n")
        (mod_dir / "helpers.py").write_text("import json\n")

        report = scan_adapter_source(str(mod_dir))
        assert report.files_scanned == 2
        assert report.critical_count >= 1
        assert report.passed is False

    def test_clean_directory_passes(self, tmp_path):
        mod_dir = tmp_path / "clean_adapter"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text("x = 1\n")

        report = scan_adapter_source(str(mod_dir))
        assert report.passed is True
        assert report.files_scanned == 1

    def test_invalid_target_returns_error(self):
        report = scan_adapter_source("nonexistent_module_xyz_12345")
        assert report.error is not None

    def test_findings_sorted_by_severity(self, tmp_path):
        mod_dir = tmp_path / "mixed"
        mod_dir.mkdir()
        (mod_dir / "code.py").write_text(
            "import subprocess\nresult = eval(x)\npath = '/etc/hosts'\n"
        )

        report = scan_adapter_source(str(mod_dir))
        if len(report.findings) >= 2:
            severities = [f.severity for f in report.findings]
            severity_order = {"critical": 0, "warning": 1, "info": 2}
            ordered = [severity_order.get(s, 9) for s in severities]
            assert ordered == sorted(ordered)

    def test_scans_nested_py_files(self, tmp_path):
        mod_dir = tmp_path / "nested"
        mod_dir.mkdir()
        sub = mod_dir / "sub"
        sub.mkdir()
        (mod_dir / "__init__.py").write_text("x = 1\n")
        (sub / "deep.py").write_text("eval('danger')\n")

        report = scan_adapter_source(str(mod_dir))
        assert report.files_scanned == 2
        assert report.critical_count >= 1
