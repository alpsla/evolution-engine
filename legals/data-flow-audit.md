# Evolution Engine -- Data Flow Audit

**Audit Date:** 2026-02-11
**Scope:** Full codebase data flow analysis for GDPR, CCPA, and US/EU legal compliance
**Auditor:** Automated source code analysis
**Version:** v0.1.1 (commit 48df4ed)

---

## Executive Summary

Evolution Engine (EE) is a local-first CLI tool. The core analysis pipeline (Phases 1-5) runs entirely on the user's machine and stores all output in the local `.evo/` directory. Data leaves the machine only when the user explicitly triggers one of the following: CLI telemetry (opt-in), KB sync (opt-in, disabled by default), AI investigation/fix (opt-in, requires API key), or via the website's Stripe/adapter-request flows.

**Key findings:**
- PII is present in the license system (email address) and the adapter request form (email address).
- Stripe processes customer payment data; only email and Stripe customer ID are stored in EE systems.
- Telemetry is opt-in with explicit user consent prompt and is anonymous by design.
- KB sync is disabled by default (privacy_level=0) and requires explicit user opt-in.
- GitHub API data is cached locally and never transmitted to EE servers.
- AI agent prompts contain repository metrics and advisory text but never raw source code.

---

## Data Flow Summary Table

| # | Data Flow | Data Collected | Destination | Contains PII | Retention | Consent Mechanism |
|---|-----------|---------------|-------------|:------------:|-----------|-------------------|
| 1 | CLI Telemetry | Event name, adapter count, family list, version, anon UUID | Vercel (`/api/telemetry`) then Axiom | No | Axiom retention policy (configurable) | Opt-in with interactive prompt; `DO_NOT_TRACK=1` respected |
| 2 | Stripe Checkout | Email, payment method (Stripe-handled), subscription | Stripe API | Yes (email) | Stripe data retention policies | User-initiated purchase |
| 3 | Stripe Webhook | Stripe customer ID, event type, license key | Vercel (`/api/webhook`) then Axiom | Partial (customer_id) | Axiom + Stripe metadata | Triggered by Stripe event |
| 4 | License Retrieval | Stripe session ID | Vercel (`/api/get-license`) | No | None (pass-through) | User-initiated page load |
| 5 | Axiom Logging | Telemetry events, webhook events, adapter requests, errors | Axiom (`api.axiom.co`) | Partial (see per-flow) | Axiom dataset retention | Server-side operational logging |
| 6 | GitHub API | Workflow runs, releases, security alerts, repo metadata | GitHub REST API (`api.github.com`) | No (public repo data) | Cached locally in `.evo/api_cache/` | User provides `GITHUB_TOKEN` explicitly |
| 7 | License Key | Email, tier, issuance date, expiration | Local files (`~/.evo/license.json`, env var) | Yes (email) | Persisted until user deletes | User activates key manually |
| 8 | Adapter Request Form | Email, adapter name, description, use case, IP address | Vercel (`/api/adapter-request`) then GitHub Issues + Axiom | Yes (email, IP) | GitHub issue (indefinite), Axiom retention | User-initiated form submission |
| 9 | Local Data Storage | Pipeline output, patterns, advisories, config, investigation reports | `~/.evo/` and `<repo>/.evo/` directories | No | Until user deletes | Local operation, no transmission |
| 10 | PR Comments | Advisory summary, risk levels, pattern matches, metric values | GitHub API (PR comments) | No | GitHub PR lifetime | User runs GitHub Action or `gh pr comment` |
| 11 | Inline Suggestions | File paths, line numbers, finding text, fix suggestions | GitHub API (PR reviews) | No | GitHub PR lifetime | User enables `suggest-fixes: true` in Action |
| 12 | KB Sync (Push) | Anonymized pattern digests OR advisory metadata | Registry (`registry.codequal.dev`) | No | Registry retention | Opt-in via `sync.privacy_level >= 1` (default: 0) |
| 13 | KB Sync (Pull) | None sent; patterns received | Local `.evo/` from registry | No | Local storage | User-initiated `evo patterns pull` |
| 14 | AI Agent (Anthropic) | Advisory text, metric deviations, pattern context, system prompt | Anthropic API (`api.anthropic.com`) | No | Anthropic data policy | User provides `ANTHROPIC_API_KEY` and runs `evo investigate` or `evo fix` |
| 15 | AI Agent (CLI) | Advisory text, metric deviations, investigation report | Local subprocess (e.g., `claude` CLI) | No | Per CLI tool policy | User runs `evo fix` with CLI agent |

