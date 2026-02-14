# evo-patterns-example

27 universal cross-family patterns calibrated from 43 open-source repositories.

## Coverage

- **8 confirmed** (5+ repos): ci+git dispersion, deployment+git dispersion, dependency+git dispersion, and more
- **19 statistical** (2-4 repos): additional cross-family correlations
- **5 family combinations**: ci×git, deployment×git, dependency×git, ci×dependency, dependency×deployment

## Usage

This package is consumed automatically by Evolution Engine's pattern auto-fetch.
No manual installation required.

For local development:

```bash
pip install -e .
```

## Validation

```bash
evo patterns validate examples/evo-patterns-example
```
