"""Tests for evo sources CLI command and evo adapter discover."""

import os
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from evolution.cli import main
from evolution.prescan import DetectedService


@pytest.fixture
def runner():
    return CliRunner()


def _mock_registry_detect(tokens=None):
    """Return an empty connected list (no adapters connected)."""
    return []


def _make_service(service, display_name, family, adapter):
    return DetectedService(
        service=service,
        display_name=display_name,
        family=family,
        adapter=adapter,
        detection_layers=["config"],
        evidence=[f"{service} config found"],
    )


# ─── Token hint tests (Task #46) ───


class TestSourcesTokenHints:
    """Token hints should be dynamic, based on TIER2_DETECTORS."""

    def test_sources_github_token_hint(self, runner, tmp_path):
        """When GITHUB_TOKEN is not set, show hint for it."""
        with patch("evolution.prescan.SourcePrescan") as mock_prescan, \
             patch("evolution.registry.AdapterRegistry") as mock_registry, \
             patch("dotenv.load_dotenv", return_value=None), \
             patch.dict("os.environ", {}, clear=False):
            # Ensure tokens are not set
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GITLAB_TOKEN", None)
            os.environ.pop("CIRCLECI_TOKEN", None)
            os.environ.pop("JENKINS_URL", None)

            mock_registry.return_value.detect.return_value = []
            mock_prescan.return_value.scan.return_value = []

            result = runner.invoke(main, ["sources", str(tmp_path)])

        assert result.exit_code == 0
        assert "Set GITHUB_TOKEN to unlock:" in result.output
        assert "ci" in result.output

    def test_sources_gitlab_token_hint(self, runner, tmp_path):
        """When GITLAB_TOKEN is not set, show hint for it."""
        with patch("evolution.prescan.SourcePrescan") as mock_prescan, \
             patch("evolution.registry.AdapterRegistry") as mock_registry, \
             patch("dotenv.load_dotenv", return_value=None), \
             patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GITLAB_TOKEN", None)
            os.environ.pop("CIRCLECI_TOKEN", None)
            os.environ.pop("JENKINS_URL", None)

            mock_registry.return_value.detect.return_value = []
            mock_prescan.return_value.scan.return_value = []

            result = runner.invoke(main, ["sources", str(tmp_path)])

        assert result.exit_code == 0
        assert "Set GITLAB_TOKEN to unlock:" in result.output

    def test_sources_hides_hint_when_token_set(self, runner, tmp_path):
        """When GITHUB_TOKEN is set, don't show hint for it."""
        with patch("evolution.prescan.SourcePrescan") as mock_prescan, \
             patch("evolution.registry.AdapterRegistry") as mock_registry, \
             patch("dotenv.load_dotenv", return_value=None), \
             patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_fake123"}, clear=False):
            os.environ.pop("GITLAB_TOKEN", None)
            os.environ.pop("CIRCLECI_TOKEN", None)
            os.environ.pop("JENKINS_URL", None)

            mock_registry.return_value.detect.return_value = []
            mock_prescan.return_value.scan.return_value = []

            result = runner.invoke(main, ["sources", str(tmp_path)])

        assert result.exit_code == 0
        assert "Set GITHUB_TOKEN" not in result.output
        # But GITLAB_TOKEN hint should still appear
        assert "Set GITLAB_TOKEN" in result.output


# ─── Third-party adapter hints (Task #46) ───


class TestSourcesThirdParty:
    """Third-party services should show PyPI availability."""

    def test_sources_third_party_on_pypi(self, runner, tmp_path):
        """When adapter is on PyPI, show install command."""
        svc = _make_service("datadog", "Datadog", "monitoring", "evo-adapter-datadog")

        with patch("evolution.prescan.SourcePrescan") as mock_prescan, \
             patch("evolution.registry.AdapterRegistry") as mock_registry, \
             patch("evolution.adapter_versions.check_pypi_version", return_value="0.1.0"), \
             patch.dict("os.environ", {"GITHUB_TOKEN": "x"}, clear=False):
            mock_registry.return_value.detect.return_value = []
            mock_prescan.return_value.scan.return_value = [svc]

            result = runner.invoke(main, ["sources", str(tmp_path)])

        assert result.exit_code == 0
        assert "pip install evo-adapter-datadog" in result.output
        assert "Datadog" in result.output

    def test_sources_third_party_not_on_pypi(self, runner, tmp_path):
        """When adapter is NOT on PyPI, show scaffold hint."""
        svc = _make_service("sentry", "Sentry", "error_tracking", "evo-adapter-sentry")

        with patch("evolution.prescan.SourcePrescan") as mock_prescan, \
             patch("evolution.registry.AdapterRegistry") as mock_registry, \
             patch("evolution.adapter_versions.check_pypi_version", return_value=None), \
             patch.dict("os.environ", {"GITHUB_TOKEN": "x"}, clear=False):
            mock_registry.return_value.detect.return_value = []
            mock_prescan.return_value.scan.return_value = [svc]

            result = runner.invoke(main, ["sources", str(tmp_path)])

        assert result.exit_code == 0
        assert "community adapter in development" in result.output
        assert "evo adapter new sentry --family error_tracking" in result.output


# ─── evo adapter discover header (Task #48) ───


class TestAdapterDiscoverHeader:
    """The 'not published' section header should be friendlier."""

    def test_adapter_discover_not_published_header(self, runner, tmp_path):
        """Not-published adapters should show friendly header."""
        from unittest.mock import MagicMock

        svc = _make_service("sentry", "Sentry", "error_tracking", "evo-adapter-sentry")
        mock_eps = MagicMock()
        mock_eps.select.return_value = []

        with patch("evolution.prescan.SourcePrescan") as mock_prescan, \
             patch("evolution.adapter_versions.check_pypi_version", return_value=None), \
             patch("importlib.metadata.entry_points", return_value=mock_eps):
            mock_prescan.return_value.scan.return_value = [svc]

            result = runner.invoke(main, ["adapter", "discover", str(tmp_path)])

        assert result.exit_code == 0
        assert "Community adapters" in result.output
        assert "Not yet on PyPI" not in result.output