---

## Detailed Flow Analysis

### 1. CLI Telemetry

**Source files:**
- `/evolution/telemetry.py` (client-side sender)
- `/evolution/config.py` (consent storage)
- `/evolution/cli.py` (integration points at lines 83-100, 162-163, 240-246, 950-951)
- `/website/api/telemetry.py` (server-side receiver)

**Data collected:**
```json
{
  "event": "analyze_complete",
  "properties": {
    "adapter_count": 3,
    "families": ["version_control", "dependency"],
    "signal_count": 5,
    "pattern_count": 2
  },
  "anon_id": "uuid-v4-random",
  "version": "0.1.1"
}
```

**What is NOT collected:** File paths, code content, repository names, usernames, commit hashes, IP addresses (client-side). The server does NOT log IP addresses from the request.

**PII assessment:** No PII. The `anon_id` is a random UUID4 generated locally and stored at `~/.evo/anon_id`. It is not derived from any personal information.

**Consent mechanism:**
- Disabled by default (`telemetry.enabled = false` in `_DEFAULTS`, line 33 of `config.py`).
- Interactive consent prompt on first `evo analyze` run (`prompt_consent()` in `telemetry.py`, line 88).
- Prompt only appears in interactive terminals (checks `sys.stdin.isatty()`).
- Respects `DO_NOT_TRACK=1` environment variable (line 32 of `telemetry.py`).
- User can toggle at any time via `evo telemetry on/off` or `evo config set telemetry.enabled false`.

**Transmission:** Fire-and-forget POST to `https://codequal.dev/api/telemetry` with a 2-second timeout. Runs in a background daemon thread. Failures are silently ignored.

**Server-side handling:** Rate limited to 100 events/hour per `anon_id`. Payload max 4096 bytes. Events logged to Vercel stdout and forwarded to Axiom.

**Retention:** Axiom dataset retention policy (externally configurable). No server-side database.

---

### 2. Stripe Payment Data (Checkout)

**Source file:** `/website/api/create-checkout.py`

**Data flow:**
1. User clicks "Upgrade to Pro" on website.
2. Frontend POSTs to `/api/create-checkout`.
3. Server creates a Stripe Checkout Session with `mode="subscription"` and returns a Stripe-hosted checkout URL.
4. User enters payment information **directly on Stripe's hosted checkout page** -- EE never sees card numbers, CVV, or billing address.

**Data EE receives from Stripe:** None at checkout time. The session metadata contains only `{"product": "evolution-engine-pro"}`.

**PII assessment:** Payment card data is processed entirely by Stripe. EE servers never handle or store payment card information.

**Consent mechanism:** User-initiated purchase flow.

---

### 3. Stripe Webhook (License Generation)

**Source file:** `/website/api/webhook.py`

**Data flow:**
1. Stripe sends `checkout.session.completed` webhook to `/api/webhook`.
2. Webhook handler verifies Stripe signature.
3. Retrieves customer from Stripe API using `customer_id`.
4. Reads `customer.email` from Stripe Customer object.
5. Generates HMAC-signed license key containing `{tier, email, issued}`.
6. Stores the license key as metadata on the Stripe Customer object (`evo_license_key`).

**Data stored in EE systems (Axiom log):**
```json
{
  "type": "webhook",
  "event": "license_generated",
  "customer_id": "cus_xxx",
  "tier": "pro",
  "timestamp": "2026-02-11T..."
}
```

