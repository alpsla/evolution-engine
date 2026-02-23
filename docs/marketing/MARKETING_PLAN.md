# Evolution Engine Beta Launch — Marketing Execution Plan

**Launch window:** Week of February 24, 2026
**Target:** 50 founding members within 6 weeks
**Status:** Pre-launch

---

## 1. Unified Message

**Core narrative (use everywhere as the foundation):**

> AI coding tools write correct code that silently breaks your architecture. Evolution Engine detects the drift, shows you the exact commit, and lets your AI fix it — with evidence.

### Message Variations

**One-liner (bios, headers):**
> Drift detection for AI-assisted development. Local-first CLI. Calibrated on 90+ repos.

**Elevator pitch (Reddit intros, LinkedIn):**
> AI coding tools like Cursor and Copilot produce code that passes tests but silently degrades architecture — coupling goes up, cohesion drops, CI slows down. Evolution Engine watches your SDLC signals (git, CI, deps, deployments) and flags the exact commit where drift began. Then it lets your AI fix it with evidence, not guesswork. Runs locally, code never leaves your machine.

**Technical hook (HN, r/programming):**
> Modified z-score deviation detection across 7 signal families (git, CI, deps, deployments, testing, coverage, error tracking). 6.18M signals calibrated across 90+ repos. No cloud, no telemetry, no code upload. `pip install evolution-engine && evo analyze .` — that's it.

**Privacy hook (Mastodon, r/selfhosted, German audience):**
> Your code never leaves your machine. No account required. No telemetry. Full analysis pipeline runs locally — git history, dependency trees, CI signals. Open-source CLI under BSL 1.1 (converts to MIT in 2029). Built for developers who take data sovereignty seriously.

**Pain-point hook (r/ExperiencedDevs, r/cursor):**
> You asked Cursor to refactor a module. Tests pass. PR looks clean. Two weeks later CI is 40% slower, three packages drifted, and half the team's files are coupled to a new god object. Sound familiar? That's architectural drift, and it's the #1 hidden cost of AI-assisted development.

---

## 2. Alias Setup Guide

The founder operates under an alias to protect current employment. Every step below is mandatory before the first public post.

### 2.1 Choose a Handle

Pick one handle and use it everywhere. Requirements:
- Not connected to your real name or employer
- Available on all target platforms
- Sounds like a developer, not a brand
- Example format: `evocli`, `driftdev`, `signalwatch` — pick one and commit

### 2.2 Create Dedicated Email

- **Provider:** ProtonMail (free tier is fine)
- **Format:** `<handle>@proton.me`
- Use this email for every platform signup below
- Never forward to your work or personal email
- Enable 2FA immediately

### 2.3 Platform Accounts

Create accounts on each platform using the alias handle and ProtonMail address:

| Platform | Handle format | Notes |
|----------|--------------|-------|
| Reddit | u/<handle> | New account, build karma in target subs first |
| Twitter/X | @<handle> | Set to public |
| LinkedIn | Use alias name, DE locale | Professional profile, German market |
| Mastodon | @<handle>@fosstodon.org | Apply for fosstodon.org (FOSS-focused instance) |
| Dev.to | <handle> | Link to GitHub |
| Hacker News | <handle> | Register early, HN accounts need age for Show HN |
| GitHub | Already exists (alpsla) | Use existing account — it's already public |

### 2.4 Avatar

- Use the Evolution Engine project logo, not a face
- Same avatar on every platform for recognition
- If no logo exists yet, use a simple geometric icon or terminal-style glyph

### 2.5 Bio Templates

**Short (Twitter, HN, Reddit):**
> Building Evolution Engine — drift detection for AI-assisted dev. Local-first CLI. I built this.

**Medium (LinkedIn DE, Dev.to):**
> I build developer tools focused on software quality. Currently working on Evolution Engine, a local-first CLI that detects architectural drift caused by AI coding tools. Calibrated on 90+ repos, 6.18M signals. Open source under BSL 1.1.

**Long (Dev.to about page):**
> AI coding tools produce code that compiles, passes tests, and silently degrades your architecture. I built Evolution Engine to detect that drift — it watches git, CI, dependencies, and deployments, flags the exact commit where things shifted, and gives your AI the evidence to fix it. Everything runs locally. Your code never leaves your machine. Calibrated across 90+ repositories and 6.18 million signals.

