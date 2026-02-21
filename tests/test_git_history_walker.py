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


## ---- Parser unit tests (no git repo needed) ----

def _make_walker():
    """Create a walker with a dummy path for parser-only testing."""
    import unittest.mock as mock
    with mock.patch("evolution.adapters.git.git_history_walker.Repo"):
        return GitHistoryWalker("/dev/null")


# ---- pnpm-lock.yaml ----

def test_parse_pnpm_lock_v6():
    """pnpm v6 format: /package/version: entries."""
    walker = _make_walker()
    content = """\
lockfileVersion: '6.0'

packages:

  /express/4.18.1:
    resolution: {integrity: sha512-abc}
    dependencies:
      accepts: 1.3.8
    dev: false

  /body-parser/1.20.2:
    resolution: {integrity: sha512-def}
    dev: false

  /@scope/name/1.0.0:
    resolution: {integrity: sha512-ghi}
    dev: true
"""
    result = walker._parse_pnpm_lock_content(content, "abc123")
    assert result["ecosystem"] == "npm"
    assert result["snapshot"]["total_count"] == 3


def test_parse_pnpm_lock_v9():
    """pnpm v9 format: package@version: entries."""
    walker = _make_walker()
    content = """\
lockfileVersion: '9.0'

packages:

  express@4.18.1:
    resolution: {integrity: sha512-abc}

  body-parser@1.20.2:
    resolution: {integrity: sha512-def}

importers:
  .:
    dependencies:
      express: 4.18.1
"""
    result = walker._parse_pnpm_lock_content(content, "abc123")
    assert result["ecosystem"] == "npm"
    assert result["snapshot"]["total_count"] == 2


def test_parse_pnpm_lock_empty():
    """Empty pnpm lockfile."""
    walker = _make_walker()
    content = "lockfileVersion: '6.0'\n"
    result = walker._parse_pnpm_lock_content(content, "abc123")
    assert result["snapshot"]["total_count"] == 0


# ---- pyproject.toml ----

def test_parse_pyproject_pep621():
    """PEP 621 dependencies list."""
    walker = _make_walker()
    content = """\
[project]
name = "my-app"
version = "1.0.0"
dependencies = [
    "requests>=2.28",
    "click>=8.0",
    "httpx[http2]>0.23",
]

[project.optional-dependencies]
dev = ["pytest", "black"]
"""
    result = walker._parse_pyproject_content(content, "abc123")
    assert result["ecosystem"] == "pip"
    assert result["snapshot"]["direct_count"] == 3
    assert result["snapshot"]["total_count"] == 3
    names = [d["name"] for d in result["dependencies"]]
    assert "requests" in names
    assert "click" in names
    assert "httpx" in names


def test_parse_pyproject_poetry():
    """Poetry format dependencies."""
    walker = _make_walker()
    content = """\
[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.28"
django = {version = ">=3.2", python = ">=3.8"}
flask = "^2.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.0"
"""
    result = walker._parse_pyproject_content(content, "abc123")
    assert result["ecosystem"] == "pip"
    # python is excluded, so 3 deps
    assert result["snapshot"]["direct_count"] == 3
    names = [d["name"] for d in result["dependencies"]]
    assert "python" not in names
    assert "requests" in names
    assert "django" in names
    assert "flask" in names


def test_parse_pyproject_no_deps():
    """pyproject.toml with no dependencies section."""
    walker = _make_walker()
    content = """\
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
"""
    result = walker._parse_pyproject_content(content, "abc123")
    assert result["snapshot"]["total_count"] == 0


# ---- composer.lock ----

def test_parse_composer_lock():
    """Standard composer.lock with packages and packages-dev."""
    walker = _make_walker()
    content = json.dumps({
        "packages": [
            {"name": "monolog/monolog", "version": "2.0.0"},
            {"name": "symfony/console", "version": "5.4.0"},
            {"name": "guzzlehttp/guzzle", "version": "7.4.0"},
        ],
        "packages-dev": [
            {"name": "phpunit/phpunit", "version": "9.5.0"},
        ],
    })
    result = walker._parse_composer_lock_content(content, "abc123")
    assert result["ecosystem"] == "composer"
    assert result["snapshot"]["direct_count"] == 3
    assert result["snapshot"]["transitive_count"] == 1
    assert result["snapshot"]["total_count"] == 4


def test_parse_composer_lock_invalid_json():
    """Malformed composer.lock returns empty snapshot."""
    walker = _make_walker()
    result = walker._parse_composer_lock_content("{invalid", "abc123")
    assert result["snapshot"]["total_count"] == 0


def test_parse_composer_lock_empty():
    """composer.lock with empty arrays."""
    walker = _make_walker()
    content = json.dumps({"packages": [], "packages-dev": []})
    result = walker._parse_composer_lock_content(content, "abc123")
    assert result["snapshot"]["total_count"] == 0


# ---- build.gradle / build.gradle.kts ----