**PII assessment:** The Axiom log contains the Stripe `customer_id` (pseudonymous identifier). The customer's email is embedded in the license key payload but the key is stored only on Stripe's side (as customer metadata). The email is NOT logged directly to Axiom. However, `customer_id` can be used to look up the email via Stripe, making it an indirect PII reference.

**On subscription deletion (`customer.subscription.deleted`):** The license key is cleared from Stripe customer metadata. A log entry with `customer_id` is sent to Axiom.

**Retention:** Stripe retains customer data per their retention policy. Axiom retains logs per dataset configuration.

---

### 4. License Retrieval

**Source file:** `/website/api/get-license.py`

**Data flow:**
1. After Stripe checkout, user is redirected to `/success?session_id=cs_xxx`.
2. Frontend calls `/api/get-license?session_id=cs_xxx`.
3. Server retrieves Stripe Session, then Customer, then reads `evo_license_key` from metadata.
4. Returns `{"license_key": "..."}` to the browser.
5. User copies key and activates via `evo license activate <key>`.

**PII assessment:** The session ID is a Stripe reference. The returned license key contains the user's email (embedded and signed). This key is displayed to the user for them to save locally.

**Retention:** No server-side storage. Pass-through only.

---

### 5. Axiom Logging (All Handlers)

**Source files:** All `website/api/*.py` files contain `_axiom_send()`.

**Events logged to Axiom across all handlers:**

| Handler | Event Type | Fields | PII Present |
|---------|-----------|--------|:-----------:|
| `telemetry.py` | `telemetry` | event name, properties (counts), anon_id, version, timestamp | No |
| `webhook.py` | `webhook` (license_generated) | customer_id, tier, timestamp | Indirect (customer_id) |
| `webhook.py` | `webhook` (license_revoked) | customer_id, timestamp | Indirect (customer_id) |
| `webhook.py` | `webhook_error` | event_type, error message, timestamp | No |
| `adapter-request.py` | `adapter_request` | adapter_name, family, description, use_case, email, timestamp | Yes (email) |
| `adapter-request.py` | `adapter_request` (error) | error type, detail, timestamp | No |

**Destination:** `https://api.axiom.co/v1/datasets/{evo}/ingest`

**Authentication:** Bearer token from `AXIOM_TOKEN` environment variable (server-side secret).

**GDPR/CCPA concern:** The adapter request flow logs user-provided email to Axiom. This is PII and requires a lawful basis (consent via form submission) and data subject access/deletion rights.

---

### 6. GitHub API Calls

**Source files:**
- `/evolution/adapters/github_client.py` (shared HTTP client)
- `/evolution/orchestrator.py` (lines 326-382, API ingestion)
- GitHub-specific adapters in `evolution/adapters/ci/`, `evolution/adapters/deployment/`, `evolution/adapters/security/`

**Data accessed from GitHub API:**
- `/repos/{owner}/{repo}/actions/runs` -- CI workflow run metadata (status, duration, timestamps)
- `/repos/{owner}/{repo}/releases` -- Release metadata (tag, prerelease flag, asset count, timestamps)
- `/repos/{owner}/{repo}/code-scanning/alerts` or `/repos/{owner}/{repo}/dependabot/alerts` -- Security alert metadata

**Data flow:** GitHub API responses are cached locally at `.evo/api_cache/` as JSON files with SHA-256 hashed filenames. Data is **never transmitted to EE servers**.

**PII assessment:** GitHub API responses may contain committer usernames and emails in some endpoints. These are cached locally but are NOT forwarded to any EE infrastructure. The user explicitly provides their `GITHUB_TOKEN` and the data accessed is limited to repositories they have access to.

**Retention:** Local cache in `.evo/api_cache/` persists until manually deleted or overwritten on next run.

**Authentication:** User's `GITHUB_TOKEN` (Personal Access Token or `github.token` from Actions).

---

### 7. License System

**Source file:** `/evolution/license.py`

