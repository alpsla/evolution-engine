# Documentation Structure & Authority

This directory contains the architectural, contractual, and research documentation
for the Evolution Engine project.

Understanding **which documents are authoritative** is critical.

---

## Authority Order (Highest → Lowest)

1. **ARCHITECTURE_VISION.md**  
   The project constitution. Defines purpose, principles, and boundaries.

2. **Contracts (`*_CONTRACT.md`)**  
   Normative guarantees and invariants for each major layer.

3. **Design Documents (`*_DESIGN.md`)**  
   Implementation approaches that must conform to the contracts.

4. **IMPLEMENTATION_PLAN.md**  
   Execution order and milestone tracking.

5. **Research (`docs/research/`)**  
   Exploratory work and historical context. Informative but not binding.

6. **Archive (`docs/archive/`)**  
   Superseded documents retained for traceability.

---

## Conflict Resolution Rule

If two documents conflict:

> Architecture Vision → Contracts → Design → Implementation → Research

Lower‑authority documents must be updated or archived.

---

## Guiding Principle

> **Clarity beats cleverness.**
> 
> If it is not obvious which document to trust, the documentation has failed.