### 2.6 Operating Rules

1. **Always disclose authorship.** Every post: "I built this" or "Disclosure: I'm the author." No exceptions.
2. **Never fake "we."** Solo founder = "I." Do not imply a team that does not exist.
3. **Never reference your employer.** Not the company name, not the industry ("large media company"), nothing.
4. **No real name anywhere.** Not in commits to public repos, not in blog footers, not in replies.
5. **Separate browser profile.** Use a dedicated Chrome/Firefox profile for all alias activity. Never cross-login.
6. **No cross-posting from personal accounts.** Do not retweet, like, or share from your real identity.
7. **VPN optional but recommended** for account creation and early posting.

---

## 3. Channel Strategy

### 3.1 US Market (English)

#### Reddit

| Subreddit | Audience | Best Angle | Format | Best Time (ET) | Expected Engagement |
|-----------|----------|-----------|--------|----------------|-------------------|
| r/ExperiencedDevs | Senior devs, 5+ years | Pain-point: "AI drift is the new tech debt" | Text post, story format | Tue/Wed 9-11am | 20-50 upvotes, 15-30 comments |
| r/programming | General dev audience | Technical hook with numbers | Link post to blog | Mon/Wed 10am-12pm | 50-200 upvotes if it hits |
| r/devops | CI/CD engineers, SREs | CI signal detection, pipeline slowdown | Text post with terminal output | Tue/Thu 10am-12pm | 10-30 upvotes, 5-15 comments |
| r/cursor | Cursor IDE users | Direct pain: "what Cursor breaks" | Text post, personal experience | Any weekday 10am-2pm | 15-40 upvotes, high comment rate |
| r/ChatGPTCoding | AI-assisted dev users | Before/after: with and without drift detection | Text post with screenshots | Mon-Fri 11am-1pm | 10-25 upvotes |
| r/selfhosted | Privacy-conscious, local-first | No cloud, no telemetry, runs on your box | Text post emphasizing local-first | Sat/Sun 10am-12pm | 20-60 upvotes, strong community |
| r/Python | Python developers | CLI tool showcase, pip install simplicity | Text post or link to blog | Tue/Thu 10am-12pm | 10-30 upvotes |
| r/commandline | CLI enthusiasts | Terminal screenshots, workflow demo | Screenshot + text post | Any day, 10am-2pm | 5-20 upvotes, niche but loyal |

#### Hacker News

- **Target:** Show HN in week 5 (March 24-28)
- **Format:** "Show HN: Evolution Engine — Drift detection for AI-assisted development"
- **Post time:** Tuesday or Wednesday, 8-9am ET
- **Body:** 3-4 paragraphs. Lead with the problem. Link to GitHub. Include `pip install` command.
- **Expected:** 50-150 points if it resonates. HN loves local-first and hates AI hype — lean into the skeptic-friendly angle.

#### Twitter/X

- **Audience:** Dev tool enthusiasts, AI-assisted dev early adopters
- **Angle:** Mix of insights ("here's what 6M signals taught me") and terminal screenshots
- **Format:** Threads (3-5 tweets) for deep content, single tweets for observations
- **Best time:** Tue-Thu, 10am-1pm ET
- **Expected:** Low follower count initially. Focus on replies to relevant threads to build presence.

#### Dev.to

- **Audience:** Developer bloggers, tutorial readers
- **Angle:** In-depth technical posts, cross-posted from blog
- **Format:** Long-form articles, 1000-2000 words
- **Best time:** Tuesday or Wednesday morning
- **Expected:** 50-200 views per post, 5-20 reactions

### 3.2 EU Market (German)

#### LinkedIn (DE)

- **Audience:** German engineering managers, team leads, CTOs at Mittelstand and enterprise
- **Angle:** Data sovereignty, GDPR compliance, local-first architecture. "Your code never leaves Germany."
- **Format:** Professional posts in German, 150-300 words. No hashtag spam.
- **Best time:** Tuesday-Thursday, 8-10am CET
- **Expected:** 500-2000 impressions, 5-15 reactions. LinkedIn DE is underserved for dev tools.

#### Mastodon (fosstodon.org)

