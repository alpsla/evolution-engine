# Pre-Release Audit — Evolution Engine

**Date:** 2026-03-01  
**Scope:** Security, performance, architecture, dependencies, code quality, business flow  
**Status:** Audit complete; one deployment fix applied.

---

## Executive Summary

The codebase is in good shape for release with a clear security posture: no hardcoded secrets, proper webhook verification, HMAC-based auth where needed, and solid input validation on API surfaces. One **deployment blocker** was fixed (missing `license-check` in Vercel builds). Remaining items are recommendations, not blockers.

---

## 1. Security

### 1.1 Secrets & Authentication

| Area | Finding | Status |
|------|---------|--------|
| **Secrets** | All sensitive values read from environment (Stripe, Axiom, Upstash, EVO_ACCEPT_SECRET, EVO_LICENSE_SIGNING_KEY, GITHUB_BOT_TOKEN). No secrets in repo. | ✅ OK |
| **.gitignore** | `.env`, `.env.vercel`, `PyPI-Recovery-Codes-*` excluded. | ✅ OK |
| **Stripe webhook** | `stripe.Webhook.construct_event(payload, sig_header, webhook_secret)` used; invalid signature returns 400. Payload capped at 65KB. | ✅ OK |
| **Accept API** | POST/GET require HMAC-SHA256 of repo name via `EVO_ACCEPT_SECRET`; `hmac.compare_digest` used. | ✅ OK |
| **Pattern push** | POST requires valid `license_key` (HMAC-validated with EVO_LICENSE_SIGNING_KEY). | ✅ OK |
| **Activate / license-check** | Keys validated server-side with same signing key; rate limiting (10/20 per minute per IP). | ✅ OK |
| **get-license** | Session ID only (no auth). Session ID format enforced (`cs_` prefix, length ≤ 200). Intentional: only post-checkout redirect has it. | ✅ OK |

### 1.2 Input Validation & Injection

| Area | Finding | Status |
|------|---------|--------|
| **accept.py** | Repo format `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$`; key `family:metric`; `_DANGEROUS_PATTERNS` block script/template/shell-like content; length limits (50KB payload, 100 entries, 500 chars safe text). | ✅ OK |
| **adapter-request** | `_sanitize` strips `<>`, length limits; family from fixed allowlist; email not in GitHub issue body (hashed for Axiom only). Title sanitized (backticks/newlines removed). | ✅ OK |
| **patterns.py** | Fingerprint hex, instance_id 16-char hex, names via `_SAFE_NAME_RE`; description fields checked against `_DANGEROUS_PATTERNS`; 100KB payload, 10 pushes/hour. | ✅ OK |
| **kb_security.py** | Full pattern validation (XSS, template, path traversal, etc.) before KB storage; used for imported/community patterns. | ✅ OK |
| **knowledge_store** | `update_pattern` builds SET clause from **allowlisted** column names only; values parameterized. No SQL injection. | ✅ OK |
| **Subprocess** | No `shell=True`; adapters/docs require explicit argument lists. | ✅ OK |

### 1.3 HTML / XSS

| Area | Finding | Status |
|------|---------|--------|
| **report_generator** | Dynamic content in HTML passed through `_esc()` (escapes `&`, `<`, `>`, `"`). Used consistently for advisory data, adapter names, descriptions, commit messages. | ✅ OK |
| **_esc** | Does not escape single quote (`'`). All observed usage is in element content, not attributes. For defense-in-depth, consider `html.escape(s, quote=True)` or adding `'` → `&#39;`. | ⚠️ Low priority |

### 1.4 API Surface & Deployment

| Area | Finding | Status |
|------|---------|--------|
| **license-check** | `POST /api/license-check` is required for CLI heartbeat (Pro license verification). It was **not** in `website/vercel.json` `builds`; with explicit builds, it would not deploy. | ✅ **Fixed** — `api/license-check.py` added to `vercel.json` builds. |
| **CORS** | get-license, create-checkout, activate-license, license-check: `Access-Control-Allow-Origin: https://codequal.dev`. accept, adapter-request, patterns: `*`. Appropriate for public forms and CLI. | ✅ OK |
| **get-license** | No auth; anyone with a valid Stripe checkout session_id can retrieve the license key. By design (session_id is the secret token after redirect). | ✅ OK |

### 1.5 Business Flow (Security View)

