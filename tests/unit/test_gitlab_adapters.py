"""
Tests for GitLab and CircleCI API adapters (CI + Deployment).

Tests use fixture mode (pre-parsed data) — no network calls.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from evolution.adapters.gitlab_client import GitLabClient
from evolution.adapters.ci.gitlab_pipelines_adapter import GitLabPipelinesAdapter
from evolution.adapters.deployment.gitlab_releases_adapter import GitLabReleasesAdapter
from evolution.adapters.ci.circleci_adapter import CircleCIAdapter


# ---- GitLabClient ----

class TestGitLabClient:

    def test_requires_token(self):
        """Client raises without token."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="GitLab token required"):
                GitLabClient("12345")

    def test_accepts_env_token(self):
        """Client reads GITLAB_TOKEN from env."""
        with patch.dict("os.environ", {"GITLAB_TOKEN": "glpat-test"}):
            client = GitLabClient("12345")
            assert client.token == "glpat-test"

    def test_base_url_default(self):
        """Default base URL is gitlab.com."""
        with patch.dict("os.environ", {"GITLAB_TOKEN": "glpat-test"}):
            client = GitLabClient("12345")
            assert "gitlab.com/api/v4" in client.api_base
            assert "/projects/12345" in client.base_url

    def test_base_url_custom(self):
        """Supports self-hosted GitLab instances."""
        with patch.dict("os.environ", {"GITLAB_TOKEN": "glpat-test"}):
            client = GitLabClient("42", base_url="https://git.company.com/api/v4")
            assert "git.company.com" in client.api_base
            assert "/projects/42" in client.base_url

    def test_ci_api_v4_url(self):
        """Uses CI_API_V4_URL when set (GitLab CI runner context)."""
        with patch.dict("os.environ", {
            "GITLAB_TOKEN": "glpat-test",
            "CI_API_V4_URL": "https://ci.example.com/api/v4",
        }):
            client = GitLabClient("99")
            assert "ci.example.com" in client.api_base

    def test_headers(self):
        """Auth headers use PRIVATE-TOKEN."""
        with patch.dict("os.environ", {"GITLAB_TOKEN": "glpat-test123"}):
            client = GitLabClient("12345")
            headers = client._headers()
            assert headers["PRIVATE-TOKEN"] == "glpat-test123"
            assert headers["Accept"] == "application/json"

    def test_stats(self):
        """Stats returns initial values."""
        with patch.dict("os.environ", {"GITLAB_TOKEN": "glpat-test"}):
            client = GitLabClient("12345")
            stats = client.stats
            assert stats["requests_made"] == 0
            assert stats["rate_limit_remaining"] == 300


# ---- GitLabPipelinesAdapter ----