def test_parse_gradle_groovy():
    """Groovy DSL build.gradle."""
    walker = _make_walker()
    content = """\
plugins {
    id 'java-library'
}

dependencies {
    implementation 'com.google.guava:guava:30.1.1-jre'
    implementation 'org.springframework:spring-web:5.3.0'
    api 'org.apache.commons:commons-lang3:3.12.0'
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine:5.8.1'
}
"""
    result = walker._parse_gradle_content(content, "abc123")
    assert result["ecosystem"] == "gradle"
    assert result["snapshot"]["total_count"] == 5
    assert result["snapshot"]["direct_count"] == 3  # impl + api
    assert result["snapshot"]["transitive_count"] == 2  # test deps


def test_parse_gradle_kotlin_dsl():
    """Kotlin DSL build.gradle.kts."""
    walker = _make_walker()
    content = """\
plugins {
    `java-library`
}

dependencies {
    implementation("com.google.guava:guava:30.1.1-jre")
    implementation("org.springframework:spring-web:5.3.0")
    runtimeOnly("org.postgresql:postgresql:42.3.0")
    testImplementation("junit:junit:4.13.2")
}
"""
    result = walker._parse_gradle_content(content, "abc123", manifest_file="build.gradle.kts")
    assert result["ecosystem"] == "gradle"
    assert result["snapshot"]["total_count"] == 4
    assert result["snapshot"]["direct_count"] == 3  # 2 impl + 1 runtimeOnly
    assert result["snapshot"]["transitive_count"] == 1  # 1 testImpl


def test_parse_gradle_empty():
    """build.gradle with no dependencies."""
    walker = _make_walker()
    content = """\
plugins {
    id 'java'
}
"""
    result = walker._parse_gradle_content(content, "abc123")
    assert result["snapshot"]["total_count"] == 0


# ---- pom.xml ----

def test_parse_pom_xml():
    """Standard Maven pom.xml."""
    walker = _make_walker()
    content = """\
<?xml version="1.0" encoding="UTF-8"?>
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>my-project</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>com.google.guava</groupId>
            <artifactId>guava</artifactId>
            <version>30.1.1-jre</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>5.3.0</version>
        </dependency>
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
"""
    result = walker._parse_pom_content(content, "abc123")
    assert result["ecosystem"] == "maven"
    assert result["snapshot"]["total_count"] == 3
    assert result["snapshot"]["direct_count"] == 2  # non-test
    assert result["snapshot"]["transitive_count"] == 1  # test scope


def test_parse_pom_xml_empty():
    """pom.xml with no dependencies."""
    walker = _make_walker()
    content = """\
<?xml version="1.0"?>
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>minimal</artifactId>
</project>
"""
    result = walker._parse_pom_content(content, "abc123")
    assert result["snapshot"]["total_count"] == 0


def test_parse_pom_xml_all_test_scope():
    """pom.xml where all dependencies are test scope."""
    walker = _make_walker()
    content = """\
<project>
    <dependencies>
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>4.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
"""
    result = walker._parse_pom_content(content, "abc123")
    assert result["snapshot"]["total_count"] == 2
    assert result["snapshot"]["direct_count"] == 0
    assert result["snapshot"]["transitive_count"] == 2


# ---- Parser return value structure ----

# ---- Package.resolved (Swift PM) ----

def test_parse_swift_package_resolved_v2():
    """Swift Package.resolved v2 format."""
    walker = _make_walker()
    content = json.dumps({
        "version": 2,
        "pins": [
            {"identity": "alamofire", "kind": "remoteSourceControl",
             "location": "https://github.com/Alamofire/Alamofire.git",
             "state": {"revision": "abc123", "version": "5.6.2"}},
            {"identity": "swiftyjson", "kind": "remoteSourceControl",
             "location": "https://github.com/SwiftyJSON/SwiftyJSON.git",
             "state": {"revision": "def456", "version": "5.0.1"}},
        ],
    })
    result = walker._parse_swift_package_resolved_content(content, "sha123")
    assert result["ecosystem"] == "swift"
    assert result["snapshot"]["total_count"] == 2
    assert result["snapshot"]["direct_count"] == 2


def test_parse_swift_package_resolved_v1():
    """Swift Package.resolved v1 format (older Xcode)."""
    walker = _make_walker()
    content = json.dumps({
        "version": 1,
        "object": {
            "pins": [
                {"package": "Alamofire", "repositoryURL": "https://github.com/Alamofire/Alamofire.git",
                 "state": {"branch": None, "revision": "abc", "version": "5.6.2"}},
            ],
        },
    })
    result = walker._parse_swift_package_resolved_content(content, "sha123")
    assert result["ecosystem"] == "swift"
    assert result["snapshot"]["total_count"] == 1


def test_parse_swift_package_resolved_empty():
    """Empty Package.resolved."""
    walker = _make_walker()
    content = json.dumps({"version": 2, "pins": []})
    result = walker._parse_swift_package_resolved_content(content, "sha123")
    assert result["snapshot"]["total_count"] == 0


