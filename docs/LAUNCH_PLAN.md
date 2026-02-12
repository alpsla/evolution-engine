# Evolution Engine — Launch Plan

> **Actionable roadmap for solo-founder beta launch.**
>
> Compiled from research on: solo founder positioning, EU AI Act compliance,
> Stripe beta discounts, and existing documentation audit.
>
> **Created:** February 11, 2026

---

## 1. Pre-Launch Blockers (This Week)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | PyPI publication | **BLOCKER** | `python -m build && twine upload dist/*` — test on TestPyPI first |
| 2 | Stripe e2e test | **BLOCKER** | Sandbox purchase → webhook → license key → CLI activation |
| 3 | Lawyer review | **BLOCKER** | ToS + Privacy drafts in `legals/` — need sign-off before accepting payments |
| 4 | Translation review | Pending | DE/ES translations need native speaker validation |
| 5 | Language switcher deploy | ✅ Done | Pushed 2026-02-11 (absolute paths + Vercel routes) |
| 6 | Report improvements | ✅ Done | Severity badges, risk banners, grouped cards, IP sanitization |

---

## 2. Stripe Beta Discount Setup

**Approach: 50% coupon for 3 months (auto-expires)**

### Steps:
1. **Dashboard → Products → Coupons → New**
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
       allow_promotion_codes=True,  # ← only change needed
       success_url="...",
       cancel_url="...",
   )
   ```

4. **Webhook** — existing handler covers it. Optionally add `customer.discount.deleted` to notify when coupon expires.

**Pricing psychology:** Call it "founding member pricing," not a discount. "$9.50/month for founding members. Regular price: $19/month."

**Transition:** Automatic. Stripe bills full price on month 4. Send email at week 11: "Your founding member rate expires in 2 weeks. Thank you for being an early tester."

**Fallback:** If churn >40% at transition, offer $14/month "permanent founding member" rescue price.

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
- Source: warm outreach to open-source maintainers

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

### Tier 1: Warm Outreach (First 10)

Find open-source maintainers of 100-5,000 star projects with dependency PR backlogs:

```
Criteria:
- Has .github/dependabot.yml or renovate.json
- 20+ open dependency PRs
- Maintainer committed in last 30 days
```

**Outreach template:**
> "Hi [name], I noticed [repo] has [N] open dependency PRs. I built a CLI that
> correlates dependency changes with CI failures and code churn to flag which
> updates actually matter. It runs locally — your code never leaves your machine.
> I'm looking for 10 beta testers and offering founding member pricing (50% off
> for 3 months). Happy to jump on a 10-minute call to see if it's relevant."

### Tier 2: Community Posts (Next 20-40)

| Platform | Angle | Timing |
|----------|-------|--------|
| **HN Show HN** | "I built a CLI that finds patterns across git, CI, and deployment data" | Tuesday-Thursday, 9-11am ET |
| **r/devops** | Problem-focused: dependency + CI correlation | 3 days after HN |
| **r/programming** | Technical deep-dive | 5 days after HN |
| **r/selfhosted** | "Local-first, code never leaves your machine" | 7 days after HN |
| **r/Python** | Implementation: 5-phase pipeline with Cython | Separate week |
| **Dev.to** | Blog post cross-post (canonical to codequal.dev) | Week +2 |
| **Twitter/X + Bluesky** | Build-in-public thread with terminal screenshots | Ongoing |
| **Mastodon** (fosstodon) | Local-first + privacy angle | Ongoing |

**Space Reddit posts 3-5 days apart.** Each community gets a unique angle.

### Tier 3: Leveraged (If Needed)
- DevOpsDays / local meetup lightning talks (5 min)
- Small DevOps podcast guest spots (<5K listeners)
- platformengineering.org Slack, DevOps Chat, Hangops

---

## 5. Solo Founder Positioning

### Do
- **Embrace "indie dev" identity** — developers trust solo founders over VC-funded startups
- Use first person ("I built this because..."), never fake "we"
- Real name and photo on the about page
- Pin the repo on GitHub, keep contribution graph active
- Respond to GitHub issues within hours (your #1 competitive advantage)
- Record a 90-second `asciinema`/`vhs` terminal recording for the README
- Write technically deep blog posts that teach something even without the tool

### Don't
- Don't buy ads yet (organic first, no ROI at this scale)
- Don't create empty Discord/Slack communities
- Don't hire a content writer (devs detect non-technical marketing instantly)
- Don't launch on all channels simultaneously (stagger by 2-3 days)
- Don't position against tools — position as the aggregation layer ("We see what Datadog can't because we analyze development, not production")

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
- Privacy policy ✅ (website/privacy.html)
- Telemetry is opt-in ✅
- Code stays local ✅
- Stripe handles payment data ✅

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
- [ ] Stripe sandbox e2e test
- [ ] Lawyer review of ToS + Privacy
- [ ] Translation validation (DE/ES)

### Week 1 (Feb 17-21) — Technical Readiness
- [ ] PyPI TestPyPI upload + test install on clean machine
- [ ] PyPI production upload
- [ ] Add `allow_promotion_codes=True` to checkout handler
- [ ] Create Stripe coupon (FOUNDING50, 50% off, 3 months, max 50)
- [ ] Add AI transparency disclosure to CLI (`evo investigate`, `evo fix`)
- [ ] Record terminal demo (asciinema/vhs, 90 seconds)

### Week 2 (Feb 24-28) — Private Alpha
- [ ] Identify 30 target repos for warm outreach
- [ ] Send 30 personalized messages to maintainers
- [ ] Create beta application form (Tally/Google Form)
- [ ] Write blog post #1 ("What 43 Repos Taught Me")
- [ ] Goal: 10 accepted alpha testers

### Week 3-4 (Mar 3-14) — Alpha Support
- [ ] High-touch alpha support (DM each user, offer calls)
- [ ] Fix critical bugs from alpha feedback
- [ ] Write blog post #2 ("Why Dependency Updates Break Code")
- [ ] Draft Show HN post + first comment
- [ ] Prepare Reddit posts (different angles per subreddit)

### Week 5 (Mar 17-21) — Public Beta Launch
- [ ] **Monday: Show HN** (the main event)
  - Monitor comments for 12 hours, reply within 30 min
  - Post on Twitter/X linking to HN discussion
- [ ] **Wednesday: r/devops** (problem-focused)
- [ ] **Thursday: r/programming** (technical deep-dive)
- [ ] **Friday: r/selfhosted** (local-first angle)
- [ ] Goal: expand to 30-50 beta testers

### Week 6-7 (Mar 24 - Apr 4) — Product Hunt + Momentum
- [ ] Launch on Product Hunt (2-3 weeks after HN)
- [ ] Ask beta users for genuine reviews
- [ ] Write comparison pages (vs Snyk, vs Datadog)
- [ ] Post to r/commandline, r/Python
- [ ] Cross-post to Mastodon/Bluesky

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
| HN post doesn't get traction | Reddit + Dev.to as backup channels. Stagger, don't batch. |
| High FP rate on user repos | 1.6% validated. Accept GitHub issues, fix within 24h. |
| Stripe payment failures | Test sandbox thoroughly. 30-day money-back guarantee in ToS. |
| Big company copies the approach | Moat = accumulated patterns + Cython engines + community data. Keep shipping. |
| EU AI Act enforcement | Minimal risk classification. Add transparency disclosure by Aug 2026. |
| Solo founder burnout | Limit support to GitHub Issues + email. No Discord until 100+ users. |

---

> **Bottom line:** The product is ready. The two hard blockers are PyPI publication and Stripe
> testing. Once those are done (estimated: 1-2 days), beta recruiting can begin immediately
> with warm outreach to open-source maintainers, followed by a Show HN launch in week 5.