- **Audience:** FOSS enthusiasts, privacy advocates, European developers
- **Angle:** Open-source, local-first, no telemetry, BSL 1.1 license story
- **Format:** Short posts (500 chars), link to blog or GitHub. Use hashtags: #FOSS #DevTools #CLI #LocalFirst
- **Best time:** Weekdays 9-11am CET
- **Expected:** 5-20 boosts, slow but compounding. Mastodon audience is loyal once engaged.

#### r/de_EDV

- **Audience:** German IT professionals
- **Angle:** German-language post, privacy/data sovereignty, practical CLI tool
- **Format:** Text post in German, link to GitHub
- **Best time:** Weekday evenings CET
- **Expected:** 5-15 upvotes, niche but targeted

### 3.3 Canada + LatAm (Spanish)

#### Twitter/X (ES)

- **Audience:** Spanish-speaking developers in Latin America and Spain
- **Angle:** Accessibility, free tier, local-first (important in regions with connectivity concerns)
- **Format:** Spanish-language thread, 3-5 tweets
- **Best time:** Tue-Thu, 11am-1pm EST (overlaps with Mexico, Colombia, Argentina)
- **Expected:** Small but underserved audience. High engagement if content resonates.

#### r/programacion

- **Audience:** Spanish-speaking programmers
- **Angle:** Free CLI tool, pip install simplicity, AI drift detection
- **Format:** Text post in Spanish
- **Best time:** Weekday afternoons EST
- **Expected:** 5-15 upvotes. Small sub but almost zero competition for dev tool posts.

#### Dev.to (ES)

- **Audience:** Spanish-speaking dev bloggers
- **Angle:** Translated versions of English blog posts
- **Format:** Long-form in Spanish, tagged with #spanish
- **Best time:** Tuesday or Wednesday
- **Expected:** 20-50 views per post

---

## 4. Founding Member Offer

### 4.1 Structure

- **50 spots** — hard cap, displayed as countdown on beta form
- **Price:** $9.50/month for 3 months (50% off the $19/month Pro tier)
- **Code:** `FOUNDING50`
- **Duration:** 3 months at founding rate, then auto-converts to standard $19/month (cancel anytime)
- **In exchange for:** Monthly 5-question survey (email, 2 minutes) + permission to quote anonymized feedback

### 4.2 Framing

Frame as exclusive early access, not a discount:

> "We're opening 50 founding member spots for developers who want to shape the tool. You get full Pro access at half price for 3 months. In exchange, I'll send you a 5-question survey each month and may quote your anonymized feedback. Once the 50 spots fill, this offer is gone."

Do NOT say: "50% discount", "sale", "deal", "cheap."
DO say: "founding member", "early access", "shape the roadmap", "exclusive."

### 4.3 Beta Application Form

**Hosted on:** Simple form (Tally.so or similar, free tier)

**Fields:**
1. GitHub username (text, required)
2. Primary repository URL — the repo you'd analyze first (URL, required)
3. Which AI coding tools do you use? (multi-select: Cursor, GitHub Copilot, Claude Code/Claude, ChatGPT, Cody, Codex, Other)
4. Current monitoring/quality tools (multi-select: SonarQube, Snyk, Datadog, Sentry, CodeClimate, None, Other)
5. How did you hear about Evolution Engine? (dropdown: Reddit, HN, Twitter, LinkedIn, Mastodon, Dev.to, Word of mouth, Other)
6. Email address (email, required — for founding member code delivery)

### 4.4 Offer Copy (for posts)

> **Founding Member Access — 50 Spots**
>
> I'm looking for 50 developers to be the first Pro users of Evolution Engine. You get full access to the AI investigation loop, CI integration (GitHub Actions + GitLab CI), and the fix-verify cycle — at $9.50/month for your first 3 months.
>
> What I ask in return: a short monthly survey (5 questions, 2 minutes) and permission to use your anonymized feedback to improve the product.
>
> Apply here: [beta form link]
>
> Disclosure: I built this.

---

## 5. Free Tier Strategy

### 5.1 What Free Includes

The free tier is genuinely powerful — this is not a crippled demo:

- Full CLI pipeline: `evo analyze .` runs Phases 1-5 locally
- Git signal analysis (files touched, dispersion, change locality, co-change novelty)
- Dependency analysis (npm, pnpm, Go, Cargo, Bundler, pip, Composer, Gradle, Maven, Swift, CMake)
- Pattern matching against calibrated universal patterns (44 patterns from 58 repos)
- Standalone HTML reports with risk badges and evidence
- Git hooks for continuous monitoring (`evo hooks install`)
- Full prescan and source detection (`evo sources`)
- Historical trend detection and verification (`evo analyze . --verify`)
- Community pattern sharing (opt-in)

### 5.2 What Free Does NOT Include

- No GitHub Action / GitLab CI integration
- No webhook-based notifications
- No AI investigation loop (`evo investigate`)
- No AI fix loop (`evo fix`)
- No inline PR/MR review comments

### 5.3 Why This Works

- **Zero friction entry:** `pip install evolution-engine && evo analyze .` — no signup, no account, no API key needed
- **No data leaves the machine** — eliminates the biggest objection
- **The report sells the upgrade** — when users see "3 advisories detected, architectural drift in 2 modules," they want the AI investigation
- **Hooks create habit** — daily drift notifications make EE part of the workflow before they ever pay

### 5.4 Free Tier CTA (use in all posts)

> Try it now — no signup, no cloud, no API key:
> ```
> pip install evolution-engine
> evo analyze .
> ```
> Your code never leaves your machine.

---

## 6. Posting Frequency and Rules

### 6.1 Frequency Limits

| Channel | Frequency | Constraint |
|---------|-----------|-----------|
| Reddit (per sub) | Max 1 post per subreddit per week | Never post to multiple subs on the same day |
| Twitter/X | 2-3 posts per week | Mix insights and screenshots, not all promotional |
| LinkedIn DE | 1 post per week | Professional tone, German language |
| Mastodon | 1-2 posts per week | Short, hashtag-rich, link to content |
| Dev.to | 1 blog post every 2 weeks | Long-form, cross-posted from primary blog |

### 6.2 Engagement Rules

1. **Reply to every comment within 4 hours** on Reddit. Within 12 hours on all other platforms.
2. **Always disclose authorship.** First post in any thread: "Disclosure: I built this."
3. **Lead with insight, not promotion.** Every post must contain a genuine observation, finding, or story. The product is secondary.
4. **Never be defensive.** If someone criticizes the tool, thank them and ask for specifics.
5. **Upvote and engage with competitors fairly.** Do not trash other tools.
6. **No astroturfing.** Never create fake accounts to upvote or comment.
7. **No cross-posting identical content.** Each subreddit gets a unique post tailored to its audience.

### 6.3 Stagger Schedule (Example Week)

| Day | Channel | Action |
|-----|---------|--------|
| Monday | Reddit (sub A) | New post |
| Tuesday | Twitter/X | Thread or insight |
| Wednesday | Reddit (sub B) | New post |
| Thursday | LinkedIn DE | Professional post |
| Friday | Twitter/X | Screenshot or reply roundup |
| Saturday | Mastodon | FOSS-focused post |
| Sunday | Rest | Reply to any outstanding comments |

---

## 7. Content Calendar (Weeks 1-8)

### Week 1: February 24-28 — Soft Launch

- **Mon:** Beta application form goes live
- **Tue:** Reddit post on r/ExperiencedDevs — pain-point format ("AI drift is the new tech debt")
- **Wed:** Reddit post on r/programming — link to blog post #1
- **Thu:** Blog post #1 published on Dev.to: "I Analyzed 90+ Repos and 6 Million Signals"
- **Fri:** Twitter/X — first thread summarizing blog post findings

### Week 2: March 3-7 — AI Tool Communities

- **Mon:** Reddit post on r/devops — CI signal detection angle
- **Tue:** Twitter/X — terminal screenshot showing drift detection
- **Wed:** Reddit post on r/cursor — direct pain-point for Cursor users
- **Thu:** Reddit post on r/ChatGPTCoding — AI drift pattern
- **Fri:** Reply to all comments, engage in discussions

### Week 3: March 10-14 — German Market Push

- **Mon:** LinkedIn DE — first professional post (German, data sovereignty angle)
- **Tue:** Mastodon (fosstodon.org) — FOSS/local-first angle
- **Wed:** Reddit post on r/de_EDV — German-language post
- **Thu:** Blog post #2 published: "Your AI Writes Correct Code That Breaks Your Architecture"
- **Fri:** Twitter/X — insight from week's engagement

