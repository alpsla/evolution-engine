"""Unit tests for agent abstraction layer."""

import os
from unittest.mock import MagicMock, patch

import pytest

from evolution.agents.base import (
    AgentResult,
    BaseAgent,
    ShowPromptAgent,
    get_agent,
)


class TestAgentResult:
    def test_default_success(self):
        r = AgentResult(text="hello")
        assert r.success is True
        assert r.error is None
        assert r.text == "hello"

    def test_failure(self):
        r = AgentResult(text="", success=False, error="boom")
        assert r.success is False
        assert r.error == "boom"

    def test_usage_tracking(self):
        r = AgentResult(
            text="test",
            model="claude-sonnet-4-5-20250929",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        assert r.model == "claude-sonnet-4-5-20250929"
        assert r.usage["input_tokens"] == 100


class TestShowPromptAgent:
    def test_returns_prompt_as_text(self):
        agent = ShowPromptAgent()
        result = agent.complete("investigate this code", system="You are an expert")
        assert result.text == "investigate this code"
        assert result.success is True
        assert result.model == "manual"

    def test_name(self):
        assert ShowPromptAgent().name == "show-prompt"

    def test_cannot_edit_files(self):
        assert ShowPromptAgent().can_edit_files is False


class TestGetAgent:
    def test_prefer_show_prompt(self):
        agent = get_agent(prefer="show-prompt")
        assert isinstance(agent, ShowPromptAgent)

    @patch.dict(os.environ, {}, clear=True)
    @patch("shutil.which", return_value=None)
    def test_fallback_to_show_prompt(self, mock_which):
        """When no API key and no CLI, falls back to ShowPromptAgent."""
        agent = get_agent()
        assert isinstance(agent, ShowPromptAgent)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"})
    def test_prefer_anthropic_when_key_available(self):
        """With API key, should prefer AnthropicAgent."""
        try:
            agent = get_agent(prefer="anthropic", api_key="sk-test")
            assert "anthropic" in agent.name
        except ImportError:
            pytest.skip("anthropic package not installed")

    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_prefer_cli_when_available(self, mock_which):
        from evolution.agents.cli_agent import CliAgent
        agent = get_agent(prefer="cli")
        assert isinstance(agent, CliAgent)

    def test_explicit_api_key(self):
        try:
            agent = get_agent(api_key="sk-ant-test123")
            assert "anthropic" in agent.name or isinstance(agent, ShowPromptAgent)
        except ImportError:
            pytest.skip("anthropic package not installed")

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch.dict(os.environ, {}, clear=True)
    def test_cli_detection_on_path(self, mock_which):
        """Auto-detects claude CLI on PATH."""
        agent = get_agent()
        # Should find CLI before falling back
        from evolution.agents.cli_agent import CliAgent
        assert isinstance(agent, CliAgent)


class TestCliAgent:
    def test_name(self):
        from evolution.agents.cli_agent import CliAgent
        agent = CliAgent(command="claude")
        assert agent.name == "cli (claude)"

    def test_can_edit_files(self):
        from evolution.agents.cli_agent import CliAgent
        agent = CliAgent()
        assert agent.can_edit_files is True

    @patch("subprocess.run")
    def test_complete_calls_subprocess(self, mock_run):
        from evolution.agents.cli_agent import CliAgent
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="The root cause is...",
            stderr="",
        )

        agent = CliAgent(command="claude")
        result = agent.complete("investigate this")

        assert result.success is True
        assert result.text == "The root cause is..."
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_complete_with_files(self, mock_run):
        from evolution.agents.cli_agent import CliAgent
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Fixed the issue",
            stderr="",
        )

        agent = CliAgent(command="claude")
        result = agent.complete_with_files(
            prompt="fix this",
            working_dir="/tmp/repo",
        )

        assert result.success is True
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["cwd"] == "/tmp/repo"

    @patch("subprocess.run")
    def test_nonzero_exit_code(self, mock_run):
        from evolution.agents.cli_agent import CliAgent
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Authentication failed",
        )

        agent = CliAgent()
        result = agent.complete("test")

        assert result.success is False
        assert "Authentication failed" in result.error

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_command_not_found(self, mock_run):
        from evolution.agents.cli_agent import CliAgent
        agent = CliAgent(command="nonexistent-tool")
        result = agent.complete("test")

        assert result.success is False
        assert "not found" in result.error.lower()

    @patch("subprocess.run", side_effect=Exception("timeout"))
    def test_generic_exception(self, mock_run):
        from evolution.agents.cli_agent import CliAgent
        agent = CliAgent()
        result = agent.complete("test")
        assert result.success is False