**License key structure:**
```
base64( json({"tier": "pro", "email": "user@example.com", "issued": "2026-02-11T..."}) + "." + hmac_sha256_signature )
```

**Data stored:**
| Location | Content | PII |
|----------|---------|:---:|
| `EVO_LICENSE_KEY` env var | Full signed license key | Yes (email embedded) |
| `~/.evo/license.json` | `{"license_key": "..."}` | Yes (email embedded) |
| `<repo>/.evo/license.json` | `{"license_key": "..."}` | Yes (email embedded) |

**PII assessment:** The license key contains the customer's email address in base64-encoded (not encrypted) form. Anyone with the key can decode it and read the email.

**GDPR/CCPA concern:** The email in the license key constitutes PII. The key is stored locally on the user's machine. The user has full control over deletion. However, if the license file is accidentally committed to version control, the email would be exposed.

**Recommendation:** Consider hashing the email in the license payload (e.g., `SHA-256(email)`) rather than including it in plaintext. This would still allow server-side validation while reducing PII exposure in the local file.

---

### 8. Adapter Request Form

**Source file:** `/website/api/adapter-request.py`

**Data collected from user:**
```json
{
  "adapter_name": "Jenkins",
  "family": "ci",
  "description": "Fetch builds from Jenkins API",
  "email": "user@example.com",
  "use_case": "Track CI failures"
}
```

**Data flow:**
1. User fills in the form on the website.
2. POST to `/api/adapter-request`.
3. Server extracts client IP from `X-Forwarded-For` header (used for rate limiting only, via `rate_key`).
4. If `GITHUB_BOT_TOKEN` is configured: creates a **public GitHub Issue** in the configured repo containing the adapter name, family, description, use case, and email (labeled "Requested by: user@example.com").
5. If no bot token: logs the request to Vercel stdout and Axiom.

**PII assessment:** **YES -- this flow has significant PII concerns:**
- **Email address** is collected and included in a public GitHub issue body as "Requested by: user@example.com".
- **IP address** is used for rate limiting (in-memory only, not logged).
- The email is also sent to Axiom as part of the log entry.

**GDPR/CCPA concerns:**
1. Email in public GitHub issue is visible to anyone. User should be informed their email will be publicly visible.
2. Email logged to Axiom requires data subject access/deletion capability.
3. No explicit privacy notice or consent checkbox is described in the server-side code.

**Recommendations:**
- Add a privacy notice to the form informing users their email may appear in a public GitHub issue.
- Consider making the email optional or redacting it from the public issue body (e.g., "Requested by: u***@e*****.com" or "A registered user").
- Implement data deletion procedures for Axiom logs.

---

### 9. Local Data Storage (~/.evo/)

**Source files:** `/evolution/config.py`, `/evolution/license.py`, various Phase engines

**Contents of `~/.evo/` (user home directory):**

| File/Directory | Content | PII |
|----------------|---------|:---:|
| `config.toml` | User preferences (telemetry, sync, LLM settings) | No |
| `license.json` | License key (contains email) | Yes (email) |
| `anon_id` | Random UUID4 for telemetry | No |
| `adapter_requests/requests.json` | Locally saved adapter requests | No |

**Contents of `<repo>/.evo/` (per-repository):**

| File/Directory | Content | PII |
|----------------|---------|:---:|
| `phase1/events.db` | Raw events (commit metadata, CI runs, etc.) | No* |
| `phase2/signals.db` | Deviation signals | No |
| `phase3/explanations/` | Generated explanation text | No |
| `phase4/knowledge.db` | Patterns and knowledge artifacts | No |
| `phase5/advisory.json` | Final advisory report | No |
| `phase5/investigation_prompt.txt` | AI prompt with metric deviations | No |
| `investigation/investigation.json` | AI investigation results | No |
| `investigation/investigation.txt` | Human-readable investigation | No |
| `fix/fix_result.json` | Fix loop results | No |
| `api_cache/` | Cached GitHub API responses | No** |
| `sync_state.json` | KB sync timestamps | No |
| `report.html` | Generated HTML report | No |

