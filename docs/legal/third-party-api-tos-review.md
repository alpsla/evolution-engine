# Third-Party API Terms of Service Review

**Project:** Evolution Engine
**Date:** 2026-02-11
**Scope:** All third-party services that Evolution Engine integrates with, either directly (API calls) or indirectly (detection/mention in UI).

---

## Table of Contents

1. [Integration Inventory](#1-integration-inventory)
2. [Tier A: Direct API Integrations (We Make API Calls)](#2-tier-a-direct-api-integrations)
   - [2.1 GitHub](#21-github)
   - [2.2 Anthropic](#22-anthropic)
   - [2.3 OpenRouter](#23-openrouter)
   - [2.4 Stripe](#24-stripe)
   - [2.5 Axiom](#25-axiom)
   - [2.6 Vercel](#26-vercel)
   - [2.7 PyPI (Python Package Index)](#27-pypi)
3. [Tier B: Detected/Mentioned Services (No Direct API Calls from EE)](#3-tier-b-detectedmentioned-services)
   - [3.1 Datadog](#31-datadog)
   - [3.2 New Relic](#32-new-relic)
   - [3.3 Sentry](#33-sentry)
   - [3.4 PagerDuty](#34-pagerduty)
   - [3.5 OpsGenie](#35-opsgenie)
   - [3.6 Snyk](#36-snyk)
   - [3.7 Semgrep](#37-semgrep)
   - [3.8 SonarQube](#38-sonarqube)
   - [3.9 Codecov](#39-codecov)
   - [3.10 Grafana](#310-grafana)
   - [3.11 Prometheus](#311-prometheus)
   - [3.12 OpenTelemetry](#312-opentelemetry)
   - [3.13 Elastic APM](#313-elastic-apm)
   - [3.14 Azure Monitor](#314-azure-monitor)
   - [3.15 Jira (Atlassian)](#315-jira-atlassian)
   - [3.16 Linear](#316-linear)
   - [3.17 Qodo (CodiumAI)](#317-qodo-codiumai)
   - [3.18 CodeRabbit](#318-coderabbit)
   - [3.19 LaunchDarkly](#319-launchdarkly)
   - [3.20 Unleash](#320-unleash)
   - [3.21 Statuspage](#321-statuspage)
4. [Tier C: Infrastructure and Hosting Services](#4-tier-c-infrastructure-and-hosting-services)
   - [4.1 GitLab](#41-gitlab)
   - [4.2 Jenkins](#42-jenkins)
   - [4.3 CircleCI](#43-circleci)
5. [Cross-Cutting Concerns](#5-cross-cutting-concerns)
6. [Risk Summary Matrix](#6-risk-summary-matrix)
7. [Priority Action Items](#7-priority-action-items)

---

## 1. Integration Inventory

Evolution Engine integrates with third-party services at three levels:

| Level | Description | Examples |
|-------|-------------|----------|
| **Direct API** | EE makes HTTP calls to their API | GitHub, Anthropic, Stripe, Axiom, OpenRouter |
| **Detection Only** | EE detects their presence in repos (config files, packages, imports) and mentions their name in output | Datadog, Snyk, Sentry, etc. (20+ services) |
| **Infrastructure** | EE is hosted on or distributed through their platform | Vercel, PyPI, GitHub Actions |

**Source files reviewed:**
- `evolution/registry.py` -- Adapter registry (Tier 1 file-based, Tier 2 API-enriched, Tier 3 plugins)
- `evolution/prescan.py` -- 3-layer source detection (configs, lockfiles, imports)
- `evolution/data/sdk_fingerprints.json` -- 21 service fingerprints for detection
- `evolution/agents/anthropic_agent.py` -- Anthropic SDK agent
- `evolution/agents/cli_agent.py` -- CLI agent (invokes Claude Code)
- `evolution/llm_anthropic.py` -- Direct Anthropic API client (requests-based)
- `evolution/llm_openrouter.py` -- OpenRouter API client
- `evolution/adapters/github_client.py` -- GitHub REST API client
- `evolution/kb_sync.py` -- Community KB registry (codequal.dev)
- `evolution/telemetry.py` -- Anonymous telemetry to codequal.dev
- `evolution/license.py` -- HMAC license system
- `evolution/pr_comment.py` -- GitHub PR comment formatting
- `evolution/inline_suggestions.py` -- GitHub PR review comments
- `evolution/investigator.py` -- AI investigation agent
- `evolution/fixer.py` -- RALF fix-verify loop
- `website/api/create-checkout.py` -- Stripe Checkout session creation
- `website/api/get-license.py` -- Stripe session license retrieval
- `website/api/webhook.py` -- Stripe webhook handler + Axiom logging
- `website/api/telemetry.py` -- Telemetry ingest + Axiom forwarding
- `website/api/adapter-request.py` -- GitHub Issues API for adapter requests
- `action/action.yml` -- GitHub Actions composite action
- `.github/workflows/build-wheels.yml` -- cibuildwheel + PyPI publish

---

## 2. Tier A: Direct API Integrations

### 2.1 GitHub

**What we use it for:**
- REST API: CI workflow runs, releases, security advisories, PR comments, PR reviews, issue creation
- Used in: `evolution/adapters/github_client.py`, `action/action.yml`, `website/api/adapter-request.py`
- Authentication: User-provided `GITHUB_TOKEN` or `github.token` in Actions

**API Terms of Service:**
- Governed by [GitHub Terms of Service, Section H (API Terms)](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)
- Additional: [GitHub Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)
- For developers: [GitHub Registered Developer Agreement](https://docs.github.com/en/site-policy/github-terms/github-registered-developer-agreement)

**Commercial use allowed?**
Yes, with conditions. GitHub permits building integrations and tools that interoperate with GitHub. The Registered Developer Agreement grants "a limited, worldwide, non-exclusive, non-transferable license to access and use the API solely for the purpose of developing, demonstrating, testing and supporting interoperability and integrations between your products and services and GitHub's products and services." EE fits squarely within this description -- it reads CI runs, releases, and security data to provide cross-signal analysis back to the user.

**Data redistribution rules:**
- We may NOT download data for spamming or selling personal information.
- We may NOT share API tokens to exceed rate limits.
- Data retrieved from GitHub API may be displayed back to the authenticated user (this is our use case).
- We do NOT store or redistribute raw GitHub data to other users. Patterns derived from analysis are anonymized.
- Caution: The Registered Developer Agreement says you cannot "use the API to provide service bureau, application hosting, or processing services to third parties" -- however, EE operates on the user's own token accessing their own repos, which is standard integration behavior (analogous to CI tools, Dependabot, etc.).

**Trademark/branding rules:**
- [GitHub Trademark Policy](https://docs.github.com/en/site-policy/content-removal-policies/github-trademark-policy)
- We may reference "GitHub" descriptively (e.g., "GitHub Actions adapter", "reads GitHub releases") under nominative fair use.
- We must NOT use the GitHub logo without permission or imply endorsement.
- We must NOT register any marks confusingly similar to GitHub's.
- Contact: trademarks@github.com for logo usage permission.

**Rate limits and fair use:**
- Authenticated REST API: 5,000 requests/hour per token.
- GitHub Apps: 5,000 requests/hour per installation.
- Secondary rate limits: No more than 100 concurrent requests; no more than 900 points/minute for GraphQL.
- Our `github_client.py` implements rate limit detection and backoff (waits up to 15 min when remaining < 50).
- In the GitHub Action, we use `github.token` which is scoped to the workflow run.

**Risk Level: MEDIUM**

Key risks:
1. The "service bureau" clause in the Registered Developer Agreement could be read broadly, but EE operates with the user's own token on their own repos, which is the standard pattern for thousands of GitHub integrations (Dependabot, Codecov, SonarQube, etc.).
2. Rate limits constrain parallel agent calibration runs (~8 repos safely at 5,000 req/hr).
3. If EE were listed on GitHub Marketplace, additional terms (the Marketplace Developer Agreement) would apply.

**Recommended actions:**
- [x] Use user-provided tokens only (never hardcode or share tokens) -- already implemented
- [x] Implement rate limit backoff -- already implemented in `github_client.py`
- [ ] Consider registering as a GitHub App for better rate limits (5,000/hr per installation vs. 5,000 per PAT)
- [ ] Add disclaimer to docs: "Evolution Engine is not affiliated with or endorsed by GitHub, Inc."
- [ ] If publishing to GitHub Marketplace, review the [Marketplace Developer Agreement](https://docs.github.com/en/site-policy/github-terms/github-marketplace-developer-agreement)
- [ ] Do NOT use GitHub's Octocat or invertocat logo in marketing without written permission

---

### 2.2 Anthropic

**What we use it for:**
- Claude API for AI investigation of advisories (root cause analysis)
- Claude API for Phase 4b semantic pattern descriptions
- Used in: `evolution/agents/anthropic_agent.py` (SDK), `evolution/llm_anthropic.py` (direct HTTP)
- Authentication: User-provided `ANTHROPIC_API_KEY`

**API Terms of Service:**
- [Anthropic Commercial Terms of Service](https://www.anthropic.com/news/expanded-legal-protections-api-improvements)
- [Anthropic Usage Policy](https://www.anthropic.com/news/usage-policy-update) (updated September 15, 2025)

**Commercial use allowed?**
Yes. Anthropic's API is explicitly designed for building commercial products. Their Commercial Terms of Service are clear that the API is for building products and applications. Anthropic does NOT use API inputs/outputs to train models by default (unlike the consumer product).

**Data redistribution rules:**
- API outputs belong to the customer. Anthropic grants customers ownership rights over outputs generated through their services.
- Anthropic provides copyright indemnification for commercial API customers: they will defend customers against copyright infringement claims related to authorized use of the service.
- No data training on commercial API traffic (explicit promise in Commercial Terms).

**Trademark/branding rules:**
- As of January 2026, Anthropic has cracked down on third-party tools spoofing the official Claude Code client.
- We should say "Powered by Claude" or "Uses Anthropic's Claude API" rather than implying we are Claude.
- Our CLI agent invokes `claude` (Claude Code CLI) as an external process -- this is the documented, supported integration pattern.

**Rate limits and fair use:**
- Rate limits vary by tier (free, build, scale) and are based on tokens per minute and requests per minute.
- Our `llm_anthropic.py` implements retry with exponential backoff and adaptive rate delay.
- Estimated cost: ~$0.003/pattern for Phase 4b, ~$0.01 total per repo analysis.

**Risk Level: LOW**

EE's use of the Anthropic API is a textbook commercial integration: user provides their own API key, we send analysis prompts, and display results back to the user. Anthropic explicitly supports and encourages this pattern.

**Recommended actions:**
- [x] Use user-provided API keys only -- already implemented
- [x] Implement retry and backoff -- already implemented
- [ ] Add "Powered by Claude" attribution where investigation results are displayed
- [ ] Do NOT store Anthropic API keys in any persistent storage or logs
- [ ] Review Anthropic's Usage Policy for prohibited use cases (ensure investigation prompts don't trigger policy violations, e.g., no weapons/malware-related analysis)

---

### 2.3 OpenRouter

**What we use it for:**
- LLM API gateway for explanation rendering (Phase 3 templates)
- Used in: `evolution/llm_openrouter.py`
- Authentication: User-provided `OPENROUTER_API_KEY`

**API Terms of Service:**
- [OpenRouter Terms of Service](https://openrouter.ai/terms) (updated April 15, 2025)

**Commercial use allowed?**
Yes. OpenRouter is an API gateway designed for developers building applications. Commercial use is permitted.

**Data redistribution rules:**
- IMPORTANT: If prompt/chat logging is enabled in the user's OpenRouter account, OpenRouter obtains an irrevocable right to further commercial use of inputs and outputs.
- Default: Prompts and completions are NOT stored (zero logging by default).
- Users must be aware that logging settings affect data rights.

**Trademark/branding rules:**
- No specific brand guidelines found. Use "OpenRouter" descriptively.

**Rate limits and fair use:**
- Rate limits depend on the upstream model provider routed through OpenRouter.
- Our `llm_openrouter.py` implements retry with exponential backoff, adaptive rate delay, and Retry-After header handling.

**Risk Level: LOW**

OpenRouter is a pass-through API gateway. The primary risk is if a user has logging enabled, OpenRouter gains rights to the data. EE should document this.

**Recommended actions:**
- [x] Implement retry and backoff -- already implemented
- [ ] Add documentation noting that OpenRouter's data rights depend on the user's logging settings
- [ ] Recommend users disable logging in OpenRouter for sensitive repos
- [ ] Consider whether OpenRouter is still needed now that Phase 3 LLM is retired (per memory notes)

---

### 2.4 Stripe

**What we use it for:**
- Payment processing for Pro subscriptions ($19/month)
- Checkout session creation, webhook handling, license key generation
- Used in: `website/api/create-checkout.py`, `website/api/get-license.py`, `website/api/webhook.py`
- Authentication: Server-side `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`

**API Terms of Service:**
- [Stripe Services Agreement](https://stripe.com/legal/ssa) (updated November 18, 2025)
- [Stripe Services Terms](https://stripe.com/legal/ssa-services-terms)

**Commercial use allowed?**
Yes -- this is Stripe's core business. We are a Stripe customer using their payment processing API as intended.

**Data redistribution rules:**
- We must NOT rent, lease, sell, redistribute, or sublicense Stripe Technology.
- We may distribute only "distributable" elements of Stripe Technology (client-side SDKs, etc.) in binary form.
- Customer payment data is subject to PCI-DSS compliance requirements.
- We store license keys in Stripe Customer metadata (this is a supported Stripe pattern).

**Trademark/branding rules:**
- [Stripe Mark Usage Terms](https://stripe.com/legal/marks)
- We may mention our connection with Stripe (e.g., "Payments processed by Stripe").
- We must NOT incorporate Stripe's marks into our own trademarks or trade names.
- We must NOT misrepresent our relationship with Stripe or imply endorsement.
- We must NOT modify or alter Stripe's marks.
- Stripe wordmark: Available in slate, blurple (on light backgrounds) and white (on dark backgrounds) only.
- Contact: trademarks@stripe.com for non-standard usage.

**Rate limits and fair use:**
- Stripe API rate limits: Generally 100 read requests/second, 100 write requests/second in live mode.
- Our usage is very low volume (webhook events only on subscription changes).

**Risk Level: LOW**

This is standard e-commerce payment processing. Stripe explicitly supports SaaS subscription billing, which is exactly our use case.

**Recommended actions:**
- [x] Use server-side secret keys only (never expose in client) -- already implemented
- [x] Verify webhook signatures -- already implemented in `webhook.py`
- [ ] Ensure PCI-DSS compliance for any payment-related pages (use Stripe Checkout hosted page, which we do)
- [ ] Add "Payments processed by Stripe" to checkout flow
- [ ] Replace hardcoded dev signing key in `webhook.py` with production `EVO_LICENSE_SIGNING_KEY` before launch
- [ ] Review Stripe's Acceptable Use Policy to confirm our product category is permitted

---

### 2.5 Axiom

**What we use it for:**
- Observability/logging for Vercel serverless functions (fire-and-forget event ingest)
- Used in: `website/api/webhook.py`, `website/api/telemetry.py`, `website/api/adapter-request.py`
- Authentication: Server-side `AXIOM_TOKEN`

**API Terms of Service:**
- [Axiom Terms of Service](https://www.axiom.co/terms/)

**Commercial use allowed?**
Yes. Axiom is designed for commercial observability. Their pricing starts free for personal projects and scales for commercial use. We are a standard Axiom customer sending our own operational logs.

**Data redistribution rules:**
- We send our own operational events (webhook logs, telemetry, errors) to Axiom.
- We do not redistribute any Axiom data to end users.
- No concerns here -- this is standard observability usage.

**Trademark/branding rules:**
- No specific public brand guidelines found. Use "Axiom" descriptively if needed.

**Rate limits and fair use:**
- Axiom's free tier includes 500 MB/day ingest. Our usage is minimal (individual JSON events).
- Our implementation uses a 2-second timeout and swallows all errors (fire-and-forget pattern).

**Risk Level: LOW**

Standard observability/logging SaaS usage. No data flows from Axiom back to our users.

**Recommended actions:**
- [x] Fire-and-forget pattern (never blocks user requests) -- already implemented
- [ ] Ensure `AXIOM_TOKEN` has minimal permissions (ingest-only, not read)
- [ ] Review Axiom's data retention settings to align with privacy policy

---

### 2.6 Vercel

**What we use it for:**
- Hosting for marketing website (codequal.dev) and serverless API functions
- Used for: Stripe webhooks, telemetry ingest, adapter request form, license retrieval
- Configuration: `website/vercel.json`

**API Terms of Service:**
- [Vercel Terms of Service](https://vercel.com/legal/terms)
- [Vercel Fair Use Guidelines](https://vercel.com/docs/limits/fair-use-guidelines)

**Commercial use allowed?**
Yes, but ONLY on paid plans. The Hobby (free) plan is restricted to personal, non-commercial use. For revenue-generating use, we need the Pro plan ($20/user/month) or Enterprise.

**Data redistribution rules:**
- Not applicable -- we host our own content on Vercel. No data redistribution concerns.

**Trademark/branding rules:**
- "Powered by Vercel" badge may be required on Hobby plan.
- On paid plans, branding requirements are relaxed.

**Rate limits and fair use:**
- Serverless function limits: 10-second duration (Hobby), 60-second (Pro), 900-second (Enterprise).
- Bandwidth: 100 GB/month (Hobby), 1 TB/month (Pro).
- Our functions are lightweight (JSON API responses, typically < 100ms).

**Risk Level: MEDIUM**

The key risk is operating on the Hobby plan for a commercial product. If codequal.dev generates revenue (Pro subscriptions), we MUST be on the Vercel Pro plan.

**Recommended actions:**
- [ ] **CRITICAL: Verify we are on Vercel Pro plan** -- using Hobby for commercial use violates ToS
- [ ] Review Vercel's Fair Use Guidelines for serverless function usage patterns
- [ ] Ensure serverless functions stay within execution time limits

---

### 2.7 PyPI (Python Package Index)

**What we use it for:**
- Package distribution (publishing `evolution-engine` package)
- Used in: `.github/workflows/build-wheels.yml` (trusted publishing via `pypa/gh-action-pypi-publish`)

**API Terms of Service:**
- [PyPI Terms of Use](https://policies.python.org/pypi.org/Terms-of-Use/)
- [PyPI Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/) (new ToS introduced February 2025)
- [PyPI Acceptable Use Policy](https://policies.python.org/pypi.org/Acceptable-Use-Policy/)

**Commercial use allowed?**
Yes. PyPI hosts both open-source and commercially-licensed packages. Uploading a package grants PSF a limited license to reproduce and distribute, but NOT to sell the content. Our package license terms are what users agree to.

**Data redistribution rules:**
- Packages uploaded to PyPI are publicly downloadable.
- If content is uploaded under a license other than an "Included License" (OSI-approved), we grant PSF and all users a non-exclusive license to reproduce, distribute, etc.
- We should ensure our package has a clear license declaration in `pyproject.toml`.

**Trademark/branding rules:**
- No specific PyPI trademark concerns. We use PyPI as a distribution channel.

**Rate limits and fair use:**
- PyPI rate limits are generous for package installation (CDN-backed).
- Upload rate limits apply during publishing.

**Risk Level: LOW**

Standard package distribution. No concerns as long as our license is clearly declared.

**Recommended actions:**
- [x] Using trusted publishing (OIDC) instead of API tokens -- already implemented
- [ ] Ensure `pyproject.toml` has correct license classifier and license file
- [ ] Review PyPI Acceptable Use Policy before first publish

---

## 3. Tier B: Detected/Mentioned Services

These services are referenced in `evolution/data/sdk_fingerprints.json` and detected by `evolution/prescan.py`. Evolution Engine does NOT make API calls to these services directly. Instead, EE:
1. Detects their presence in a repository (config files, package dependencies, import statements)
2. Mentions their name in analysis output (e.g., "Datadog detected", "evo-adapter-datadog available")
3. Suggests future adapter plugins for these services

**General Legal Analysis for All Detected Services:**

Since EE only detects the presence of these tools and mentions them by name, the legal analysis is primarily about **trademark/nominative fair use**, not API terms.

Under US trademark law, [nominative fair use](https://en.wikipedia.org/wiki/Nominative_use) permits referencing a trademark to identify the trademark holder's product, provided:
1. The product is not readily identifiable without the mark
2. Only as much of the mark as is necessary is used
3. The use does not suggest endorsement or sponsorship

EE's use pattern ("Datadog detected in your repository") satisfies all three criteria. We refer to the product by name to identify it, use only the text name (not logos), and do not imply endorsement.

### 3.1 Datadog

**What EE does:** Detects Datadog via config files (`datadog.yaml`), packages (`dd-trace`, `ddtrace`), and imports.
**Family:** Monitoring
**Future adapter:** `evo-adapter-datadog`

**Trademark/branding:**
- [Datadog Website Terms of Use](https://www.datadoghq.com/legal/terms/): "Trademarks, logos and service marks displayed on the Website are the property of Datadog or third parties. You are not permitted to use these Marks without the prior written consent of Datadog or such third party."
- This applies to logo/mark usage, not textual references in a fair-use context.

**Risk Level: LOW** -- Detection only, nominative fair use for text mentions.

**Recommended actions:**
- [ ] Do NOT use the Datadog logo (the dog mascot "Bits") without permission
- [ ] Use only the text name "Datadog" in descriptive context
- [ ] If creating a Datadog adapter that calls their API, review their [Marketplace Terms](https://www.datadoghq.com/legal/marketplace-terms/)

### 3.2 New Relic

**What EE does:** Detects via config files (`newrelic.yml`), packages (`newrelic`, `@newrelic/native-metrics`), and imports.
**Family:** Monitoring
**Future adapter:** `evo-adapter-newrelic`

**Trademark/branding:**
- [New Relic Developer Terms](https://newrelic.com/termsandconditions/developers): Developers may use New Relic names and logos to "promote their App's availability for use with the New Relic Service" per New Relic Trademark Guidelines.
- Name must always include a space with "N" and "R" capitalized: "New Relic" (not "new relic" or "NewRelic").
- Contact: legal@newrelic.com

**Risk Level: LOW** -- Detection only.

**Recommended actions:**
- [ ] Always capitalize as "New Relic" in all output and documentation

### 3.3 Sentry

**What EE does:** Detects via config files (`.sentryclirc`), packages (`@sentry/node`, `sentry-sdk`), and imports.
**Family:** Error Tracking
**Future adapter:** `evo-adapter-sentry`

**Trademark/branding:**
- [Sentry Terms of Service](https://sentry.io/terms/): "You have no right under these Terms to use Sentry's trademarks, trade names, service marks or product names" except for identifying Sentry as the origin.
- Sentry's FSL (Functional Source License) allows descriptive reference.

**Risk Level: LOW** -- Detection only.

### 3.4 PagerDuty

**What EE does:** Detects via packages (`@pagerduty/pdjs`, `pypd`), and imports.
**Family:** Incidents
**Future adapter:** `evo-adapter-pagerduty`

**Trademark/branding:**
- [PagerDuty Terms of Service](https://www.pagerduty.com/terms-of-service/): Customers cannot remove or alter PagerDuty's logos or trademarks from Services.
- Standard nominative fair use for textual references.

**Risk Level: LOW** -- Detection only.

### 3.5 OpsGenie

**What EE does:** Detects via packages (`opsgenie-sdk`, `@opsgenie/sdk`).
**Family:** Incidents
**Future adapter:** `evo-adapter-opsgenie`

**Note:** OpsGenie is an Atlassian product. See Jira/Atlassian trademark rules below.

**Risk Level: LOW** -- Detection only.

### 3.6 Snyk

**What EE does:** Detects via config files (`.snyk`) and packages (`snyk`, `@snyk/protect`).
**Family:** Security Scanning
**Future adapter:** `evo-adapter-snyk`

**Trademark/branding:**
- [Snyk Terms of Service](https://snyk.io/procurement/purchasing-terms/): "All product and company names and logos are trademarks of their respective owners."
- Their ToS prohibits using the Services to "provide services to third parties" -- this would apply to an adapter that calls Snyk's API, not to mere detection.

**Risk Level: LOW** -- Detection only. MEDIUM if building an adapter that calls their API.

**Recommended actions:**
- [ ] If building a Snyk adapter, carefully review their ToS regarding third-party service provision

### 3.7 Semgrep

**What EE does:** Detects via config files (`.semgrep.yml`) and packages (`semgrep`).
**Family:** Security Scanning
**Future adapter:** `evo-adapter-semgrep`

**Risk Level: LOW** -- Detection only. Semgrep is open-source (LGPL-2.1).

### 3.8 SonarQube

**What EE does:** Detects via config files (`sonar-project.properties`) and packages.
**Family:** Quality Gate
**Future adapter:** `evo-adapter-sonarqube`

**Risk Level: LOW** -- Detection only. SonarQube Community Edition is open-source (LGPL-3.0).

### 3.9 Codecov

**What EE does:** Detects via config files (`codecov.yml`) and packages.
**Family:** Quality Gate
**Future adapter:** `evo-adapter-codecov`

**Risk Level: LOW** -- Detection only.

### 3.10 Grafana

**What EE does:** Detects via config files (`grafana.ini`), packages, and imports.
**Family:** Monitoring
**Future adapter:** `evo-adapter-grafana`

**Risk Level: LOW** -- Detection only. Grafana OSS is AGPL-3.0.

### 3.11 Prometheus

**What EE does:** Detects via config files (`prometheus.yml`), packages, and imports.
**Family:** Monitoring
**Future adapter:** `evo-adapter-prometheus`

**Risk Level: LOW** -- Detection only. Prometheus is open-source (Apache 2.0).

### 3.12 OpenTelemetry

**What EE does:** Detects via config files and packages (`@opentelemetry/api`, etc.).
**Family:** Monitoring
**Future adapter:** `evo-adapter-otel`

**Risk Level: LOW** -- Detection only. OpenTelemetry is open-source (Apache 2.0) under CNCF.

### 3.13 Elastic APM

**What EE does:** Detects via packages (`elastic-apm-node`, `@elastic/apm-rum`) and imports.
**Family:** Monitoring
**Future adapter:** `evo-adapter-elastic`

**Risk Level: LOW** -- Detection only. Elastic products have mixed licensing (SSPL + Elastic License).

### 3.14 Azure Monitor

**What EE does:** Detects via packages (`applicationinsights`) and imports.
**Family:** Monitoring
**Future adapter:** `evo-adapter-azure-monitor`

**Risk Level: LOW** -- Detection only. Microsoft has extensive trademark guidelines; textual reference is fine.

### 3.15 Jira (Atlassian)

**What EE does:** Detects via packages (`jira`, `jira-client`) and imports.
**Family:** Work Items
**Future adapter:** `evo-adapter-jira`

**Trademark/branding:**
- [Atlassian Trademark Policy](https://www.atlassian.com/legal/trademark): Atlassian embraces "fair use" of its trademarks. You may use them "to the extent necessary to identify Atlassian and its family of products in your website, blog, news article, or product review, without written consent," as long as usage is not deceptive.
- If referencing Jira in a product name, use must be part of a referential phrase: "for," "for use with," or "compatible with" (e.g., "evo-adapter for Jira").
- Contact: trademarks@atlassian.com

**Risk Level: LOW** -- Detection only. Atlassian is explicitly supportive of fair use references.

**Recommended actions:**
- [ ] Ensure adapter names use referential phrases: "evo-adapter-jira" is acceptable as it describes the adapter's function
- [ ] Do NOT use the Jira or Atlassian logo without permission

### 3.16 Linear

**What EE does:** Detects via packages (`@linear/sdk`).
**Family:** Work Items
**Future adapter:** `evo-adapter-linear`

**Risk Level: LOW** -- Detection only.

### 3.17 Qodo (CodiumAI)

**What EE does:** Detects via config files (`.codiumai`, `qodo.yml`) and packages.
**Family:** Code Review
**Future adapter:** `evo-adapter-qodo`

**Risk Level: LOW** -- Detection only.

### 3.18 CodeRabbit

**What EE does:** Detects via config files (`.coderabbit.yaml`).
**Family:** Code Review
**Future adapter:** `evo-adapter-coderabbit`

**Risk Level: LOW** -- Detection only.

### 3.19 LaunchDarkly

**What EE does:** Detects via packages (`launchdarkly-node-server-sdk`, `ldclient-py`) and imports.
**Family:** Feature Flags
**Future adapter:** `evo-adapter-launchdarkly`

**Trademark/branding:**
- [LaunchDarkly Terms of Service](https://launchdarkly.com/policies/terms-of-service-apr082020/): "No license, right or interest in any LaunchDarkly trademark, copyright, trade name or service mark is granted."

**Risk Level: LOW** -- Detection only.

### 3.20 Unleash

**What EE does:** Detects via packages (`unleash-client`, `@unleash/proxy-client-react`) and imports.
**Family:** Feature Flags
**Future adapter:** `evo-adapter-unleash`

**Risk Level: LOW** -- Detection only. Unleash OSS is Apache 2.0.

### 3.21 Statuspage

**What EE does:** Listed in fingerprints with no detection methods (empty arrays).
**Family:** Incidents
**Future adapter:** `evo-adapter-statuspage`

**Note:** Statuspage is an Atlassian product. Same trademark rules as Jira.

**Risk Level: LOW** -- No detection, just listed in fingerprint DB.

---

## 4. Tier C: Infrastructure and Hosting Services

### 4.1 GitLab

**What we use it for:**
- Tier 2 API adapters: `gitlab_pipelines` (CI), `gitlab_releases` (deployment)
- Authentication: User-provided `GITLAB_TOKEN`
- Tier 1: Local config detection (`.gitlab-ci.yml`)

**Risk Level: LOW** -- Same pattern as GitHub: user's own token, their own repos. GitLab's API terms support integration tools.

### 4.2 Jenkins

**What we use it for:**
- Tier 2 API adapter: `jenkins` (CI)
- Authentication: User-provided `JENKINS_URL`
- Tier 1: Local detection (`Jenkinsfile`)
- Plugin system example in registry docs

**Risk Level: LOW** -- Jenkins is open-source (MIT). Self-hosted, no third-party API ToS concerns.

### 4.3 CircleCI

**What we use it for:**
- Tier 1: Local detection (`.circleci/config.yml`)
- No API adapter currently implemented

**Risk Level: LOW** -- Detection only.

---

## 5. Cross-Cutting Concerns

### 5.1 "Works With" / "Compatible With" Claims

Several services we detect are positioned as peers or even competitors (Datadog, Snyk, Qodo). Our marketing messaging states: "Existing tools (Qodo, Snyk, Datadog) are data sources, not competitors."

**Legal analysis:**
- Comparative advertising and compatibility claims are generally permitted under US trademark law as nominative fair use.
- We should use phrasing like "compatible with" or "works alongside" rather than implying partnership or endorsement.
- The phrase "data sources" is factually accurate -- EE aggregates signals from these tools.

**Recommended actions:**
- [ ] Use "compatible with" or "works with" phrasing, never "powered by" or "endorsed by" for third-party tools
- [ ] Add a general disclaimer on the website: "Product names mentioned are trademarks of their respective owners. Evolution Engine is an independent product and is not affiliated with, endorsed by, or sponsored by any of the third-party tools it detects."
- [ ] On the website, use text-only mentions (no logos) for third-party tools unless explicit permission is obtained

### 5.2 User Data Flow

EE's architecture is intentionally local-first:
- All analysis runs on the user's machine
- GitHub/GitLab API calls use the user's own tokens
- Anthropic/OpenRouter API calls use the user's own keys
- No code ever leaves the machine (only anonymized patterns if KB sync is enabled at privacy level 2)
- Telemetry is opt-in, anonymous, and collects only command names and adapter counts

This architecture significantly reduces third-party ToS risk because EE acts as a tool on behalf of the authenticated user, not as a data aggregator.

### 5.3 KB Sync and Community Registry

The `evolution/kb_sync.py` module communicates with `https://registry.codequal.dev/v1` (our own API). This is first-party infrastructure, not third-party, but warrants mention:
- Privacy level 0 (default): Nothing shared
- Privacy level 1: Anonymous metadata only (family counts, risk levels)
- Privacy level 2: Anonymized pattern digests (no code, no file paths)

No third-party ToS concerns, but our own privacy policy must accurately describe this data flow.

### 5.4 Claude Code CLI Integration

The `evolution/agents/cli_agent.py` invokes `claude` (Claude Code CLI) as a subprocess. This is different from the API integration:
- We do NOT use Anthropic's API directly in this path; we invoke the user's installed CLI tool.
- The user must have their own Claude Code subscription/license.
- As of January 2026, Anthropic has deployed safeguards against tools that spoof the Claude Code client. Our integration invokes the real `claude` binary, which is the supported pattern.

**Risk Level: LOW** -- We are an upstream consumer of the CLI, not a wrapper or proxy.

---

## 6. Risk Summary Matrix

| Service | Integration Type | Risk | Key Concern |
|---------|-----------------|------|-------------|
| **GitHub** | Direct API | **MEDIUM** | Registered Developer Agreement "service bureau" clause; rate limits |
| **Anthropic** | Direct API | LOW | Standard commercial API usage |
| **OpenRouter** | Direct API | LOW | Data rights if user has logging enabled |
| **Stripe** | Direct API | LOW | Standard payment processing |
| **Axiom** | Direct API | LOW | Standard observability |
| **Vercel** | Hosting | **MEDIUM** | Must be on paid plan for commercial use |
| **PyPI** | Distribution | LOW | Standard package publishing |
| **GitLab** | User-token API | LOW | Same pattern as GitHub |
| **Jenkins** | User-token API | LOW | Open-source, self-hosted |
| **Datadog** | Detection only | LOW | Trademark: no logo usage without permission |
| **New Relic** | Detection only | LOW | Capitalize as "New Relic" |
| **Sentry** | Detection only | LOW | Nominative fair use |
| **Snyk** | Detection only | LOW | MEDIUM if building an adapter |
| **Jira/Atlassian** | Detection only | LOW | Use referential phrases for product names |
| All others (13) | Detection only | LOW | Standard nominative fair use |

---

## 7. Priority Action Items

### Critical (Before Commercial Launch)

1. **Verify Vercel Pro plan** -- Using the Hobby plan for a revenue-generating product (codequal.dev with Stripe checkout) violates Vercel ToS.

2. **Replace dev signing key in production** -- `webhook.py` hardcodes `"evo-license-v1-dev-key-replace-in-production"`. Must use `EVO_LICENSE_SIGNING_KEY` from environment in production.

3. **Add third-party trademark disclaimer** -- Add to website footer and documentation:
   > "Product names, logos, and brands are property of their respective owners. Evolution Engine is an independent product and is not affiliated with, endorsed by, or sponsored by any third-party tools it integrates with or detects."

### High Priority (Within 30 Days of Launch)

4. **Add "Powered by Claude" attribution** where investigation results are displayed (Anthropic best practice).

5. **Review GitHub Registered Developer Agreement** in full and consider whether to register as a GitHub Developer Program participant or create a GitHub App for better rate limits.

6. **Ensure `pyproject.toml` license** is correctly declared before first PyPI publish.

7. **Document data flow for each integration** in a user-facing privacy/security page, covering:
   - What tokens are used for
   - What data is sent where
   - What stays local

### Medium Priority (Within 90 Days)

8. **Review Stripe Acceptable Use Policy** for prohibited business categories.

9. **Audit marketing copy** for any implied partnerships or endorsements with third parties.

10. **Contact GitHub trademarks team** (trademarks@github.com) about logo usage if we want to display the GitHub mark on the website.

11. **Review OpenRouter necessity** -- If Phase 3 LLM is retired, consider removing the OpenRouter client to reduce third-party dependency surface.

12. **Create brand guidelines** for how adapter plugin authors should reference third-party services (Tier 3 plugin ecosystem).

### Low Priority (Ongoing)

13. **Monitor ToS changes** for GitHub, Anthropic, and Stripe -- these are the three highest-impact dependencies.

14. **Consider GitHub App registration** for improved rate limits (5,000/hr per installation) and better UX (no PAT management).

15. **Review Axiom data retention** settings to align with privacy policy commitments.

---

## Sources

### Official Terms of Service Pages
- [GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)
- [GitHub Registered Developer Agreement](https://docs.github.com/en/site-policy/github-terms/github-registered-developer-agreement)
- [GitHub Trademark Policy](https://docs.github.com/en/site-policy/content-removal-policies/github-trademark-policy)
- [GitHub Acceptable Use Policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)
- [GitHub Rate Limits for REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [GitHub Marketplace Developer Agreement](https://docs.github.com/en/site-policy/github-terms/github-marketplace-developer-agreement)
- [Anthropic Usage Policy Update](https://www.anthropic.com/news/usage-policy-update)
- [Anthropic Expanded Legal Protections](https://www.anthropic.com/news/expanded-legal-protections-api-improvements)
- [Stripe Services Agreement](https://stripe.com/legal/ssa)
- [Stripe Mark Usage Terms](https://stripe.com/legal/marks)
- [Stripe User Terms Update (November 2025)](https://support.stripe.com/questions/stripe-user-terms-update-november-18-2025)
- [Axiom Terms of Service](https://www.axiom.co/terms/)
- [Vercel Terms of Service](https://vercel.com/legal/terms)
- [Vercel Fair Use Guidelines](https://vercel.com/docs/limits/fair-use-guidelines)
- [OpenRouter Terms of Service](https://openrouter.ai/terms)
- [PyPI Terms of Use](https://policies.python.org/pypi.org/Terms-of-Use/)
- [PyPI Terms of Service](https://policies.python.org/pypi.org/Terms-of-Service/)
- [Datadog Website Terms of Use](https://www.datadoghq.com/legal/terms/)
- [New Relic Developer Terms](https://newrelic.com/termsandconditions/developers)
- [Sentry Terms of Service](https://sentry.io/terms/)
- [Snyk Terms of Service](https://snyk.io/procurement/purchasing-terms/)
- [Atlassian Trademark Policy](https://www.atlassian.com/legal/trademark)
- [Atlassian Developer Terms](https://developer.atlassian.com/platform/marketplace/atlassian-developer-terms/)
- [LaunchDarkly Terms of Service](https://launchdarkly.com/policies/terms-of-service-apr082020/)
- [PagerDuty Terms of Service](https://www.pagerduty.com/terms-of-service/)

### Analysis and Commentary
- [GitHub Community Discussion: Building apps using GitHub API](https://github.com/orgs/community/discussions/172999)
- [Anthropic 2025-2026 Policy Changes](https://aihackers.net/posts/anthropic-tos-changes-2025/)
- [Who Owns Claude-Generated Code](https://www.arsturn.com/blog/who-owns-claude-generated-code-a-guide-for-developers-and-businesses)
- [Anthropic Claude AI Updated Terms](https://amstlegal.com/anthropics-claude-ai-updated-terms-explained/)
- [PyPI New Terms of Service (February 2025)](https://blog.pypi.org/posts/2025-02-25-terms-of-service/)

---

*This review is for internal planning purposes and does not constitute legal advice. Consult a qualified attorney before making final compliance decisions.*
