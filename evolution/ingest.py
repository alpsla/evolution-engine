from pathlib import Path
import json
from datetime import datetime
from git import Repo

EVOLUTION_DIR = ".evolution"
EVENTS_DIR = "events"
DIFFS_DIR = "diffs"
INDEX_DIR = "index"


def ingest_repo(repo_path: str = "."):
    repo_path = Path(repo_path).resolve()
    evo_dir = repo_path / EVOLUTION_DIR

    if not evo_dir.exists():
        raise RuntimeError(".evolution directory not found. Run `evolution init` first.")

    repo = Repo(repo_path)

    events_path = evo_dir / EVENTS_DIR
    diffs_path = evo_dir / DIFFS_DIR
    index_path = evo_dir / INDEX_DIR / "commit_to_event.json"

    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            commit_to_event = json.load(f)
    else:
        commit_to_event = {}

    next_event_id = len(commit_to_event) + 1

    commits = list(repo.iter_commits(rev="HEAD"))
    commits.reverse()  # oldest -> newest

    for commit in commits:
        commit_hash = commit.hexsha

        if commit_hash in commit_to_event:
            continue

        parent_hashes = [p.hexsha for p in commit.parents]
        is_merge = len(parent_hashes) > 1

        event = {
            "event_id": next_event_id,
            "commit_hash": commit_hash,
            "parent_hashes": parent_hashes,
            "timestamp": datetime.utcfromtimestamp(commit.committed_date).isoformat() + "Z",
            "author": {
                "name": commit.author.name,
                "email": commit.author.email,
            },
        }

        if is_merge:
            event["event_type"] = "merge"
            event["merge"] = {
                "parent_count": len(parent_hashes)
            }
        else:
            event["event_type"] = "change"
            stats = commit.stats.total
            files = commit.stats.files

            modules = set()
            for path in files:
                parts = Path(path).parts
                if parts:
                    modules.add(parts[0])

            event["metrics"] = {
                "files_touched": len(files),
                "modules_touched": len(modules),
                "lines_added": stats.get("insertions", 0),
                "lines_removed": stats.get("deletions", 0),
                "churn": stats.get("insertions", 0) + stats.get("deletions", 0),
                "net_delta": stats.get("insertions", 0) - stats.get("deletions", 0),
                "dispersion": None,  # to be implemented
                "scope_ratio": None,  # to be implemented
            }

            diff_text = repo.git.show(commit_hash)
            diff_file = diffs_path / f"{commit_hash}.patch"
            with open(diff_file, "w", encoding="utf-8") as df:
                df.write(diff_text)

            event["diff_ref"] = str(diff_file.relative_to(evo_dir))

        event_file = events_path / f"{next_event_id:08d}.json"
        with open(event_file, "w", encoding="utf-8") as ef:
            json.dump(event, ef, indent=2)

        commit_to_event[commit_hash] = next_event_id
        next_event_id += 1

    index_path.parent.mkdir(exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(commit_to_event, f, indent=2)

    print(f"✅ Ingested {len(commit_to_event)} events")
