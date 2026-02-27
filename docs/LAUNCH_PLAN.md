# Evolution Engine — Launch Plan

> **Actionable roadmap for solo-founder beta launch.**
>
> Compiled from research on: solo founder positioning, EU AI Act compliance,
> Stripe beta discounts, and existing documentation audit.
>
> **Created:** February 11, 2026
> **Last updated:** February 12, 2026

---

## 1. Pre-Launch Blockers (This Week)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | PyPI publication | **BLOCKER** | `python -m build && twine upload dist/*` — test on TestPyPI first |
| 2 | Stripe e2e test | **BLOCKER** | Full test matrix below (Section 2.1), including FOUNDING50 coupon |
| 3 | Lawyer review | **IN PROGRESS** | PDFs sent for review (`docs/legal/*.pdf`); after sign-off → upload corrected docs → translator verification |
| 4 | Translation review | Blocked on #3 | DE/ES translations need native speaker validation after lawyer corrections |
| 5 | Language switcher deploy | Done | Pushed 2026-02-11 (absolute paths + Vercel routes) |
| 6 | Report improvements | Done | Severity badges, risk banners, grouped cards, IP sanitization |
| 7 | GitLab manual testing | **BLOCKER** | 7-scenario test matrix (Section 12.2) — code verified, needs manual walkthrough |
| 8 | User review flow testing | **BLOCKER** | End-to-end: analyze → accept → investigate → fix → verify (Section 12.4) |
| 9 | Accept deviations | Done | `evo accept` + `evo accepted` (list/remove/clear), 12 tests |

### 1.1 GitLab Compatibility Testing

Before launch, verify Evolution Engine works with GitLab-hosted repositories:

- [ ] Clone 3 public GitLab.com repos, run `evo analyze` on each
- [ ] Verify git adapter handles GitLab remote URL formats (`https://gitlab.com/...` and `git@gitlab.com:...`)
- [ ] Test `evo sources` detects `.gitlab-ci.yml` as a CI config
- [ ] Document that Tier 2 API adapters (CI runs, releases, security) are GitHub-only for now
- [ ] Confirm `_infer_github_remote()` in orchestrator returns `(None, None)` for GitLab remotes without crashing

**Expected outcome:** Git-level analysis (Phase 1-5) works fully on GitLab repos. Tier 2 API features (CI run history, release data, security advisories) are GitHub-only and should degrade gracefully with a clear message.

---

## 2. Stripe Beta Discount Setup

**Approach: 50% coupon for 3 months (auto-expires)**

### Steps:
1. **Dashboard -> Products -> Coupons -> New**
   - Percentage off: 50%
   - Duration: Repeating, 3 months
   - Max redemptions: 50
   - Redemption deadline: set to beta end date

2. **Create promotion code** from the coupon:
   - Code: `FOUNDING50`
   - This is what beta testers enter at checkout

3. **Code change** — add `allow_promotion_codes=True` to checkout session:
   ```python
   checkout_session = stripe.checkout.Session.create(
       mode="subscription",
       line_items=[{"price": "price_xxx", "quantity": 1}],
       allow_promotion_codes=True,  # <- only change needed
       success_url="...",
       cancel_url="...",
   )
   ```

4. **Webhook** — existing handler covers it. Optionally add `customer.discount.deleted` to notify when coupon expires.

**Pricing psychology:** Call it "founding member pricing," not a discount. "$9.50/month for founding members. Regular price: $19/month."

**Transition:** Automatic. Stripe bills full price on month 4. Send email at week 11: "Your founding member rate expires in 2 weeks. Thank you for being an early tester."

**Fallback:** If churn >40% at transition, offer $14/month "permanent founding member" rescue price.

### 2.1 Comprehensive Stripe Test Scenarios

Run all tests in Stripe test mode before launch:

**Checkout Flow:**
- [ ] Happy path: complete checkout with test card `4242 4242 4242 4242` -> verify subscription created
- [ ] Apply coupon: enter `FOUNDING50` at checkout -> verify 50% discount applied
- [ ] Abandoned checkout: start checkout, close browser -> verify no subscription created, no charge
- [ ] Declined card: use test card `4000 0000 0000 0002` -> verify graceful error message

