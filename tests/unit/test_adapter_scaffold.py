"""Tests for adapter scaffold and guide."""

import json
from pathlib import Path

import pytest

from evolution.adapter_scaffold import scaffold_adapter, _sanitize_name, _class_name


class TestNameConversion:
    def test_sanitize_simple(self):
        assert _sanitize_name("jenkins") == "jenkins"

    def test_sanitize_hyphens(self):
        assert _sanitize_name("bitbucket-pipelines") == "bitbucket_pipelines"

    def test_sanitize_spaces(self):
        assert _sanitize_name("Azure DevOps") == "azure_devops"

    def test_sanitize_special_chars(self):
        assert _sanitize_name("my.ci@v2") == "my_ci_v2"

    def test_class_name_simple(self):
        assert _class_name("jenkins") == "JenkinsAdapter"

    def test_class_name_hyphenated(self):
        assert _class_name("bitbucket-pipelines") == "BitbucketPipelinesAdapter"

    def test_class_name_underscored(self):
        assert _class_name("azure_devops") == "AzureDevopsAdapter"


class TestScaffold:
    def test_creates_package_structure(self, tmp_path):
        result = scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))

        pkg_dir = Path(result["package_dir"])
        assert pkg_dir.exists()
        assert (pkg_dir / "pyproject.toml").exists()
        assert (pkg_dir / "evo_jenkins" / "__init__.py").exists()
        assert (pkg_dir / "tests" / "test_adapter.py").exists()
        assert (pkg_dir / "README.md").exists()

    def test_pyproject_has_entry_point(self, tmp_path):
        scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))
        content = (tmp_path / "evo-adapter-jenkins" / "pyproject.toml").read_text()
        assert 'evo.adapters' in content
        assert 'jenkins' in content
        assert 'evo_jenkins:register' in content

    def test_adapter_has_register_function(self, tmp_path):
        scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))
        content = (tmp_path / "evo-adapter-jenkins" / "evo_jenkins" / "__init__.py").read_text()
        assert "def register():" in content
        assert "adapter_name" in content
        assert '"ci"' in content

    def test_adapter_has_class(self, tmp_path):
        scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))
        content = (tmp_path / "evo-adapter-jenkins" / "evo_jenkins" / "__init__.py").read_text()
        assert "class JenkinsAdapter:" in content
        assert 'source_family = "ci"' in content
        assert "def iter_events(self):" in content

    def test_tests_reference_correct_class(self, tmp_path):
        scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))
        content = (tmp_path / "evo-adapter-jenkins" / "tests" / "test_adapter.py").read_text()
        assert "from evo_jenkins import JenkinsAdapter" in content
        assert "def test_certification():" in content

    def test_different_family_ci(self, tmp_path):
        result = scaffold_adapter("argocd", "deployment", output_dir=str(tmp_path))
        content = (tmp_path / "evo-adapter-argocd" / "evo_argocd" / "__init__.py").read_text()
        assert 'source_family = "deployment"' in content
        assert "class ArgocdAdapter:" in content
        assert "release_tag" in content  # deployment-specific payload

    def test_different_family_dependency(self, tmp_path):
        result = scaffold_adapter("maven", "dependency", output_dir=str(tmp_path))
        content = (tmp_path / "evo-adapter-maven" / "evo_maven" / "__init__.py").read_text()
        assert 'source_family = "dependency"' in content
        assert "dependencies" in content  # dependency-specific payload

    def test_different_family_security(self, tmp_path):
        scaffold_adapter("snyk", "security", output_dir=str(tmp_path))
        content = (tmp_path / "evo-adapter-snyk" / "evo_snyk" / "__init__.py").read_text()
        assert 'source_family = "security"' in content
        assert "severity" in content  # security-specific payload

    def test_invalid_family_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown family"):
            scaffold_adapter("test", "invalid_family", output_dir=str(tmp_path))

    def test_result_dict(self, tmp_path):
        result = scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))
        assert "package_dir" in result
        assert "adapter_file" in result
        assert "adapter_class_path" in result
        assert result["adapter_class_path"] == "evo_jenkins.JenkinsAdapter"

    def test_readme_content(self, tmp_path):
        scaffold_adapter("jenkins", "ci", output_dir=str(tmp_path))
        readme = (tmp_path / "evo-adapter-jenkins" / "README.md").read_text()
        assert "evo-adapter-jenkins" in readme
        assert "pip install" in readme
        assert "evo adapter validate" in readme


class TestGuide:
    def test_guide_prints(self, capsys):
        from evolution.adapter_scaffold import print_guide
        print_guide()
        captured = capsys.readouterr()
        assert "BUILDING AN EVO ADAPTER PLUGIN" in captured.out
        assert "QUICK START" in captured.out
        assert "ADAPTER CONTRACT" in captured.out
        assert "VALIDATION" in captured.out
        assert "DON'T WANT TO BUILD IT YOURSELF?" in captured.out


class TestAIPrompt:
    def test_prompt_includes_contract(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("jenkins", "ci")
        assert "source_family" in prompt
        assert "source_type" in prompt
        assert "iter_events" in prompt
        assert "trigger" in prompt
        assert "commit_sha" in prompt

    def test_prompt_includes_correct_names(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("jenkins", "ci")
        assert "JenkinsAdapter" in prompt
        assert "evo_jenkins" in prompt
        assert "evo-adapter-jenkins" in prompt
        assert '"ci"' in prompt

    def test_prompt_includes_validation_checklist(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("jenkins", "ci")
        assert "13 checks" in prompt.lower() or "validation" in prompt.lower()
        assert "evo adapter validate" in prompt

    def test_prompt_includes_reference_adapter(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("jenkins", "ci")
        assert "GitHubActionsAdapter" in prompt

    def test_prompt_includes_entry_points(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("jenkins", "ci")
        assert "evo.adapters" in prompt
        assert "register" in prompt
        assert "pyproject.toml" in prompt

    def test_prompt_includes_user_description(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("jenkins", "ci", description="Fetch from Jenkins REST API")
        assert "Fetch from Jenkins REST API" in prompt

    def test_prompt_includes_data_source(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("jenkins", "ci", data_source="https://jenkins.example.com/api")
        assert "https://jenkins.example.com/api" in prompt

    def test_prompt_different_family(self):
        from evolution.adapter_scaffold import generate_ai_prompt
        prompt = generate_ai_prompt("argocd", "deployment")
        assert "ArgocdAdapter" in prompt
        assert '"deployment"' in prompt
        assert "release_tag" in prompt  # deployment-specific payload