\* Git commit metadata may contain author names/emails from the git log, but these are read from the local git repository (already on disk).

\** Cached GitHub API responses may contain GitHub usernames in action run metadata.

**Data flow:** All this data stays on disk. None of it is transmitted unless the user explicitly triggers a telemetry event, KB push, or AI investigation.

---

### 10. PR Comments

**Source files:**
- `/evolution/pr_comment.py` (formatting)
- `/action/action.yml` (posting via `gh pr comment`)

**Data posted to GitHub:**
- Risk level badges (Critical/High/Medium/Low)
- Family names and metric names (e.g., "ci / run_duration")
- Current and baseline metric values (numerical)
- Pattern match descriptions (generic text like "CI failure correlates with dispersion increase")
- Truncated AI investigation summary (max 3000 chars, if investigation was run)

**PII assessment:** No PII. The comment contains only aggregate metrics and pattern descriptions. No usernames, emails, file content, or code snippets are included in the PR comment.

**Retention:** GitHub PR comments persist for the lifetime of the PR/repo.

---

### 11. Inline Fix Suggestions

**Source files:**
- `/evolution/inline_suggestions.py` (extraction and formatting)
- `/action/action.yml` (posting via `gh api`)

**Data posted to GitHub:**
- File paths within the repository (e.g., `src/main.py`)
- Line numbers
- Finding text: risk level, root cause description, suggested fix text
- Commit SHA for the review

**PII assessment:** No PII. The suggestions reference files and metrics. The finding text is generated from the AI investigation report which operates on metric deviations, not personal data.

**Retention:** GitHub PR review comments persist for the lifetime of the PR/repo.

---

### 12. KB Sync (Push)

**Source file:** `/evolution/kb_sync.py`

**Privacy levels (configurable via `evo config set sync.privacy_level`):**

| Level | Default | Data Shared |
|:-----:|:-------:|-------------|
| 0 | Yes | **Nothing** -- sharing completely disabled |
| 1 | No | Advisory metadata only: family counts, significant changes count, patterns matched count, timestamp |
| 2 | No | Anonymized pattern digests: fingerprint (hash), pattern type, sources (family names), metrics (metric names), correlation strength, occurrence count |

**Level 2 push payload:**
```json
{
  "level": 2,
  "instance_id": "sha256(evo_dir_path)[:16]",
  "patterns": [
    {
      "fingerprint": "a1b2c3d4e5f6...",
      "pattern_type": "co_occurrence",
      "sources": ["ci", "version_control"],
      "metrics": ["run_duration", "dispersion"],
      "correlation_strength": 0.72,
      "occurrence_count": 5
    }
  ],
  "timestamp": "2026-02-11T..."
}
```

**PII assessment:** No PII. The `instance_id` is derived from the local `.evo` directory path via SHA-256 hash -- it cannot be reversed to identify a user. Pattern digests contain only family/metric names and statistical measures. The export process (`kb_export.py`) explicitly strips pattern_id, signal_refs, event_refs, repo path, and author info.

**Destination:** `https://registry.codequal.dev/v1/patterns` (POST).

**Consent mechanism:** Requires explicit opt-in by setting `sync.privacy_level >= 1`. Default is 0 (nothing shared).

---

### 13. KB Sync (Pull)

**Source file:** `/evolution/kb_sync.py`

**Data flow:** GET request to `https://registry.codequal.dev/v1/patterns` with optional `since` timestamp. Returns community patterns. No local data is sent in the request.

**Imported patterns are validated** through `kb_security.validate_pattern()` which checks for injection attacks, oversized payloads, fingerprint spoofing, and type confusion before storage.

**PII assessment:** No PII sent or received.

---

### 14. AI Agent (Anthropic API)

**Source files:**
- `/evolution/agents/anthropic_agent.py`
- `/evolution/investigator.py`