def test_parse_swift_package_resolved_invalid():
    """Malformed Package.resolved."""
    walker = _make_walker()
    result = walker._parse_swift_package_resolved_content("{bad", "sha123")
    assert result["snapshot"]["total_count"] == 0


# ---- CMakeLists.txt ----

def test_parse_cmake_find_package():
    """CMakeLists.txt with find_package calls."""
    walker = _make_walker()
    content = """\
cmake_minimum_required(VERSION 3.14)
project(MyProject)

find_package(Boost REQUIRED COMPONENTS filesystem)
find_package(OpenSSL 1.1 REQUIRED)
find_package(Threads REQUIRED)

add_executable(main main.cpp)
target_link_libraries(main Boost::filesystem OpenSSL::SSL Threads::Threads)
"""
    result = walker._parse_cmake_content_deps(content, "sha123")
    assert result["ecosystem"] == "cmake"
    assert result["snapshot"]["total_count"] == 3
    assert result["snapshot"]["direct_count"] == 3


def test_parse_cmake_fetch_content():
    """CMakeLists.txt with FetchContent_Declare."""
    walker = _make_walker()
    content = """\
include(FetchContent)

FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG release-1.12.1
)

FetchContent_Declare(
  fmt
  GIT_REPOSITORY https://github.com/fmtlib/fmt.git
  GIT_TAG 9.1.0
)

FetchContent_MakeAvailable(googletest fmt)
"""
    result = walker._parse_cmake_content_deps(content, "sha123")
    assert result["ecosystem"] == "cmake"
    assert result["snapshot"]["total_count"] == 2


def test_parse_cmake_mixed():
    """CMakeLists.txt with both find_package and FetchContent."""
    walker = _make_walker()
    content = """\
find_package(Boost REQUIRED)
FetchContent_Declare(fmt GIT_REPOSITORY https://github.com/fmtlib/fmt.git)
find_package(OpenSSL)
"""
    result = walker._parse_cmake_content_deps(content, "sha123")
    assert result["ecosystem"] == "cmake"
    assert result["snapshot"]["total_count"] == 3


def test_parse_cmake_empty():
    """CMakeLists.txt with no dependencies."""
    walker = _make_walker()
    content = """\
cmake_minimum_required(VERSION 3.14)
project(Simple)
add_executable(main main.cpp)
"""
    result = walker._parse_cmake_content_deps(content, "sha123")
    assert result["snapshot"]["total_count"] == 0


# ---- Parser return value structure ----

def test_all_parsers_return_correct_structure():
    """All parsers return the standard dependency snapshot structure."""
    walker = _make_walker()

    parsers_and_content = [
        ("_parse_pnpm_lock_content", "lockfileVersion: '6.0'\npackages:\n  /a/1.0:\n    resolution: {}\n"),
        ("_parse_pyproject_content", '[project]\ndependencies = ["requests"]\n'),
        ("_parse_composer_lock_content", '{"packages": [{"name": "a/b"}], "packages-dev": []}'),
        ("_parse_gradle_content", "dependencies {\n    implementation 'a:b:1.0'\n}\n"),
        ("_parse_pom_content", "<project><dependencies><dependency><groupId>a</groupId><artifactId>b</artifactId><version>1</version></dependency></dependencies></project>"),
        ("_parse_swift_package_resolved_content", '{"version": 2, "pins": [{"identity": "a"}]}'),
        ("_parse_cmake_content_deps", "find_package(Boost REQUIRED)\n"),
    ]

    required_keys = {"ecosystem", "manifest_file", "trigger", "snapshot", "dependencies"}
    snapshot_keys = {"direct_count", "transitive_count", "total_count", "max_depth"}

    for parser_name, content in parsers_and_content:
        parser = getattr(walker, parser_name)
        result = parser(content, "sha123")
        missing = required_keys - set(result.keys())
        assert not missing, f"{parser_name} missing keys: {missing}"
        snap_missing = snapshot_keys - set(result["snapshot"].keys())
        assert not snap_missing, f"{parser_name} snapshot missing keys: {snap_missing}"
        assert result["trigger"]["commit_sha"] == "sha123"


if __name__ == "__main__":
    print("Running Git History Walker tests...\n")
    test_git_history_walker_extracts_dependencies()
    test_phase2_generates_signals_for_all_families()
    print("\n✅ All integration tests passed")

    print("\nRunning parser unit tests...\n")
    test_parse_pnpm_lock_v6()
    test_parse_pnpm_lock_v9()
    test_parse_pnpm_lock_empty()
    test_parse_pyproject_pep621()
    test_parse_pyproject_poetry()
    test_parse_pyproject_no_deps()
    test_parse_composer_lock()
    test_parse_composer_lock_invalid_json()
    test_parse_composer_lock_empty()
    test_parse_gradle_groovy()
    test_parse_gradle_kotlin_dsl()
    test_parse_gradle_empty()
    test_parse_pom_xml()
    test_parse_pom_xml_empty()
    test_parse_pom_xml_all_test_scope()
    test_all_parsers_return_correct_structure()
    print("\n✅ All parser tests passed")
