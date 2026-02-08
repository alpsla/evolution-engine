#!/usr/bin/env python3
"""
Repository Search Agent — Automated Multi-Family Data Discovery

Searches GitHub for repositories with maximum multi-family data coverage,
validates each across 8 source families, and ranks by suitability for
Evolution Engine calibration.

Usage:
    python search_agent.py --min-stars 1000 --max-repos 200 --output repos_ranked.csv

Output:
    CSV with 100+ repos ranked by family coverage score
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class RepoCandidate:
    """Repository candidate with multi-family validation results."""
    owner: str
    repo: str
    language: str
    stars: int
    forks: int
    commits: int
    last_updated: str
    
    # Family availability (True/False)
    has_git: bool = False
    has_ci: bool = False
    has_dependencies: bool = False
    has_testing: bool = False
    has_schema: bool = False
    has_deployment: bool = False
    has_config: bool = False
    has_security: bool = False
    
    # Family metrics
    ci_runs: int = 0
    releases: int = 0
    test_files: int = 0
    lockfile_path: str = ""
    lockfile_commits: int = 0
    schema_path: str = ""
    schema_commits: int = 0
    config_path: str = ""
    config_commits: int = 0
    
    # Scoring
    family_count: int = 0
    calibration_score: float = 0.0
    
    def calculate_score(self):
        """Calculate calibration suitability score (0-100)."""
        # Count families
        families = [
            self.has_git, self.has_ci, self.has_dependencies,
            self.has_testing, self.has_schema, self.has_deployment,
            self.has_config, self.has_security
        ]
        self.family_count = sum(families)
        
        # Base score: family coverage (0-80 points, 10 per family)
        family_score = self.family_count * 10
        
        # Bonus: commit count (0-10 points)
        if self.commits >= 1000:
            commit_score = 10
        elif self.commits >= 500:
            commit_score = 5
        else:
            commit_score = max(0, (self.commits / 500) * 5)
        
        # Bonus: lockfile history depth (0-5 points)
        lockfile_score = min(5, self.lockfile_commits / 20)
        
        # Bonus: CI runs (0-5 points)
        ci_score = min(5, self.ci_runs / 100)
        
        self.calibration_score = family_score + commit_score + lockfile_score + ci_score


class GitHubSearchAgent:
    """Automated repository search and validation agent."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.results: List[RepoCandidate] = []
        self.rate_limit_remaining = 5000
        self.temp_dir = Path("search_temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def check_prerequisites(self) -> bool:
        """Verify gh CLI is installed."""
        try:
            # Just check if gh is available, let actual commands handle auth
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                logger.info("✅ GitHub CLI found, version: " + result.stdout.split('\n')[0])
                logger.info("Note: Authentication will be checked during first API call")
                return True
            else:
                logger.error("GitHub CLI check failed")
                return False
        except FileNotFoundError:
            logger.error("GitHub CLI not found. Install with: brew install gh")
            return False
    
    def search_repositories(self) -> List[Dict]:
        """Search GitHub for repositories matching criteria."""
        logger.info("🔍 Searching GitHub for candidate repositories...")
        
        min_stars = self.config.get('min_stars', 1000)
        max_repos = self.config.get('max_repos', 200)
        languages = self.config.get('languages', ['Python', 'Go', 'TypeScript', 'JavaScript', 'Java', 'Ruby'])
        
        all_repos = []
        
        for language in languages:
            logger.info(f"Searching {language} repositories (stars>={min_stars})...")
            
            # GitHub search query
            query = f"language:{language} stars:>={min_stars} archived:false"
            
            try:
                result = subprocess.run(
                    [
                        "gh", "search", "repos", query,
                        "--limit", str(max_repos // len(languages)),
                        "--json", "name,owner,stargazersCount,forksCount,language,updatedAt",
                        "--sort", "stars"
                    ],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                repos = json.loads(result.stdout)
                logger.info(f"  Found {len(repos)} {language} repositories")
                all_repos.extend(repos)
                
                # Rate limit pause
                time.sleep(2)
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Search failed for {language}: {e.stderr}")
                continue
        
        logger.info(f"✅ Total repositories found: {len(all_repos)}")
        return all_repos
    
    def get_commit_count(self, owner: str, repo: str) -> int:
        """Get total commit count for repository."""
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/commits", "--paginate", "--jq", "length"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )
            if result.returncode == 0:
                counts = result.stdout.strip().split('\n')
                return sum(int(c) for c in counts if c.isdigit())
        except Exception as e:
            logger.debug(f"Commit count failed for {owner}/{repo}: {e}")
        
        # Fallback: search API
        try:
            result = subprocess.run(
                ["gh", "api", f"search/commits?q=repo:{owner}/{repo}", "--jq", ".total_count"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except:
            pass
        
        return 0
    
    def validate_ci_family(self, owner: str, repo: str) -> Tuple[bool, int]:
        """Check for CI/Build family data."""
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/actions/runs?per_page=1", "--jq", ".total_count"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
            if result.returncode == 0:
                count = int(result.stdout.strip())
                return (count >= 100, count)
        except:
            pass
        return (False, 0)
    
    def validate_deployment_family(self, owner: str, repo: str) -> Tuple[bool, int]:
        """Check for Deployment family data."""
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{owner}/{repo}/releases", "--paginate", "--jq", "length"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False
            )
            if result.returncode == 0:
                counts = result.stdout.strip().split('\n')
                total = sum(int(c) for c in counts if c.isdigit())
                return (total >= 10, total)
        except:
            pass
        return (False, 0)
    
    def clone_and_inspect(self, owner: str, repo: str) -> Dict:
        """Shallow clone and inspect for lockfiles, tests, schema, config."""
        repo_path = self.temp_dir / repo
        
        # Clean up if exists
        if repo_path.exists():
            subprocess.run(["rm", "-rf", str(repo_path)], check=False)
        
        # Shallow clone
        try:
            subprocess.run(
                ["git", "clone", "--depth", "50", "--quiet", f"https://github.com/{owner}/{repo}.git", str(repo_path)],
                capture_output=True,
                timeout=60,
                check=True
            )
        except Exception as e:
            logger.debug(f"Clone failed for {owner}/{repo}: {e}")
            return {}
        
        inspection = {
            'lockfile_path': '',
            'lockfile_commits': 0,
            'schema_path': '',
            'schema_commits': 0,
            'config_path': '',
            'config_commits': 0,
            'test_files': 0
        }
        
        # Find lockfiles
        lockfile_patterns = [
            "requirements*.txt", "Pipfile.lock", "poetry.lock", "pyproject.toml",
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "go.mod", "go.sum", "Gemfile.lock", "Cargo.lock",
            "pom.xml", "build.gradle*"
        ]
        
        for pattern in lockfile_patterns:
            try:
                result = subprocess.run(
                    ["find", str(repo_path), "-maxdepth", "3", "-name", pattern],
                    capture_output=True,
                    text=True,
                    check=False
                )
                lockfiles = [f for f in result.stdout.strip().split('\n') if f]
                if lockfiles:
                    lockfile = lockfiles[0].replace(str(repo_path) + '/', '')
                    inspection['lockfile_path'] = lockfile
                    
                    # Get commit count for lockfile
                    try:
                        git_result = subprocess.run(
                            ["git", "-C", str(repo_path), "log", "--oneline", "--follow", "--", lockfile],
                            capture_output=True,
                            text=True,
                            check=False
                        )
                        inspection['lockfile_commits'] = len(git_result.stdout.strip().split('\n'))
                    except:
                        pass
                    break
            except:
                continue
        
        # Find schema files
        schema_patterns = ["openapi*.json", "openapi*.yaml", "swagger*.json", "schema.graphql"]
        for pattern in schema_patterns:
            try:
                result = subprocess.run(
                    ["find", str(repo_path), "-maxdepth", "4", "-name", pattern],
                    capture_output=True,
                    text=True,
                    check=False
                )
                schemas = [f for f in result.stdout.strip().split('\n') if f]
                if schemas:
                    schema = schemas[0].replace(str(repo_path) + '/', '')
                    inspection['schema_path'] = schema
                    
                    try:
                        git_result = subprocess.run(
                            ["git", "-C", str(repo_path), "log", "--oneline", "--follow", "--", schema],
                            capture_output=True,
                            text=True,
                            check=False
                        )
                        inspection['schema_commits'] = len(git_result.stdout.strip().split('\n'))
                    except:
                        pass
                    break
            except:
                continue
        
        # Find config files
        config_patterns = ["*.tf", "Dockerfile*", "*docker-compose*.yml"]
        for pattern in config_patterns:
            try:
                result = subprocess.run(
                    ["find", str(repo_path), "-maxdepth", "3", "-name", pattern],
                    capture_output=True,
                    text=True,
                    check=False
                )
                configs = [f for f in result.stdout.strip().split('\n') if f and 'node_modules' not in f]
                if configs:
                    config = configs[0].replace(str(repo_path) + '/', '')
                    inspection['config_path'] = config
                    
                    try:
                        git_result = subprocess.run(
                            ["git", "-C", str(repo_path), "log", "--oneline", "--follow", "--", config],
                            capture_output=True,
                            text=True,
                            check=False
                        )
                        inspection['config_commits'] = len(git_result.stdout.strip().split('\n'))
                    except:
                        pass
                    break
            except:
                continue
        
        # Count test files
        test_patterns = ["*test*.py", "*_test.go", "*.test.ts", "*.test.js", "*.spec.ts", "*.spec.js"]
        for pattern in test_patterns:
            try:
                result = subprocess.run(
                    ["find", str(repo_path), "-name", pattern, "-not", "-path", "*/node_modules/*"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                count = len([f for f in result.stdout.strip().split('\n') if f])
                inspection['test_files'] += count
            except:
                continue
        
        # Cleanup
        subprocess.run(["rm", "-rf", str(repo_path)], check=False)
        
        return inspection
    
    def validate_repository(self, repo_data: Dict) -> Optional[RepoCandidate]:
        """Validate single repository across all families."""
        owner = repo_data['owner']['login']
        repo_name = repo_data['name']
        language = repo_data.get('language', 'Unknown')
        
        logger.info(f"Validating {owner}/{repo_name} ({language})...")
        
        try:
            # Basic info
            candidate = RepoCandidate(
                owner=owner,
                repo=repo_name,
                language=language,
                stars=repo_data.get('stargazersCount', 0),
                forks=repo_data.get('forksCount', 0),
                commits=0,
                last_updated=repo_data.get('updatedAt', '')
            )
            
            # Git family: commit count
            commits = self.get_commit_count(owner, repo_name)
            candidate.commits = commits
            candidate.has_git = commits >= 500
            
            if commits < 500:
                logger.debug(f"  ⚠️  {owner}/{repo_name}: Only {commits} commits (need 500+)")
                return None  # Skip low-commit repos
            
            # CI/Build family
            has_ci, ci_runs = self.validate_ci_family(owner, repo_name)
            candidate.has_ci = has_ci
            candidate.ci_runs = ci_runs
            
            # Deployment family
            has_deploy, releases = self.validate_deployment_family(owner, repo_name)
            candidate.has_deployment = has_deploy
            candidate.releases = releases
            
            # Clone and inspect for Dependencies, Testing, Schema, Config
            inspection = self.clone_and_inspect(owner, repo_name)
            
            if inspection:
                # Dependencies
                candidate.has_dependencies = bool(inspection['lockfile_path']) and inspection['lockfile_commits'] >= 20
                candidate.lockfile_path = inspection['lockfile_path']
                candidate.lockfile_commits = inspection['lockfile_commits']
                
                # Testing
                candidate.has_testing = inspection['test_files'] >= 50
                candidate.test_files = inspection['test_files']
                
                # Schema
                candidate.has_schema = bool(inspection['schema_path']) and inspection['schema_commits'] >= 10
                candidate.schema_path = inspection['schema_path']
                candidate.schema_commits = inspection['schema_commits']
                
                # Config
                candidate.has_config = bool(inspection['config_path']) and inspection['config_commits'] >= 5
                candidate.config_path = inspection['config_path']
                candidate.config_commits = inspection['config_commits']
            
            # Security (basic check - just note if Dependabot exists)
            # (requires elevated permissions, skip for now)
            candidate.has_security = False
            
            # Calculate score
            candidate.calculate_score()
            
            logger.info(f"  ✅ {owner}/{repo_name}: {candidate.family_count}/8 families, score={candidate.calibration_score:.1f}")
            
            return candidate
            
        except Exception as e:
            logger.error(f"  ❌ Validation failed for {owner}/{repo_name}: {e}")
            return None
    
    def run(self) -> List[RepoCandidate]:
        """Run full search and validation pipeline."""
        logger.info("🚀 Starting Repository Search Agent")
        logger.info("=" * 60)
        
        # Check prerequisites
        if not self.check_prerequisites():
            sys.exit(1)
        
        # Search repositories
        repos = self.search_repositories()
        
        if not repos:
            logger.error("No repositories found matching criteria")
            return []
        
        # Validate each repository
        logger.info("=" * 60)
        logger.info(f"🔬 Validating {len(repos)} repositories across 8 families...")
        logger.info("=" * 60)
        
        validated = 0
        for i, repo_data in enumerate(repos, 1):
            logger.info(f"\n[{i}/{len(repos)}] ", )
            
            candidate = self.validate_repository(repo_data)
            if candidate:
                self.results.append(candidate)
                validated += 1
            
            # Rate limit pause
            if i % 10 == 0:
                logger.info(f"\n⏸️  Pausing 5 seconds (processed {i}/{len(repos)})...")
                time.sleep(5)
        
        logger.info("=" * 60)
        logger.info(f"✅ Validation complete: {validated}/{len(repos)} repositories passed")
        logger.info("=" * 60)
        
        # Sort by score
        self.results.sort(key=lambda r: r.calibration_score, reverse=True)
        
        return self.results
    
    def export_csv(self, filepath: Path):
        """Export results to CSV."""
        logger.info(f"💾 Exporting results to {filepath}...")
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'rank', 'owner', 'repo', 'language', 'stars', 'commits',
                'family_count', 'calibration_score',
                'has_git', 'has_ci', 'has_dependencies', 'has_testing',
                'has_schema', 'has_deployment', 'has_config', 'has_security',
                'ci_runs', 'releases', 'test_files',
                'lockfile_path', 'lockfile_commits',
                'schema_path', 'schema_commits',
                'config_path', 'config_commits',
                'last_updated'
            ])
            
            writer.writeheader()
            
            for rank, candidate in enumerate(self.results, 1):
                row = asdict(candidate)
                row['rank'] = rank
                writer.writerow(row)
        
        logger.info(f"✅ Exported {len(self.results)} repositories")
    
    def print_summary(self):
        """Print summary statistics."""
        if not self.results:
            return
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 SUMMARY")
        logger.info("=" * 60)
        
        total = len(self.results)
        family_counts = [r.family_count for r in self.results]
        
        logger.info(f"Total validated repositories: {total}")
        logger.info(f"Average family coverage: {sum(family_counts) / total:.1f}/8")
        logger.info(f"Repos with 6+ families: {sum(1 for c in family_counts if c >= 6)}")
        logger.info(f"Repos with 4+ families: {sum(1 for c in family_counts if c >= 4)}")
        
        logger.info("\n🏆 Top 10 Repositories:")
        logger.info("-" * 60)
        for i, candidate in enumerate(self.results[:10], 1):
            logger.info(
                f"{i:2}. {candidate.owner}/{candidate.repo:30} "
                f"({candidate.language:12}) "
                f"{candidate.family_count}/8 families "
                f"score={candidate.calibration_score:.1f}"
            )
        
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Repository Search Agent for Evolution Engine')
    parser.add_argument('--min-stars', type=int, default=1000, help='Minimum stars (default: 1000)')
    parser.add_argument('--max-repos', type=int, default=200, help='Maximum repos to search (default: 200)')
    parser.add_argument('--output', type=str, default='repos_ranked.csv', help='Output CSV file')
    parser.add_argument('--languages', nargs='+', default=['Python', 'Go', 'TypeScript', 'JavaScript', 'Java', 'Ruby'],
                        help='Languages to search (default: Python Go TypeScript JavaScript Java Ruby)')
    
    args = parser.parse_args()
    
    config = {
        'min_stars': args.min_stars,
        'max_repos': args.max_repos,
        'languages': args.languages
    }
    
    agent = GitHubSearchAgent(config)
    results = agent.run()
    
    if results:
        output_path = Path(args.output)
        agent.export_csv(output_path)
        agent.print_summary()
    else:
        logger.error("No repositories validated successfully")
        sys.exit(1)


if __name__ == '__main__':
    main()
