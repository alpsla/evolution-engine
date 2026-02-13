# Adapter Security Requirements & Scanning

Evolution Engine scans adapter source code for dangerous patterns before
certification. This protects users from malicious or unsafe adapters.

## Running a Security Scan

```bash
# Scan a module by name
evo adapter security-check evo_jenkins

# Scan a directory
evo adapter security-check /path/to/evo-adapter-jenkins/

# Combined with structural validation
evo adapter validate evo_jenkins.JenkinsAdapter --security
```

## Severity Levels

| Level | Effect | Description |
|-------|--------|-------------|
| **Critical** | Blocks certification | Code that can execute arbitrary commands or leak secrets |
| **Warning** | Advisory only | Code that should be reviewed but isn't necessarily dangerous |
| **Info** | Informational | Style observations, no action required |

## What the Scanner Checks

### Critical (must fix)

| Check | Pattern | Why it's dangerous | Fix |
|-------|---------|-------------------|-----|
| `eval()` | `eval(...)` | Executes arbitrary Python code | Use `json.loads()` or `ast.literal_eval()` |
| `exec()` | `exec(...)` | Executes arbitrary Python code | Restructure logic to avoid dynamic execution |
| `os.system()` | `os.system(...)` | Runs shell commands | Use `subprocess.run()` with explicit args |
| `os.popen()` | `os.popen(...)` | Runs shell commands | Use `subprocess.run()` with explicit args |
| `pickle.load()` | `pickle.load(...)` | Deserializes arbitrary objects | Use `json.loads()` |
| `yaml.unsafe_load()` | `yaml.unsafe_load(...)` | Deserializes arbitrary objects | Use `yaml.safe_load()` |
| `marshal.load()` | `marshal.load(...)` | Deserializes arbitrary objects | Use `json.loads()` |
| Hardcoded secrets | `api_key = 'ABCD...'` | Leaks credentials | Use environment variables |

### Warning (should review)

| Check | Pattern | Recommendation |
|-------|---------|---------------|
| `subprocess` | `import subprocess` | Use specific args list, never `shell=True` |
| `compile()` | `compile(...)` | Avoid dynamic code compilation |
| `__import__()` | `__import__(...)` | Use standard `import` statements |
| Path traversal | `'../'` | Validate and sanitize file paths |

### Info

| Check | Pattern | Note |
|-------|---------|------|
| System paths | `'/etc/'`, `'/tmp/'` | May be intentional; review for correctness |

### AST-based Checks

The scanner also uses Python AST analysis to detect:

- **Network calls in `__init__`**: HTTP libraries (`requests`, `urllib`, `httpx`, `socket`)
  should not make network calls during adapter construction. Move network access
  to `iter_events()` where it's expected and can be properly timed.

## Security Best Practices for Adapter Authors

1. **No dynamic code execution**: Never use `eval()`, `exec()`, or `compile()`
2. **No shell commands**: Use `subprocess.run()` with explicit argument lists
3. **No hardcoded secrets**: Read credentials from environment variables
4. **Safe deserialization**: Use `json.loads()` or `yaml.safe_load()`, never pickle
5. **Network calls in iter_events()**: Keep `__init__` fast and offline
6. **Validate file paths**: Sanitize user-provided paths to prevent traversal
7. **Minimal dependencies**: Only import what you need