**Data sent to Anthropic API:**
- **System prompt:** Fixed investigation instructions (no user data).
- **User prompt:** Contains:
  - Repository scope name (e.g., directory name like "my-project")
  - Period dates (from/to)
  - Metric deviations: family name, metric name, current value, normal value, standard deviation count
  - Pattern match descriptions (generic statistical text)

**Example prompt content:**
```
Here is a structural analysis of my-project over the period 2026-01-01 to 2026-02-01.

CHANGES DETECTED:
- ci / run_duration: normally 120.3, now 342.7 (3.2 stddev)
- dependency / dependency_count: normally 45, now 52 (2.1 stddev)
```

**What is NOT sent:** Source code, file contents, git diffs, commit messages, author names, file paths (unless present in AI investigation results from a previous step).

**PII assessment:** No PII in the prompts. The data consists of aggregate metrics and family/metric names. Repository name (directory name) is included but this is not PII.

**Data retention:** Subject to Anthropic's data usage and retention policies. As of the API terms, Anthropic does not train on API inputs.

**Consent mechanism:** User must explicitly provide `ANTHROPIC_API_KEY` and invoke `evo investigate` or `evo fix`. No implicit API calls are made.

---

### 15. AI Agent (CLI / Subprocess)

**Source file:** `/evolution/agents/cli_agent.py`

**Data flow:** The investigation prompt or fix prompt is passed as a `--prompt` argument to the local `claude` CLI (or other configured tool) via subprocess. For fix operations, the agent runs in the repo working directory and can read/modify local files.

**PII assessment:** No PII in prompts (same analysis as Anthropic Agent). The CLI agent has access to the local file system, but this is a local operation controlled by the user.

**Data destination:** Depends on the CLI tool used. For the `claude` CLI (Claude Code), data goes to Anthropic's API subject to their data policy.

---

## Data Subject Rights (GDPR/CCPA)

### Right to Access

| Data Store | Can User Access? | Method |
|------------|:----------------:|--------|
| Local files (`~/.evo/`) | Yes | Direct file access |
| Telemetry (Axiom) | Partial | User can identify their `anon_id` from `~/.evo/anon_id` but Axiom access requires internal tooling |
| Stripe data | Yes | Stripe customer portal |
| Adapter request (GitHub Issue) | Yes | Public GitHub issue URL |
| Adapter request (Axiom) | No direct access | Requires internal tooling |

### Right to Deletion

| Data Store | Can User Delete? | Method |
|------------|:----------------:|--------|
| Local files (`~/.evo/`) | Yes | `rm -rf ~/.evo/` |
| Telemetry (Axiom) | No self-service | Requires internal deletion process |
| Stripe data | Partial | Account deletion via Stripe; EE must handle customer data deletion |
| Adapter request (GitHub Issue) | No self-service | Issue must be edited/deleted by repo admin |
| Adapter request (Axiom) | No self-service | Requires internal deletion process |
| License key (Stripe metadata) | Yes | Clears on subscription cancellation |

### Right to Opt-Out

| Data Flow | Opt-Out Method |
|-----------|---------------|
| Telemetry | `evo telemetry off` or `DO_NOT_TRACK=1` |
| KB Sync | Default is off; `evo config set sync.privacy_level 0` |
| AI Investigation | Don't set `ANTHROPIC_API_KEY`; don't run `evo investigate` |
| GitHub API | Don't set `GITHUB_TOKEN` |
| Adapter Request | Don't submit the form |

---

## Compliance Gaps and Recommendations

### High Priority

1. **Adapter request email in public GitHub issue** -- User email is posted as plain text in a public GitHub issue. Add a privacy notice to the form, or redact/omit email from the issue body.

2. **License key contains plaintext email** -- The base64-encoded license key can be trivially decoded to reveal the user's email. Consider hashing the email (SHA-256) in the license payload, or encrypting the payload.

3. **No data deletion procedure for Axiom** -- There is no documented or automated way to delete a specific user's data from Axiom logs. Implement a data deletion process or retention auto-expiry.