**Webhook Reliability:**
- [ ] Idempotency: send same webhook event twice -> verify license not duplicated
- [ ] Signature mismatch: send webhook with invalid signature -> verify 400 response, no action taken
- [ ] Missing env vars: remove `STRIPE_WEBHOOK_SECRET` -> verify handler returns error without crashing
- [ ] Event ordering: send `invoice.paid` before `checkout.session.completed` -> verify correct handling

**License Key Chain:**
- [ ] Generate: complete checkout -> verify license key generated with correct tier and email
- [ ] Validate: run `evo license status` with generated key -> verify "Pro" tier shown
- [ ] Mismatch: use key from different email -> verify rejection with clear error
- [ ] Clear: run `evo license clear` -> verify returns to free tier

**Subscription Lifecycle:**
- [ ] Renewal: trigger `invoice.paid` for month 2 -> verify license stays active
- [ ] Coupon expiry: simulate month 4 billing at full price -> verify no disruption
- [ ] Cancel: cancel subscription in dashboard -> verify license deactivated on next validation
- [ ] Resubscribe: cancel then re-subscribe -> verify new license key works

**Edge Cases:**
- [ ] Duplicate email: two checkouts with same email -> verify only one active subscription
- [ ] Cold start timeout: first webhook after deploy -> verify Vercel function responds within 10s
- [ ] Currency: verify checkout shows USD (or user's local currency if configured)

---

## 3. Beta Program Structure

### Cohort
- **Target: 30 active testers** (recruit 50-60, expect 50% to engage regularly)
- Solo founder can support 30 without it becoming a second job
- Local-first = no infrastructure scaling concerns

### Two Phases

**Month 1 — Private Alpha (10 users)**
- High-touch: DM each user, offer 15-min call
- Focus: installation issues, false positive rates, critical bugs
- Source: Reddit posts to targeted subreddits

**Months 2-3 — Private Beta (30-50 users)**
- Lower-touch: weekly update email, respond to issues within 24 hours
- Focus: pattern quality, GitHub Action reliability, PR comment usefulness
- Source: Show HN + Reddit + community posts

### Feedback Collection
- **Primary:** GitHub Issues with `beta-feedback` label
- **Secondary:** Monthly 5-question survey (Tally/Typeform)
  1. How often did you run `evo` this week?
  2. Did it surface anything you didn't already know?
  3. What was confusing or broken?
  4. What feature would make you recommend it?
  5. NPS (1-10)
- **Do NOT create Discord/Slack yet** — wait until 100+ active users

### Beta Application Form (4 fields)
- GitHub username
- Primary repo you'd analyze
- Current monitoring tools (Dependabot, Snyk, Datadog, etc.)
- How did you hear about Evolution Engine?

### Promises & Non-Promises

**Promise:** Direct founder access, roadmap influence, founding member pricing, 1-week notice for breaking changes.

**Don't promise:** SLAs, guaranteed response times, specific feature delivery, permanent beta pricing.

---

## 4. Finding Beta Testers

### Tier 1: Reddit Posts (First 10-20 users)

Reddit is the primary acquisition channel. No cold emails, no DMs to strangers.

| Subreddit | Angle | Key message |
|-----------|-------|-------------|
| **r/devops** | CI + dependency correlation | "I built a CLI that correlates CI failures with dependency changes to find which updates actually break things" |
| **r/programming** | Cross-signal methodology | "What 43 open-source repos taught me about predicting CI failures from git patterns" |
| **r/selfhosted** | Local-first, privacy | "Your code never leaves your machine — a local-first CLI for codebase evolution analysis" |
| **r/Python** | 5-phase pipeline, Cython | "Building a 5-phase analysis pipeline in Python with Cython for the hot path" |
| **r/commandline** | Terminal demo | "Terminal demo: correlating git, CI, and deployment signals in one command" |
| **r/opensource** | Pattern dataset | "I'm open-sourcing correlation patterns from 43 repos — here's what I found" |

**Rules:**
- Disclose authorship clearly: "I built this" / "I'm the developer of..."
- Lead with insight, not tool promotion — teach something valuable even without EE
- Respond to every comment within 4 hours
- Space posts 3-5 days apart — never post to multiple subreddits on the same day
- Include beta application link in each post

### Tier 2: DE/ES Social Media

**German audience:** Privacy-conscious, local-first resonates strongly.
- **LinkedIn (DE):** Professional developer audience, post in German about local-first tooling and data sovereignty
- **Mastodon** (fosstodon.org): Open-source community, privacy angle, post in German/English
- **r/de_EDV:** German IT subreddit, technical deep-dive in German
- Link directly to translated website pages (`/de/`)

**Spanish audience:** Growing LatAm open-source community.
- **Twitter/X (ES):** Thread in Spanish about cross-signal correlation methodology
- **Dev.to (ES):** Blog post cross-post in Spanish (canonical to codequal.dev/es/)
- **r/programacion:** Spanish programming subreddit, implementation deep-dive
- Link directly to translated website pages (`/es/`)

### Tier 3: Community (Ongoing)

- **Show HN** (main event, week 5) — Tuesday-Thursday, 9-11am ET
- **Dev.to** cross-posts (canonical to codequal.dev)
- **platformengineering.org Slack**, DevOps Chat, Hangops
- **Podcast guest spots** (voice only, no video — see Section 5) — target <5K listener shows
- **Twitter/X + Bluesky** — build-in-public thread with terminal screenshots (ongoing)

**NOT doing:**
- No cold emails or DMs to maintainers
- No mass outreach campaigns
- No paid ads (organic first, no ROI at this scale)

---

## 5. Founder Positioning — Anonymity Strategy

### Alias Approach

Operate under a consistent alias across all platforms to protect employment at current employer.

**Do:**
- Use a consistent alias (same handle everywhere)
- Use an avatar/logo instead of a photo on all profiles
- Write in first person ("I built this because..."), never fake "we"
- Be transparent about being a solo founder under an alias
- Pin the repo on GitHub (under alias account), keep contribution graph active
- Respond to GitHub issues within hours (your #1 competitive advantage)
- Record terminal demos (asciinema/vhs) — no face, no voice
- Write technically deep blog posts that teach something even without the tool

**Don't:**
- No real name on any public-facing material
- No employer references anywhere — not in bio, posts, or conversations
- No live video without a presenter (see below)
- No personal email — use a dedicated project email
- Don't buy ads yet (organic first)
- Don't create empty Discord/Slack communities
- Don't hire a content writer (devs detect non-technical marketing instantly)
- Don't launch on all channels simultaneously (stagger by 2-3 days)
- Don't position against tools — position as the aggregation layer

### Presenter Option (Video/Audio)

For content that requires a human presence:
- **YouTube demos:** Hire a presenter for walkthrough videos
- **Podcast appearances:** Presenter or voice-only (no video)
- **Conference talks:** Presenter delivers, founder provides content
- Founder stays behind the scenes for all video/audio content

### Rules
1. No real name appears in any commit, profile, or public communication
2. No employer reference — ever, even casually
3. Separate email for all project communication
4. No live video without a presenter
5. Consistent alias across GitHub, Reddit, Twitter, Mastodon, Dev.to

---

## 6. Content Strategy

### Blog Posts (in priority order)

1. **"What 43 Open-Source Repos Taught Me About CI Failure Patterns"**
   — Original research from calibration data. No one else has this.

2. **"Why Your Dependency Updates Break Unrelated Code (And How to Predict It)"**
   — Cross-family correlation concept. Problem-focused.

3. **"Local-First Developer Tools: Why Your Code Should Never Leave Your Machine"**
   — Privacy positioning. Will resonate on Mastodon, r/selfhosted.

4. **"I Analyzed 40 Repos to Find a 1.6% False Positive Rate — Here's My Methodology"**
   — Technical credibility for accuracy-focused developers.

5. **"Building a 5-Phase Analysis Pipeline in Python (With Cython for the Hot Path)"**
   — Implementation deep-dive. Attracts Python contributors.

### Comparison Pages (on codequal.dev)
- "EE vs Snyk" — "Snyk scans vulnerabilities. We correlate its signals with your git and CI patterns."
- "EE vs Datadog" — "Datadog monitors production. We analyze development patterns."
- "EE vs SonarQube" — Complementary, not competitive. Aggregation layer positioning.

### Open Source as Marketing
- Publish `universal_patterns.json` as standalone repo: `codequal/universal-repo-patterns`
- Create a small GitHub Action that reports file dispersion on PRs (drives concept awareness)
- Contribute to adjacent tools (gitpython, CI analysis libraries)

---

## 7. EU AI Act Compliance

### Classification: **Minimal Risk**

Evolution Engine does NOT fall into any Annex III high-risk category. It analyzes code repositories, not natural persons. No registration, CE marking, conformity assessment, or risk management system required.

### One Obligation: Article 50 Transparency (by August 2, 2026)

The `evo investigate` and `evo fix` features use third-party AI (Claude/ChatGPT). While the "obvious" exception likely applies (developers explicitly provide API keys), add disclosure as best practice:

**Action items:**
1. Add to CLI output when AI features run: `"This feature uses AI (Claude/ChatGPT) to analyze your code."`
2. Add "AI Transparency" section to privacy page
3. Write 1-2 page internal memo documenting minimal-risk classification (defensive measure)

### GDPR (Already Covered)
- Privacy policy (website/privacy.html)
- Telemetry is opt-in
- Code stays local
- Stripe handles payment data

### Not Required
- No CE marking, no EU AI database registration
- No fundamental rights impact assessment
- No post-market monitoring plan, no notified body audit
- No Data Protection Officer at this scale

---

## 8. Launch Timeline

### Week 0 (Current — Feb 11-14)
- [x] Report improvements (severity, grouping, IP sanitization)
- [x] Language switcher fix deployed
- [x] Accept deviations (`evo accept` + `evo accepted`) — 12 tests
- [x] Legal docs converted to PDF for lawyer review (5 docs)
- [x] GitLab compatibility verified in code (516 commits, 677 events, 8 adapters)
- [ ] Lawyer review of ToS + Privacy — **in progress**, awaiting sign-off
- [ ] Stripe sandbox e2e test (full matrix — Section 2.1)
- [ ] GitLab manual testing (7 scenarios — Section 12.2)
- [ ] User review flow testing (analyze → accept → investigate → fix → verify — Section 12.4)
- [ ] Translation validation (DE/ES) — blocked on lawyer review

### Week 1 (Feb 17-21) — Technical Readiness
- [ ] **BLOCKER: Production license signing key** — do ALL of these before first real customer:
  1. Generate key: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
  2. Save to password manager (this key is permanent — rotating it invalidates all paid licenses)
  3. Set on Vercel: `EVO_LICENSE_SIGNING_KEY` env var (Production + Preview)
  4. Set in GitHub Actions secrets: `EVO_LICENSE_SIGNING_KEY` (used by cibuildwheel to bake into Cython binaries)
  5. Rebuild + publish wheels (key is embedded in compiled `license.so`, not readable as plaintext)
  6. Verify: purchase with test Stripe → activate with `evo activate` → confirm Pro features work
- [ ] Switch Stripe to live mode (only after signing key is deployed end-to-end)
- [ ] PyPI TestPyPI upload + test install on clean machine
- [ ] PyPI production upload
- [ ] Add `allow_promotion_codes=True` to checkout handler
- [ ] Create Stripe coupon (FOUNDING50, 50% off, 3 months, max 50)
- [ ] Add AI transparency disclosure to CLI (`evo investigate`, `evo fix`)
- [x] Add `run_number` + timestamps to telemetry (activation/retention metrics)
- [x] Set up Axiom dashboard + monitors (5 dashboards, 3 alerts — Feb 26)
- [ ] Record terminal demo (asciinema, no face/voice — alias only)
- [ ] README hero section with terminal demo embed

### Week 2 (Feb 24-28) — Reddit Launch + Beta Applications
- [ ] Create beta application form (Tally/Google Form)
- [ ] Publish first Reddit post (**r/devops** — CI+dependency correlation angle)
- [ ] Write blog post #1 ("What 43 Repos Taught Me")
- [ ] Draft DE/ES social media posts (German LinkedIn, Spanish Twitter thread)
- [ ] Goal: 10 beta applications

### Week 3-4 (Mar 3-14) — Reddit Momentum + Alpha Support
- [ ] Post to **r/programming** (technical deep-dive)
- [ ] Post to **r/selfhosted** (local-first angle)
- [ ] High-touch alpha support (DM each tester, offer calls)
- [ ] Fix critical bugs from alpha feedback
- [ ] Write blog post #2 ("Why Dependency Updates Break Code")
- [ ] Draft Show HN post + first comment
- [ ] Monitor Reddit, engage every commenter
- [ ] Collect beta sign-ups from Reddit engagement
- [ ] Post to r/Python, r/commandline (staggered)

### Week 5 (Mar 17-21) — Show HN + DE Social Media
- [ ] **Monday: Show HN** (the main event)
  - Monitor comments for 12 hours, reply within 30 min
  - Post on Twitter/X linking to HN discussion
- [ ] **Tuesday: German LinkedIn post** (privacy/local-first angle)
- [ ] **Wednesday: Mastodon** (fosstodon, German/English)
- [ ] **Thursday: r/de_EDV** (German IT community)
- [ ] Goal: expand to 30-50 beta testers

### Week 6-7 (Mar 24 - Apr 4) — ES Social Media + Momentum
- [ ] Spanish Twitter thread
- [ ] Dev.to cross-post (Spanish, canonical to codequal.dev/es/)
- [ ] r/programacion post
- [ ] Write comparison pages (vs Snyk, vs Datadog)
- [ ] Ask beta users for genuine reviews

### Weeks 8-12 (Apr 7 - May 16) — Beta Sustain
- [ ] One blog post per week
- [ ] Monthly feedback survey
- [ ] Ship improvements based on feedback
- [ ] Daily Twitter/X engagement (5-10 min)
- [ ] Track: activation rate, weekly active users, NPS

### Week 13 (May 19) — Beta End / GA Decision
- [ ] Coupon auto-expires
- [ ] Send transition email at week 11
- [ ] Monitor churn rate at full-price transition
- [ ] If churn >40%, offer $14/month founding member rescue
- [ ] Collect exit interviews from churned users
- [ ] Decide: GA launch or extend beta

---

## 9. Success Metrics

| Metric | Target (Month 1) | Target (Month 3) |
|--------|-------------------|-------------------|
| Website visitors | 10,000+ | 5,000/month steady |
| GitHub stars | 200+ | 500+ |
| Free tier activations | 200-500 | 500+ cumulative |
| Pro conversions | 10-25 ($190-475 MRR) | 30-50 ($570-950 MRR) |
| Beta NPS | 30+ | 40+ |
| FP rate (real repos) | <2% | <1.5% |

### 9.1 Leading Indicators (Axiom Dashboard)

These are the signals that predict retention and conversion. All derived from the `analyze_complete` telemetry event, which now includes `run_number` (lifetime analysis count per anonymous user).

| Indicator | Formula | Target | Why It Matters |
|-----------|---------|--------|----------------|
| **Activation rate** | % of `anon_id`s with `run_number >= 2` in first 7 days | >40% | Users who run twice are retained |
| **Time-to-second-run** | Median days between `run_number=1` and `run_number=2` | <3 days | Fast repeat = genuine interest |
| **Weekly active users** | Distinct `anon_id`s with events in trailing 7 days | Growing | Core health metric |
| **Retention (week 2)** | % of week-1 users still active in week 2 | >30% | Early churn signal |
| **Retention (week 4)** | % of week-1 users still active in week 4 | >20% | Sticky product signal |
| **Finding rate** | % of analyses with `signal_count >= 1` | >60% | Empty results = churn risk |
| **Pro feature trigger** | `investigate` and `fix` command frequency | Growing | Upsell readiness |

### 9.2 Axiom Dashboard & Monitors Setup

**Dashboard — create before beta launch (Week 1):**

1. **Overview panel**: total events/day, unique `anon_id`s/day, version distribution
2. **Activation funnel**: run_number=1 → run_number=2 → run_number=5 (by cohort week)
3. **Finding quality**: `signal_count` distribution, `pattern_count` distribution per analysis
4. **Command mix**: breakdown of `analyze_complete` vs `investigate` vs `fix` vs `report`
5. **Webhook health**: success/error rate for Stripe webhooks, license generation events
6. **Error panel**: `webhook_error` events, pattern push failures

**Monitors — alert to email (info@codequal.dev):**

| Monitor | Condition | Priority |
|---------|-----------|----------|
| Webhook failures | >2 `webhook_error` events in 1 hour | Critical |
| Zero telemetry | No `analyze_complete` events in 24 hours (after beta starts) | High |
| Activation drop | Week-over-week activation rate drops >20% | Medium |
| Error spike | >10 errors of any type in 1 hour | High |

---

## 10. Budget

| Item | Cost | Notes |
|------|------|-------|
| Claude Code sessions | ~$5/session | Development |
| GitHub API | $0 | Free tier (5,000 req/hr) |
| Vercel | $0 | Free tier sufficient for launch |
| Stripe | 2.9% + $0.30/txn | Standard rate |
| PyPI | $0 | Free |
| Plausible analytics | $9/month | Privacy-respecting (optional) |
| Newsletter sponsorship | $500-2,000 | Test one at week +5 (Changelog/TLDR) |
| **Total (Month 1)** | **~$50** | Excluding time |

---

## 11. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| HN post doesn't get traction | Reddit posts already running as primary channel. Show HN is amplification, not sole strategy. |
| High FP rate on user repos | 1.6% validated. Accept GitHub issues, fix within 24h. |
| Stripe payment failures | Comprehensive test matrix (Section 2.1). 30-day money-back guarantee in ToS. |
| Big company copies the approach | Moat = accumulated patterns + Cython engines + community data. Keep shipping. |
| EU AI Act enforcement | Minimal risk classification. Add transparency disclosure by Aug 2026. |
| Solo founder burnout | Limit support to GitHub Issues + email. No Discord until 100+ users. |
| Real identity discovered | All accounts under alias, no employer references, separate email, no live video without presenter. |
| GitLab compatibility issues | Test pre-launch (Section 1.1). Document Tier 2 API adapters are GitHub-only. Git analysis works on any host. |

---

## 12. Manual Testing Guide (New Features)

Test everything implemented in this session before moving to beta.

### 12.1 Run History Feature

**Setup:** Use any analyzed repo (e.g., `.calibration/runs/bat-api` or a fresh GitLab clone).

**Snapshot creation (auto):**
```bash
# First run — creates .evo/phase5/history/ with a snapshot
evo analyze /path/to/repo

# Verify snapshot was created
evo history list /path/to/repo
# Expected: 1 snapshot with timestamp, change count, families
```

**History list:**
```bash
# List all runs
evo history list /path/to/repo

# Limit to last 5
evo history list /path/to/repo -n 5

# JSON output (for scripting)
evo history list /path/to/repo --json
```

**History show (view a specific run):**
```bash
# Use full timestamp from list output
evo history show 20260212-042515-473148 /path/to/repo

# Or use prefix match (like git short hashes)
evo history show 20260212 /path/to/repo

# JSON output
evo history show 20260212 /path/to/repo --json
```

**History diff (compare two runs):**
```bash
# Clear .evo and run twice to get 2 snapshots
rm -rf /path/to/repo/.evo
evo analyze /path/to/repo
# (make a change or wait)
rm -rf /path/to/repo/.evo/events /path/to/repo/.evo/phase*signals*
evo analyze /path/to/repo

# Compare latest vs previous (default)
evo history diff /path/to/repo

# Compare specific runs
evo history diff 20260212-041500 20260212-042500 /path/to/repo

# JSON output
evo history diff /path/to/repo --json
```

**Expected diff output categories:**
- `RESOLVED` — changes that returned to normal
- `STILL UNUSUAL` — changes that persist (with improving/not improving)
- `NEW OBSERVATIONS` — new changes not in the previous run
- `REGRESSIONS` — new deviations in families that had changes before
- `Resolution rate: X%` — percentage of resolved changes

**History clean:**
```bash
# Keep only the 5 most recent snapshots
evo history clean /path/to/repo -k 5

# Delete snapshots before a date
evo history clean /path/to/repo --before 20260201

# Skip confirmation
evo history clean /path/to/repo -k 5 -y
```

**Edge cases to verify:**
- [ ] `evo history list` on a repo with no `.evo/` directory -> shows helpful message
- [ ] `evo history show nonexistent` -> shows error message
- [ ] `evo history diff` with only 1 snapshot -> shows "need at least 2 runs" message
- [ ] History never blocks the pipeline (if history dir is unwritable, analyze still completes)

### 12.2 GitLab Compatibility

**Prerequisites:**
- GitLab Personal Access Token (create at GitLab -> Preferences -> Access Tokens, scopes: `read_api`, `read_repository`)
- Token format: `glpat-...`

**Test 1: Source detection**
```bash
git clone https://gitlab.com/gitlab-org/gitlab-styles.git /tmp/gl-test
evo sources /tmp/gl-test
# Expected: detects git, .gitlab-ci.yml, Gemfile.lock
# Expected: suggests setting GITLAB_TOKEN for Tier 2
```

**Test 2: Full analysis (git-only, no token)**
```bash
evo analyze /tmp/gl-test
# Expected: git + dependency events ingested, advisory generated
# Expected: no crash from _infer_github_remote() returning (None, None)
```

**Test 3: Full analysis with GitLab token**
```bash
export GITLAB_TOKEN="glpat-your-token-here"
evo analyze /tmp/gl-test
# Expected: detects gitlab_pipelines (tier 2) and gitlab_releases (tier 2)
# Expected: Tier 2 API adapters attempt to fetch data
```

**Test 4: HTML report**
```bash
evo report /tmp/gl-test
open /tmp/gl-test/.evo/report.html
# Expected: valid HTML report with severity badges, grouped cards
```

**Test 5: History auto-snapshot**
```bash
evo history list /tmp/gl-test
# Expected: snapshot created from the analyze run
evo history show 20260212 /tmp/gl-test
# Expected: shows advisory details from GitLab repo analysis
```

**Test 6: Different GitLab URL formats**
```bash
# HTTPS format
git clone https://gitlab.com/inkscape/inkscape.git /tmp/gl-test2
evo analyze /tmp/gl-test2
# Expected: works without crash

# SSH format (if SSH key configured)
git clone git@gitlab.com:gitlab-org/gitlab-styles.git /tmp/gl-test3
evo analyze /tmp/gl-test3
# Expected: works without crash
```

**Test 7: Verify graceful degradation**
```bash
# Without GITLAB_TOKEN, Tier 2 should be skipped gracefully
unset GITLAB_TOKEN
evo analyze /tmp/gl-test
# Expected: only Tier 1 adapters run, no errors about missing token
```

**Results from automated testing (Feb 12, 2026):**
- `evo sources` detects `.gitlab-ci.yml` -> PASS
- `evo analyze` with GITLAB_TOKEN detects 8 adapters (3 Tier 1 + 5 Tier 2) -> PASS
- 677 events ingested (516 git + 161 dependency) -> PASS
- 5 significant changes detected in advisory -> PASS
- HTML report generates successfully -> PASS
- History snapshot auto-created -> PASS
- `evo history show` with prefix match -> PASS
- No crash from GitLab remote URL -> PASS

### 12.3 Phase 5 Diff Refactor Verification

The advisory diff logic was extracted from `phase5_engine.py` into `history.py`. Verify existing behavior is preserved:

```bash
# Run the full test suite
.venv/bin/python -m pytest tests/ -v
# Expected: 574 tests passing

# Specifically check Phase 5 advisory diff tests
.venv/bin/python -m pytest tests/unit/test_phase5_advisory.py -v -k "Diff"
# Expected: TestAdvisoryDiff tests pass (resolved, persisting, new)

# Check history tests
.venv/bin/python -m pytest tests/unit/test_history.py -v
# Expected: 29 tests passing

# Verify fix verification loop still works
evo verify /path/to/previous-advisory.json /path/to/repo
# Expected: same behavior as before refactor
```

### 12.4 User Review Flow (End-to-End)

Verify the complete user journey from analysis to fix verification, including the new accept deviations feature.

**Test 1: Analyze → Accept → Re-analyze**
```bash
# Run analysis
evo analyze /path/to/repo

# Note the numbered changes in output (e.g., 1-4)
# Accept changes #1 and #2 with a reason
evo accept /path/to/repo 1 2 --reason "Known refactoring spike"
# Expected: "Accepted 2 deviation(s): git / dispersion, ci / run_duration"

# Re-analyze — accepted changes should be hidden
evo analyze /path/to/repo
# Expected: only the unaccepted changes appear
```

**Test 2: Accepted management**
```bash
# List all accepted deviations
evo accepted list /path/to/repo
# Expected: shows 2 entries with age ("accepted today") and reason

# Remove one
evo accepted remove /path/to/repo git:dispersion
# Expected: "Removed: git:dispersion"

# Clear all
evo accepted clear /path/to/repo
# Expected: confirmation prompt, then "Cleared 1 accepted deviation(s)."
```

**Test 3: Investigate with accepted deviations**
```bash
# Accept some deviations, then investigate
evo accept /path/to/repo 1
evo investigate /path/to/repo --show-prompt
# Expected: investigation prompt only contains unaccepted changes
```

**Test 4: Fix loop respects accepted deviations**
```bash
# Accept known issues, fix only the unexpected ones
evo accept /path/to/repo 1 --reason "Expected"
evo fix /path/to/repo --dry-run
# Expected: fix prompt focuses on unaccepted changes only
```

**Edge cases:**
- [ ] `evo accept . 99` with invalid index -> shows "Invalid change number(s): 99 (valid range: 1-N)"
- [ ] `evo accept .` with no indices -> shows usage error
- [ ] `evo accepted list .` on repo with no accepted.json -> shows "No accepted deviations."
- [ ] `evo accepted remove . nonexistent:key` -> shows "Not found: nonexistent:key"
- [ ] Accept all changes -> next `evo analyze` shows no significant changes
- [ ] `.evo/accepted.json` persists across multiple `evo analyze` runs

---

## 13. Supporting Materials Checklist

### Week 1 (Before Launch)
- [ ] Terminal demo recording (asciinema, no face/voice, alias watermark)
- [ ] README hero section with demo embed and quick-start
- [ ] Beta application form (Tally) with 4 fields
- [ ] Blog post #1 draft: "What 43 Open-Source Repos Taught Me About CI Failure Patterns"

### Week 2 (Before Reddit)
- [ ] **r/devops post draft:** Lead with CI+dependency correlation insight, include demo link
- [ ] **r/programming post draft:** Technical methodology, cross-signal analysis concept
- [ ] **r/selfhosted post draft:** Local-first angle, privacy comparison with cloud tools
- [ ] **r/Python post draft:** 5-phase pipeline architecture, Cython optimization story

### Week 2-3 (Before DE/ES Push)
- [ ] German LinkedIn post draft (privacy/data sovereignty angle)
- [ ] German Mastodon post draft (fosstodon, open-source/local-first)
- [ ] Spanish Twitter thread draft (cross-signal methodology, LatAm dev community)
- [ ] Translation validation complete (native speakers reviewed DE/ES website pages)

### Week 5 (Before Show HN)
- [ ] Show HN post draft + prepared first comment (technical details, methodology)
- [ ] FAQ page on codequal.dev (anticipate common questions from HN)
- [ ] Comparison pages live (vs Snyk, vs Datadog, vs SonarQube)

### Social Media Templates

**English Twitter thread (template):**
```
1/ I analyzed 43 open-source repos and found that CI failures correlate with
   file dispersion in commits — not just test coverage.

2/ When a commit touches files across 5+ directories, CI failure rate jumps
   3x compared to focused commits. Here's what the data shows...

3/ I built a CLI that detects these patterns automatically.
   It runs locally — your code never leaves your machine.
   [link to repo]
```

**German Mastodon post (template):**
```
Ich habe ein CLI-Tool entwickelt, das Git-, CI- und Dependency-Signale
korreliert, um Muster in der Codebase-Entwicklung zu erkennen.

Alles laeuft lokal — kein Code verlaesst euren Rechner.

Open Source, 5-Phasen-Pipeline, Python + Cython.
[link to /de/ page]

#OpenSource #DevOps #LocalFirst #Python
```

**Spanish Twitter post (template):**
```
Construi un CLI que correlaciona senales de git, CI y dependencias
para detectar patrones de evolucion en tu codebase.

Todo corre local — tu codigo nunca sale de tu maquina.

Open source, pipeline de 5 fases, Python + Cython.
[link to /es/ page]

#OpenSource #DevOps #Python
```

---

> **Bottom line:** The product is feature-complete (586 tests). The remaining blockers are:
>
> 1. **Lawyer review** (in progress) — sign-off on ToS + Privacy, then corrected docs to translator
> 2. **GitLab manual testing** — 7-scenario walkthrough (code verified, needs hands-on run)
> 3. **Stripe E2E testing** — full matrix including FOUNDING50 beta discount coupon
> 4. **User review flow** — end-to-end: analyze → accept → investigate → fix → verify
> 5. **PyPI publication** — `python -m build && twine upload dist/*`
>
> Once testing is complete (estimated: 2-3 days after lawyer sign-off), beta recruiting
> begins with Reddit posts (r/devops first), followed by DE/ES social media outreach and
> a Show HN launch in week 5. All activity under a consistent alias — no identity exposure.
