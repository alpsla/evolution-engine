"""
Test Git History Walker

Verifies that walking git history extracts dependency/schema/config
snapshots and Phase 2 generates signals for all families.
"""

import shutil
import tempfile
import json
from pathlib import Path
from git import Repo

from evolution.phase1_engine import Phase1Engine
from evolution.phase2_engine import Phase2Engine
from evolution.adapters.git.git_adapter import GitSourceAdapter
from evolution.adapters.git.git_history_walker import GitHistoryWalker


def setup_test_repo():
    """Create a test repo with evolving requirements.txt."""
    temp_dir = Path(tempfile.mkdtemp())
    repo = Repo.init(temp_dir)
    
    # Configure git (required for commits)
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")
    
    # Commit 1: Initial requirements
    (temp_dir / "requirements.txt").write_text("requests==2.25.0\nflask==1.1.2\n")
    repo.index.add(["requirements.txt"])
    repo.index.commit("Initial dependencies")
    
    # Commit 2: Add new dependency
    (temp_dir / "requirements.txt").write_text("requests==2.25.0\nflask==1.1.2\ndjango==3.1.0\n")
    repo.index.add(["requirements.txt"])
    repo.index.commit("Add Django")
    
    # Commit 3: Upgrade Flask
    (temp_dir / "requirements.txt").write_text("requests==2.25.0\nflask==2.0.0\ndjango==3.1.0\n")
    repo.index.add(["requirements.txt"])
    repo.index.commit("Upgrade Flask")
    
    return temp_dir


def test_git_history_walker_extracts_dependencies():
    """Test that walker extracts historical dependency snapshots."""
    repo_dir = setup_test_repo()
    evo_dir = repo_dir / ".evo"
    
    try:
        # Phase 1: Ingest git + historical dependencies
        phase1 = Phase1Engine(evo_dir)
        
        # Ingest git commits
        git_adapter = GitSourceAdapter(repo_path=str(repo_dir))
        git_count = phase1.ingest(git_adapter)
        assert git_count == 3, f"Should have 3 git commits, got {git_count}"
        
        # Walk history and extract dependencies
        walker = GitHistoryWalker(
            repo_path=str(repo_dir),
            target_families=['dependency']
        )
        dep_count = 0
        for commit, family, adapter, committed_at in walker.iter_commit_events():
            count = phase1.ingest(adapter, override_observed_at=committed_at)
            dep_count += count
        
        assert dep_count == 3, f"Should extract 3 dependency snapshots, got {dep_count}"
        
        # Verify events have correct observed_at timestamps
        events = []
        for event_file in (evo_dir / "events").glob("*.json"):
            events.append(json.loads(event_file.read_text()))
        
        dep_events = [e for e in events if e.get("source_family") == "dependency"]
        assert len(dep_events) == 3, f"Should have 3 dependency events, got {len(dep_events)}"
        
        # Verify timestamps are non-empty (ordering may vary for same-second commits)
        timestamps = [e["observed_at"] for e in dep_events]
        assert all(ts for ts in timestamps), "All events should have timestamps"
        
        # Verify trigger.commit_sha is present
        for e in dep_events:
            assert e["payload"]["trigger"]["commit_sha"], "Should have commit SHA"
        
        print("✅ test_git_history_walker_extracts_dependencies passed")
        
    finally:
        shutil.rmtree(repo_dir)


def test_phase2_generates_signals_for_all_families():
    """Test that Phase 2 generates signals for dependency family (not just git)."""
    repo_dir = setup_test_repo()
    evo_dir = repo_dir / ".evo"
    
    try:
        # Phase 1: Ingest git + dependencies
        phase1 = Phase1Engine(evo_dir)
        
        git_adapter = GitSourceAdapter(repo_path=str(repo_dir))
        phase1.ingest(git_adapter)
        
        walker = GitHistoryWalker(
            repo_path=str(repo_dir),
            target_families=['dependency']
        )
        for commit, family, adapter, committed_at in walker.iter_commit_events():
            phase1.ingest(adapter, override_observed_at=committed_at)
        
        # Phase 2: Run all families
        phase2 = Phase2Engine(evo_dir, window_size=2, min_baseline=1)
        results = phase2.run_all()
        
        # Verify signals exist for multiple families
        families_with_signals = set()
        for family, signals in results.items():
            if signals:
                families_with_signals.add(family)
        
        assert "git" in families_with_signals, "Should have git signals"
        assert "dependency" in families_with_signals, "Should have dependency signals"
        
        print(f"✅ Phase 2 generated signals for families: {families_with_signals}")
        print("✅ test_phase2_generates_signals_for_all_families passed")
        
    finally:
        shutil.rmtree(repo_dir)


if __name__ == "__main__":
    print("Running Git History Walker tests...\n")
    test_git_history_walker_extracts_dependencies()
    test_phase2_generates_signals_for_all_families()
    print("\n✅ All tests passed")