### Week 4: March 17-21 — Spanish Market + Expand

- **Mon:** Twitter/X — Spanish-language thread
- **Tue:** Reddit post on r/selfhosted — local-first, no cloud angle
- **Wed:** Reddit post on r/Python — CLI tool showcase
- **Thu:** r/programacion — Spanish-language post
- **Fri:** Dev.to — Spanish cross-post of blog #1

### Week 5: March 24-28 — Show HN (Main Event)

- **Mon:** Final prep: ensure GitHub README is polished, demo GIF works, QUICKSTART is current
- **Tue:** **Show HN post** — 8-9am ET. All hands on deck for comments.
- **Wed:** Continue engaging with HN comments (expect 50-200 comments if it hits front page)
- **Thu:** Blog post #3: "The Fix Loop: How to Let AI Break Things and Then Fix Them"
- **Fri:** Twitter/X — recap HN reception, share highlights

### Week 6: March 31 - April 4 — Sustain

- **Mon:** Reddit post on r/commandline — CLI workflow showcase
- **Tue:** Twitter/X — user testimonial (if available from founding members)
- **Wed:** LinkedIn DE — second post, reference any German interest
- **Thu:** Mastodon — update on reception and progress
- **Fri:** Review metrics, adjust strategy

### Week 7: April 7-11 — Iterate

- **Mon:** Blog post #4: "Local-First in 2026: Why Your Code Should Never Leave Your Machine"
- **Tue:** Reddit — revisit highest-engagement subreddit with follow-up post
- **Wed:** Twitter/X — share founding member feedback (anonymized)
- **Thu:** Dev.to — cross-post blog #4
- **Fri:** Assess founding member count, adjust offer if needed

### Week 8: April 14-18 — Consolidate

- **Mon-Fri:** Focus on engagement over new posts. Reply to outstanding threads. Build relationships with active commenters. Identify potential champions.
- **Thu:** Internal review: founding member count, feedback themes, next quarter plan

---

## 8. Blog Post Topics

All posts reframed for the AI drift angle. Each post must include a working `pip install` CTA.

### Post #1: "I Analyzed 90+ Repos and 6 Million Signals — Here's What AI Coding Tools Get Wrong"
- **Angle:** Data-driven, research-flavored. Lead with numbers.
- **Content:** Show real patterns from calibration. CI slowdown after AI-generated PRs. Dependency sprawl. Dispersion increase. Name specific patterns (ci+dispersion, deploy+dispersion).
- **CTA:** "Run it on your repo: `pip install evolution-engine && evo analyze .`"
- **Target:** r/programming, HN, Dev.to

### Post #2: "Your AI Writes Correct Code That Breaks Your Architecture — Here's the Pattern"
- **Angle:** Story format. Walk through a realistic scenario of AI-caused drift.
- **Content:** Cursor refactors a module. Tests pass. Two weeks later: god object, coupling explosion, CI regression. Show the exact detection flow.
- **CTA:** Link to founding member form.
- **Target:** r/ExperiencedDevs, r/cursor, LinkedIn DE

### Post #3: "The Fix Loop: How to Let AI Break Things and Then Fix Them (With Evidence)"
- **Angle:** Practical workflow. "Here's how to use AI tools safely."
- **Content:** Demonstrate the evo analyze → evo investigate → evo fix → evo analyze --verify loop. Show before/after.
- **CTA:** "The investigation loop requires Pro. Founding member spots still open."
- **Target:** r/ChatGPTCoding, r/devops, Twitter/X

### Post #4: "Local-First in 2026: Why Your Code Should Never Leave Your Machine"
- **Angle:** Privacy and data sovereignty. Especially relevant for EU audience.
- **Content:** Compare EE's approach (everything local) to cloud-based code analysis tools. Address GDPR. Address enterprise security concerns.
- **CTA:** "No account, no signup, no data upload: `pip install evolution-engine`"
- **Target:** Mastodon, r/selfhosted, LinkedIn DE, r/de_EDV

---

## 9. Identity and Employment Considerations

The founder currently works at a large company. The following sequence minimizes risk.