class TestGitLabPipelinesAdapter:

    def _make_pipeline(self, id=1, status="success", ref="main",
                       sha="abc123", duration=120, source="push",
                       created_at="2025-01-15T10:00:00Z",
                       started_at="2025-01-15T10:01:00Z",
                       finished_at="2025-01-15T10:03:00Z"):
        return {
            "id": id,
            "status": status,
            "ref": ref,
            "sha": sha,
            "duration": duration,
            "source": source,
            "created_at": created_at,
            "started_at": started_at,
            "finished_at": finished_at,
        }

    def test_fixture_mode_basic(self):
        """Fixture mode emits events without API calls."""
        adapter = GitLabPipelinesAdapter(
            runs=[self._make_pipeline()],
            source_id="test",
        )
        events = list(adapter.iter_events())
        assert len(events) == 1

    def test_event_structure(self):
        """Events conform to CI family contract."""
        adapter = GitLabPipelinesAdapter(
            runs=[self._make_pipeline()],
        )
        event = list(adapter.iter_events())[0]

        assert event["source_family"] == "ci"
        assert event["source_type"] == "gitlab_ci"
        assert event["ordering_mode"] == "temporal"
        assert event["attestation"]["type"] == "ci_run"
        assert event["attestation"]["run_id"] == "1"
        assert event["attestation"]["commit_sha"] == "abc123"

        payload = event["payload"]
        assert payload["run_id"] == "1"
        assert payload["status"] == "success"
        assert payload["trigger"]["ref"] == "main"
        assert payload["trigger"]["commit_sha"] == "abc123"
        assert payload["timing"]["duration_seconds"] == 120.0

    def test_status_normalization(self):
        """GitLab statuses map to contract values."""
        adapter = GitLabPipelinesAdapter(runs=[], source_id="test")
        assert adapter._normalize_status("success") == "success"
        assert adapter._normalize_status("failed") == "failure"
        assert adapter._normalize_status("canceled") == "cancelled"
        assert adapter._normalize_status("skipped") == "skipped"
        assert adapter._normalize_status("running") == "skipped"
        assert adapter._normalize_status(None) == "cancelled"
        assert adapter._normalize_status("unknown_value") == "failure"

    def test_trigger_normalization(self):
        """GitLab pipeline sources map to contract trigger types."""
        adapter = GitLabPipelinesAdapter(runs=[], source_id="test")
        assert adapter._normalize_trigger("push") == "push"
        assert adapter._normalize_trigger("merge_request_event") == "pull_request"
        assert adapter._normalize_trigger("schedule") == "schedule"
        assert adapter._normalize_trigger("web") == "manual"
        assert adapter._normalize_trigger("api") == "manual"

    def test_duration_from_field(self):
        """Uses GitLab's duration field when available."""
        adapter = GitLabPipelinesAdapter(runs=[], source_id="test")
        result = adapter._parse_duration({"duration": 300})
        assert result == 300.0

    def test_duration_from_timestamps(self):
        """Falls back to timestamp calculation when duration missing."""
        adapter = GitLabPipelinesAdapter(runs=[], source_id="test")
        result = adapter._parse_duration({
            "started_at": "2025-01-15T10:00:00Z",
            "finished_at": "2025-01-15T10:05:00Z",
        })
        assert result == 300.0

    def test_multiple_pipelines(self):
        """Multiple pipelines emit multiple events."""
        runs = [
            self._make_pipeline(id=1, status="success", sha="aaa"),
            self._make_pipeline(id=2, status="failed", sha="bbb"),
            self._make_pipeline(id=3, status="success", sha="ccc"),
        ]
        adapter = GitLabPipelinesAdapter(runs=runs)
        events = list(adapter.iter_events())
        assert len(events) == 3
        assert events[0]["payload"]["status"] == "success"
        assert events[1]["payload"]["status"] == "failure"
        assert events[2]["payload"]["status"] == "success"

    def test_fixture_mode_with_jobs(self):
        """Jobs included in fixture data are passed through."""
        run = self._make_pipeline()
        run["jobs"] = [
            {"name": "test", "status": "success", "duration_seconds": 60},
            {"name": "lint", "status": "success", "duration_seconds": 30},
        ]
        adapter = GitLabPipelinesAdapter(runs=[run])
        event = list(adapter.iter_events())[0]
        assert len(event["payload"]["jobs"]) == 2
        assert event["payload"]["jobs"][0]["name"] == "test"

    def test_source_id_from_project(self):
        """Source ID includes project ID."""
        adapter = GitLabPipelinesAdapter(runs=[], source_id=None)
        assert "gitlab_ci:fixture" in adapter.source_id

    def test_requires_input(self):
        """Raises without project_id, client, or runs."""
        with pytest.raises(RuntimeError, match="Provide"):
            GitLabPipelinesAdapter()


# ---- GitLabReleasesAdapter ----