4. **No privacy policy link in adapter request form** -- The server-side code does not reference a privacy policy. The website form should link to a privacy policy before data submission.

### Medium Priority

5. **Stripe customer_id logged to Axiom** -- While pseudonymous, this is an indirect personal identifier under GDPR. Consider whether this logging is necessary or if it can be further anonymized.

6. **Webhook error messages may contain PII** -- The webhook handler logs `str(exc)` to Axiom on errors (line 91 of `webhook.py`). Exception messages from Stripe could theoretically contain customer data. Consider sanitizing error messages.

7. **No DSAR (Data Subject Access Request) process** -- There is no documented process for handling access/deletion requests. This is required under both GDPR (Article 15-17) and CCPA.

### Low Priority

8. **Telemetry anon_id is persistent** -- While the UUID is random, it is a persistent identifier that could theoretically be correlated with other data. This is standard practice for anonymous telemetry but should be disclosed in the privacy policy.

9. **Git commit metadata** -- Phase 1 ingestion reads git log data which includes committer names/emails. This data stays local and is not transmitted, but the `.evo/` directory contents should be mentioned in documentation.

10. **`api_cache/` may contain GitHub usernames** -- Cached GitHub API responses may include usernames in workflow run data. This data is local-only but should be covered by the repo's `.gitignore`.

---

## Third-Party Data Processors

| Service | Role | Data Received | Data Processing Agreement |
|---------|------|---------------|:-------------------------:|
| **Stripe** | Payment processor | Customer email, payment method, subscription status | Required (Stripe DPA) |
| **Axiom** | Log aggregation | Telemetry events, webhook logs, adapter requests | Required (Axiom DPA) |
| **Vercel** | Serverless hosting | All HTTP request data for `website/api/` endpoints | Required (Vercel DPA) |
| **GitHub** | Issue tracker, PR comments | Adapter requests (email in issues), advisory summaries | Standard GitHub ToS |
| **Anthropic** | AI API | Investigation prompts (metrics, advisory text) | Review Anthropic API terms |

---

## Cookie and Tracking Summary

The Evolution Engine CLI does **not** use cookies or browser-based tracking. The website (`codequal.dev`) is hosted on Vercel and may use Vercel's standard analytics. The only client-side identifier is the `anon_id` UUID stored at `~/.evo/anon_id` on the user's local machine.

---

## Appendix: Source File Index

| File | Data Flow Role |
|------|---------------|
| `evolution/telemetry.py` | CLI-side telemetry sender (opt-in) |
| `evolution/config.py` | User preferences including telemetry/sync consent |
| `evolution/license.py` | License key validation and storage |
| `evolution/cli.py` | CLI entry point; telemetry integration |
| `evolution/orchestrator.py` | Pipeline orchestrator; GitHub API ingestion |
| `evolution/registry.py` | Adapter detection (local file scanning) |
| `evolution/kb_sync.py` | Community pattern push/pull |
| `evolution/kb_export.py` | Pattern anonymization for export |
| `evolution/kb_security.py` | Pattern validation on import |
| `evolution/agents/anthropic_agent.py` | Anthropic API integration |
| `evolution/agents/cli_agent.py` | Local CLI subprocess agent |
| `evolution/agents/base.py` | Agent factory and base interface |
| `evolution/investigator.py` | AI investigation prompt builder |
| `evolution/fixer.py` | AI fix-verify loop |
| `evolution/pr_comment.py` | PR comment formatting |
| `evolution/inline_suggestions.py` | Inline review comment extraction |
| `evolution/adapters/github_client.py` | Shared GitHub API client with caching |
| `website/api/telemetry.py` | Server-side telemetry receiver |
| `website/api/webhook.py` | Stripe webhook handler (license generation) |
| `website/api/create-checkout.py` | Stripe checkout session creation |
| `website/api/get-license.py` | License key retrieval after checkout |
| `website/api/adapter-request.py` | Adapter request form handler |
| `action/action.yml` | GitHub Action (PR comments, inline suggestions) |