### 9.1 Phase 1: Alias Launch (Weeks 1-4)

- All public activity under the alias handle
- No real name, no employer reference, no industry hints
- GitHub account (alpsla) is already public — this is acceptable as long as it doesn't link to the employer
- The beta program, founding member offer, and all marketing operate under the alias
- No legal entity disclosure needed at this stage (CodeQual LLC is registered but doesn't need to be front-and-center)

### 9.2 Phase 2: Legal Review (Weeks 3-5)

- **Read employment contract carefully.** Look for:
  - IP assignment clauses (especially "all inventions" language)
  - Moonlighting restrictions
  - Non-compete clauses (scope, duration, geography)
  - Non-solicitation clauses
  - Use of company equipment/time restrictions
- **Consult an employment lawyer.** Budget $200-400 for a 1-hour consultation.
  - Bring: employment contract, summary of EE project, timeline of development (all done on personal time/equipment)
  - Ask: "Can I launch this commercially while employed? What disclosures are required?"
- **Document everything:** Personal laptop, personal time, no company resources used. Keep receipts.

### 9.3 Phase 3: Identity Decision (Weeks 5-8)

- If legal review is clear: consider telling your manager before going public. Turns a risk into an asset ("I build developer tools on the side").
- If legal review shows risk: continue under alias indefinitely. Many successful tools launched this way.
- The LinkedIn career play (real name, real profile) can wait 4-8 weeks until traction proves the product is worth the risk.

### 9.4 Phase 4: Public Reveal (Month 2-3, if safe)

- Sequence: alias launch, legal review, identity decision, then public reveal
- Public reveal includes: real name on GitHub, LinkedIn post announcing the project, connecting alias to real identity
- Only do this after legal confirmation and (ideally) manager conversation

---

## 10. Success Metrics

### Week 2 (by March 7)

| Metric | Target |
|--------|--------|
| Beta applications | 10+ |
| GitHub stars | 30+ |
| Blog post #1 views | 500+ |
| Reddit total upvotes | 50+ |

### Week 4 (by March 21)

| Metric | Target |
|--------|--------|
| Beta applications | 30+ |
| Active testers (ran evo analyze) | 10+ |
| GitHub stars | 80+ |
| Twitter/X followers | 50+ |
| Email list | 40+ |

### Week 6 (by April 4)

| Metric | Target |
|--------|--------|
| Founding members (paid) | 50 (cap filled) |
| GitHub stars | 200+ |
| Active free tier users | 100+ |
| Blog total views | 3000+ |
| Show HN score | 50+ points |

### Month 3 (by May 24)

| Metric | Target |
|--------|--------|
| Pro subscribers | 30-50 |
| MRR | $570-$950 |
| GitHub stars | 500+ |
| NPS (from founding member surveys) | 40+ |
| Community patterns submitted | 20+ |

### Tracking Tools

- **GitHub:** Stars, forks, clones (GitHub Insights, free)
- **Reddit:** Post karma, comment count (manual tracking)
- **Twitter/X:** Followers, impressions (Twitter Analytics, free)
- **Beta form:** Tally.so analytics (free tier)
- **Revenue:** Stripe dashboard
- **CLI usage:** No telemetry by design. Measure by PyPI download count (`pip install` stats via pypistats.org).

---

## Appendix: Quick Reference

### Key URLs (to be filled in before launch)

- GitHub: https://github.com/alpsla/evolution-engine
- PyPI: https://pypi.org/project/evolution-engine/
- Beta form: [TBD]
- Website: https://codequal.dev
- Stripe checkout: [TBD]

### Key Commands for Posts

```bash
# Install
pip install evolution-engine

# Analyze a repo
evo analyze .

# See what sources are detected
evo sources

# Verify previous findings
evo analyze . --verify

# Install git hooks for continuous monitoring
evo hooks install

# Generate HTML report
evo analyze . --report
```

### Pricing Summary

| Tier | Price | Includes |
|------|-------|----------|
| Free | $0 | Full CLI pipeline, git + deps + patterns, HTML reports, hooks |
| Pro | $19/month | + AI investigation, AI fix loop, CI integration, inline PR comments |
| Founding | $9.50/month (3 mo) | Same as Pro, code `FOUNDING50`, 50 spots |
