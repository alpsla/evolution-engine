# evo-adapter-jest-cov

Evolution Engine adapter for jest-cov (testing family).

## Install

```bash
pip install evo-adapter-jest-cov
```

After installing, `evo analyze .` will automatically detect and use this adapter.

## Verify

```bash
evo adapter validate evo_jest_cov.JestCovAdapter
evo adapter list .
```

## Development

```bash
git clone <this-repo>
cd evo-adapter-jest-cov
pip install -e .
pytest tests/
evo adapter validate evo_jest_cov.JestCovAdapter
```
