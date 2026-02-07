"""
Git Source Adapter (Reference)

Emits canonical SourceEvent payloads for Git commits.
Conforms strictly to Adapter Contract.
"""

from pathlib import Path
from datetime import datetime
from git import Repo

class GitSourceAdapter:
    source_type = "git"
    ordering_mode = "causal"
    attestation_tier = "strong"

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.repo = Repo(self.repo_path)
        self.source_id = str(self.repo_path)

    def iter_events(self):
        commits = list(self.repo.iter_commits(rev="HEAD"))
        commits.reverse()  # oldest → newest

        for commit in commits:
            files = list(commit.stats.files.keys())
            payload = {
                "commit_hash": commit.hexsha,
                "parent_commits": [p.hexsha for p in commit.parents],
                "author": {
                    "name": commit.author.name,
                    "email": commit.author.email,
                },
                "committer": {
                    "name": commit.committer.name,
                    "email": commit.committer.email,
                },
                "authored_at": datetime.utcfromtimestamp(commit.authored_date).isoformat() + "Z",
                "committed_at": datetime.utcfromtimestamp(commit.committed_date).isoformat() + "Z",
                "message": commit.message,
                "tree_hash": commit.tree.hexsha,
                "files": files,
            }

            yield {
                "source_type": self.source_type,
                "source_id": self.source_id,
                "ordering_mode": self.ordering_mode,
                "attestation": {
                    "type": "git_commit",
                    "commit_hash": commit.hexsha,
                    "trust_tier": self.attestation_tier,
                },
                "predecessor_refs": payload["parent_commits"],
                "payload": payload,
            }