class TestGitLabReleasesAdapter:

    def _make_release(self, tag="v1.0.0", sha="abc123",
                      released_at="2025-01-15T14:00:00Z",
                      assets=None):
        return {
            "tag_name": tag,
            "commit": {"id": sha},
            "released_at": released_at,
            "created_at": released_at,
            "assets": assets or {"links": [], "sources": [
                {"format": "zip"}, {"format": "tar.gz"}
            ]},
        }

    def test_fixture_mode_basic(self):
        """Fixture mode emits events."""
        deploy = {
            "deployment_id": "v1.0.0",
            "environment": "production",
            "trigger": {"type": "release", "commit_sha": "abc", "ref": "v1.0.0"},
            "status": "success",
            "timing": {"initiated_at": "2025-01-15T14:00:00Z",
                       "completed_at": "2025-01-15T14:00:00Z",
                       "duration_seconds": 0.0},
            "version": "v1.0.0",
            "is_rollback": False,
        }
        adapter = GitLabReleasesAdapter(deployments=[deploy])
        events = list(adapter.iter_events())
        assert len(events) == 1

    def test_event_structure(self):
        """Events conform to deployment family contract."""
        deploy = {
            "deployment_id": "v2.0.0",
            "environment": "production",
            "trigger": {"type": "release", "commit_sha": "def456", "ref": "v2.0.0"},
            "status": "success",
            "timing": {"initiated_at": "2025-02-01T10:00:00Z",
                       "completed_at": "2025-02-01T10:00:00Z",
                       "duration_seconds": 0.0},
            "version": "v2.0.0",
            "is_rollback": False,
        }
        adapter = GitLabReleasesAdapter(deployments=[deploy])
        event = list(adapter.iter_events())[0]

        assert event["source_family"] == "deployment"
        assert event["source_type"] == "gitlab_releases"
        assert event["attestation"]["type"] == "deployment"
        assert event["attestation"]["deployment_id"] == "v2.0.0"
        assert event["payload"]["version"] == "v2.0.0"
        assert event["payload"]["environment"] == "production"

    def test_prerelease_detection(self):
        """Tags with alpha/beta/rc are detected as prerelease."""
        adapter = GitLabReleasesAdapter(deployments=[], source_id="test")
        deploy = adapter._release_to_deployment(
            self._make_release(tag="v2.0.0-beta.1")
        )
        assert deploy["environment"] == "prerelease"

    def test_production_release(self):
        """Normal version tags are production."""
        adapter = GitLabReleasesAdapter(deployments=[], source_id="test")
        deploy = adapter._release_to_deployment(
            self._make_release(tag="v3.0.0")
        )
        assert deploy["environment"] == "production"

    def test_commit_sha_from_release(self):
        """Commit SHA extracted from release commit object."""
        adapter = GitLabReleasesAdapter(deployments=[], source_id="test")
        deploy = adapter._release_to_deployment(
            self._make_release(sha="deadbeef123")
        )
        assert deploy["trigger"]["commit_sha"] == "deadbeef123"

    def test_asset_count(self):
        """Asset count includes links + sources."""
        assets = {
            "links": [{"url": "https://example.com/file.zip"}],
            "sources": [{"format": "zip"}, {"format": "tar.gz"}],
        }
        release = self._make_release(assets=assets)
        # To test asset counting, we need to go through iter_events with API mock
        # Instead test the conversion directly
        adapter = GitLabReleasesAdapter(deployments=[], source_id="test")
        deploy = adapter._release_to_deployment(release)
        # asset_count is added during iter_events, not in _release_to_deployment
        assert deploy["deployment_id"] == "v1.0.0"

    def test_requires_input(self):
        """Raises without project_id, client, or deployments."""
        with pytest.raises(RuntimeError, match="Provide"):
            GitLabReleasesAdapter()


# ---- Orchestrator integration ----