- **Checkout:** create-checkout → Stripe Session → success.html with `session_id` → get-license fetches key from Stripe Customer metadata. Webhook (checkout.session.completed) generates key and stores in metadata + Redis. Flow is consistent and key is only exposed to the session that completed checkout.
- **License heartbeat:** CLI calls license-check with signed key; server validates HMAC then returns Redis status (active/cancelled/past_due/revoked). Prevents use of revoked/cancelled keys.
- **Activation:** activate-license validates key server-side and returns tier/email_hash/issued; CLI stores result with local integrity token (`_compute_activation_token`) to detect tampering of `~/.evo/license.json`.

---

## 2. Dependencies

| Area | Finding | Status |
|------|---------|--------|
| **pyproject.toml** | Core: GitPython, click, requests, jinja2 — pinned major ranges. Optional: pytest, pytest-cov, python-dotenv, stripe, build. | ✅ OK |
| **website/requirements.txt** | `stripe>=7.0,<13` for Vercel serverless. | ✅ OK |
| **Supply chain** | No lockfile in repo for main app (pip/setuptools). Consider `pip freeze` or pip-tools for reproducible builds. | ⚠️ Recommendation |
| **Vulnerabilities** | No automated vuln scan run in this audit. Recommend `pip audit` or Dependabot for the repo. | ⚠️ Recommendation |

---

## 3. Architecture & Business Flow

- **Pipeline:** Prescan → Registry (detect adapters) → Phase 1 (events) → Phase 2 (baselines) → Phase 3 (explanations) → Phase 4 (patterns) → Phase 5 (advisory). Clear separation; license checked at orchestrator entry; Pro gating for Tier 2 adapters and LLM.
- **License:** Env key → file (~/.evo, .evo in repo) → default free. File supports activated (integrity token) or HMAC-validated key. Heartbeat every 7 days with 14-day grace.
- **Stripe:** Webhook is single source of truth for key generation and Redis status. Idempotency on invoice.payment_succeeded (evo_last_invoice_id). Subscription deleted / refund / dispute revoke key and update Redis.
- **Accept flow:** PR comment → user runs `/evo accept` or `/evo accept permanent` → action calls accept webhook with HMAC(session_secret, repo) → Redis stores entries by repo hash. GET accept requires same HMAC for reads.
- **Pattern push:** CLI (Pro) pushes to /api/patterns with license_key; server validates key and pattern payload, rate limits by instance_id, merges with CAS into Redis.

---

## 4. Performance & Code Quality

| Area | Finding | Status |
|------|---------|--------|
| **Orchestrator** | Tier 2 API adapters run in ThreadPoolExecutor (e.g. max_workers=3); parallel where appropriate. | ✅ OK |
| **SQLite** | WAL mode, foreign_keys=ON; parameterized queries; schema and migrations in one place. | ✅ OK |
| **Rate limits** | Accept, adapter-request, patterns, activate-license, license-check, get-license all use in-memory rate limits (resets on cold start). Accept also has _MAX_ACCEPTS_PER_HOUR per repo. | ✅ OK (consider Redis-backed limits later for multi-instance) |
| **Payload limits** | Webhook 65KB; accept 50KB; patterns 100KB; license-check 4KB; adapter-request 10KB. | ✅ OK |
| **Test** | `os.system("whoami")` / `eval` in tests are intentional (malicious adapter detection tests). | ✅ OK |

---

## 5. Recommendations (Non-Blocking)

1. **Vercel:** Confirm in deployment that `api/license-check.py` is actually invoked (builds entry added; if your Vercel project uses auto-discovery, it may have worked anyway).
2. **HTML escape:** Use `html.escape(text, quote=True)` or add `'` → `&#39;` in `_esc` for full attribute safety.
3. **create-checkout:** Optionally cap length of `utm_source` from body before putting in Stripe metadata (Stripe has metadata size limits).
4. **Dependencies:** Add `pip audit` or Dependabot to CI; consider a lockfile for reproducible installs.
5. **Rate limiting:** If you scale to multiple Vercel instances, in-memory rate limits will not be shared; consider Upstash (or similar) for accept/patterns/activate/license-check.

---

## 6. Checklist Before Go-Live

- [x] No hardcoded secrets
- [x] Stripe webhook signature verification
- [x] Accept API HMAC for write and read
- [x] Pattern push requires valid license key
- [x] get-license session_id format validated
- [x] license-check included in Vercel builds
- [ ] Run `pip audit` (or equivalent) and fix any high/critical
- [ ] Smoke-test checkout → success → get-license → activate → heartbeat (license-check) on staging

---

*Audit performed against the evolution-engine codebase as of 2026-03-01.*
