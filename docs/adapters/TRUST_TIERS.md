# Trust Tiers & Badge System

Every adapter detected by Evolution Engine is automatically assigned a trust
badge. Badges help users understand the provenance and review status of each
adapter.

## The Four Tiers

| Badge | Source | Description |
|-------|--------|-------------|
| `[built-in]` | Tier 1 (file) or Tier 2 (API) | Ships with evolution-engine. Maintained by the core team. |
| `[verified]` | Tier 3 plugin, in `verified_adapters.json` | Published on PyPI and reviewed by the EE maintainers. |
| `[community]` | Tier 3 plugin, published on PyPI | Available on PyPI but not yet reviewed by maintainers. |
| `[local]` | Tier 3 plugin, editable install | Development mode only. No PyPI version metadata. |

## How Badges Are Auto-Assigned

```
Is this Tier 1 or Tier 2?
  ├── Yes → [built-in]
  └── No (Tier 3 plugin) →
        Is plugin_name in verified_adapters.json?
          ├── Yes → [verified]
          └── No →
                Does the package have PyPI version metadata?
                  ├── Yes → [community]
                  └── No → [local]
```

## Display in CLI

```
evo adapter list .

Connected adapters:
  [built-in  ] version_control/git
  [built-in  ] dependency/pip
  [verified  ] ci/jenkins  (from evo-adapter-jenkins)
  [community ] testing/pytest-cov  (from evo-adapter-pytest-cov)
  [local     ] quality/sonarqube  (from evo-adapter-sonarqube)
```

JSON output includes the `trust_level` field for each adapter.

## Promotion Path

### local → community

Publish your adapter to PyPI:

```bash
pip install build twine
python -m build
twine upload dist/*
```

Once published, the badge automatically changes to `[community]` on the next
`evo adapter list` run.

### community → verified

1. Your adapter must pass `evo adapter validate` (all 13 structural checks)
2. Your adapter must pass `evo adapter security-check` (no critical findings)
3. Open a pull request adding your package name to `evolution/data/verified_adapters.json`
4. The EE maintainers review the adapter source and approve the PR
5. On the next EE release, your adapter is tagged `[verified]`

### What Each Tier Means for Users

| Tier | Risk | Support | Update Policy |
|------|------|---------|---------------|
| built-in | Lowest | Full support | Updated with EE releases |
| verified | Low | Community + maintainer oversight | Independent releases |
| community | Medium | Community only | Independent releases |
| local | Variable | Self-supported | Manual |