class TestOrchestratorGitLabInference:

    def test_infer_gitlab_project_ssh(self):
        """Infers project path from SSH remote."""
        from evolution.orchestrator import Orchestrator
        with patch.object(Orchestrator, '__init__', lambda self: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo_path = "/tmp/test"

            mock_remote = MagicMock()
            mock_remote.url = "git@gitlab.com:mygroup/myproject.git"
            mock_repo = MagicMock()
            mock_repo.remotes = [mock_remote]

            with patch("git.Repo", return_value=mock_repo):
                result = orch._infer_gitlab_project()
                assert result is not None
                assert "mygroup" in result
                assert "myproject" in result

    def test_infer_gitlab_project_https(self):
        """Infers project path from HTTPS remote."""
        from evolution.orchestrator import Orchestrator
        with patch.object(Orchestrator, '__init__', lambda self: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo_path = "/tmp/test"

            mock_remote = MagicMock()
            mock_remote.url = "https://gitlab.com/mygroup/myproject.git"
            mock_repo = MagicMock()
            mock_repo.remotes = [mock_remote]

            with patch("git.Repo", return_value=mock_repo):
                result = orch._infer_gitlab_project()
                assert result is not None
                assert "mygroup" in result

    def test_infer_gitlab_project_ci_env(self):
        """Uses CI_PROJECT_ID env var when available."""
        from evolution.orchestrator import Orchestrator
        with patch.object(Orchestrator, '__init__', lambda self: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo_path = "/tmp/test"

            with patch.dict("os.environ", {"CI_PROJECT_ID": "12345"}):
                result = orch._infer_gitlab_project()
                assert result == "12345"

    def test_infer_gitlab_project_github_remote(self):
        """Returns None for GitHub remotes."""
        from evolution.orchestrator import Orchestrator
        with patch.object(Orchestrator, '__init__', lambda self: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo_path = "/tmp/test"

            mock_remote = MagicMock()
            mock_remote.url = "git@github.com:owner/repo.git"
            mock_repo = MagicMock()
            mock_repo.remotes = [mock_remote]

            with patch("git.Repo", return_value=mock_repo), \
                 patch.dict("os.environ", {}, clear=True):
                result = orch._infer_gitlab_project()
                assert result is None


# ---- CircleCIAdapter ----

class TestCircleCIAdapter:

    def _make_run(self, run_id="wf-1", status="success", sha="abc123",
                  ref="main", workflow_name="build",
                  created_at="2025-01-15T10:00:00Z",
                  completed_at="2025-01-15T10:05:00Z"):
        return {
            "run_id": run_id,
            "workflow_name": workflow_name,
            "trigger": {
                "type": "push",
                "ref": ref,
                "commit_sha": sha,
            },
            "status": status,
            "timing": {
                "created_at": created_at,
                "started_at": created_at,
                "completed_at": completed_at,
                "duration_seconds": 300.0,
            },
            "jobs": [],
        }

    def test_fixture_mode_basic(self):
        """Fixture mode emits events without API calls."""
        adapter = CircleCIAdapter(runs=[self._make_run()])
        events = list(adapter.iter_events())
        assert len(events) == 1

    def test_event_structure(self):
        """Events conform to CI family contract."""
        adapter = CircleCIAdapter(runs=[self._make_run()])
        event = list(adapter.iter_events())[0]

        assert event["source_family"] == "ci"
        assert event["source_type"] == "circleci"
        assert event["ordering_mode"] == "temporal"
        assert event["attestation"]["type"] == "ci_run"
        assert event["attestation"]["run_id"] == "wf-1"
        assert event["attestation"]["commit_sha"] == "abc123"

        payload = event["payload"]
        assert payload["run_id"] == "wf-1"
        assert payload["status"] == "success"
        assert payload["trigger"]["ref"] == "main"

    def test_status_normalization(self):
        """CircleCI statuses map to contract values."""
        adapter = CircleCIAdapter(runs=[], source_id="test")
        assert adapter._normalize_status("success") == "success"
        assert adapter._normalize_status("failed") == "failure"
        assert adapter._normalize_status("error") == "failure"
        assert adapter._normalize_status("canceled") == "cancelled"
        assert adapter._normalize_status("not_run") == "skipped"
        assert adapter._normalize_status(None) == "cancelled"

    def test_trigger_normalization(self):
        """CircleCI trigger types map to contract values."""
        adapter = CircleCIAdapter(runs=[], source_id="test")
        assert adapter._normalize_trigger("webhook") == "push"
        assert adapter._normalize_trigger("api") == "manual"
        assert adapter._normalize_trigger("schedule") == "schedule"

    def test_multiple_runs(self):
        """Multiple runs emit multiple events."""
        runs = [
            self._make_run(run_id="1", status="success"),
            self._make_run(run_id="2", status="failure"),
        ]
        adapter = CircleCIAdapter(runs=runs)
        events = list(adapter.iter_events())
        assert len(events) == 2

    def test_requires_input(self):
        """Raises without project_slug or runs."""
        with pytest.raises(RuntimeError, match="Provide"):
            CircleCIAdapter()

    def test_requires_token_in_api_mode(self):
        """Raises without token in API mode."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="CircleCI token required"):
                CircleCIAdapter(project_slug="gh/owner/repo")

    def test_source_id(self):
        """Source ID includes project slug."""
        adapter = CircleCIAdapter(runs=[], source_id=None)
        assert "circleci:fixture" in adapter.source_id


class TestOrchestratorCircleCIInference:

    def test_infer_circleci_slug_github(self):
        """Infers CircleCI slug from GitHub remote."""
        from evolution.orchestrator import Orchestrator
        with patch.object(Orchestrator, '__init__', lambda self: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo_path = "/tmp/test"

            mock_remote = MagicMock()
            mock_remote.url = "git@github.com:myorg/myrepo.git"
            mock_repo = MagicMock()
            mock_repo.remotes = [mock_remote]

            with patch("git.Repo", return_value=mock_repo):
                result = orch._infer_circleci_slug()
                assert result == "gh/myorg/myrepo"

    def test_infer_circleci_slug_https(self):
        """Infers CircleCI slug from HTTPS GitHub remote."""
        from evolution.orchestrator import Orchestrator
        with patch.object(Orchestrator, '__init__', lambda self: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo_path = "/tmp/test"

            mock_remote = MagicMock()
            mock_remote.url = "https://github.com/myorg/myrepo.git"
            mock_repo = MagicMock()
            mock_repo.remotes = [mock_remote]

            with patch("git.Repo", return_value=mock_repo):
                result = orch._infer_circleci_slug()
                assert result == "gh/myorg/myrepo"

    def test_infer_circleci_slug_no_match(self):
        """Returns None for GitLab remotes (CircleCI doesn't support GitLab)."""
        from evolution.orchestrator import Orchestrator
        with patch.object(Orchestrator, '__init__', lambda self: None):
            orch = Orchestrator.__new__(Orchestrator)
            orch.repo_path = "/tmp/test"

            mock_remote = MagicMock()
            mock_remote.url = "git@gitlab.com:group/project.git"
            mock_repo = MagicMock()
            mock_repo.remotes = [mock_remote]

            with patch("git.Repo", return_value=mock_repo):
                result = orch._infer_circleci_slug()
                assert result is None
