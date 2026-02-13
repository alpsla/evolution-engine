# Evolution Engine — Documentation

## Quick Links
- [Implementation Plan](IMPLEMENTATION_PLAN.md) — full roadmap and execution status
- [Launch Plan](LAUNCH_PLAN.md) — beta launch strategy and testing guide
- [Architecture Vision](ARCHITECTURE_VISION.md) — design principles (constitution)

## Contracts
Interface specifications for each phase and adapter family.
- [contracts/](contracts/) — Phase 2–5 contracts + adapter contract
- [contracts/adapters/](contracts/adapters/) — per-family contracts (CI, git, dependency, etc.)

## Design
Phase design documents and technical specifications.
- [design/](design/) — Phase 2–5 designs + report generator spec

## Adapters
- [adapters/](adapters/) — adapter developer guide, security, trust tiers, lifecycle, building

## Guides
- [guides/CALIBRATION_GUIDE.md](guides/CALIBRATION_GUIDE.md) — how to calibrate on new repos
- [guides/INTEGRATIONS.md](guides/INTEGRATIONS.md) — connecting external tools

## Legal
- [legal/](legal/) — ToS draft, privacy policy draft, AI safety audit, data flow audit

## Website & Translations
- Website source: [../website/](../website/)
- Translations: [../website/i18n/](../website/i18n/) — EN, DE, ES JSON files

## Archive
Old versions, research notes, completed task specs.
- [archive/](archive/)

---

## Authority Order (Highest → Lowest)

If two documents conflict:

> Architecture Vision → Phase Contracts → Adapter Contracts → Design → Implementation → Research

Lower-authority documents must be updated or archived.

---

## Guiding Principle

> **Clarity beats cleverness.**
>
> If it is not obvious which document to trust, the documentation has failed.
