# Terms of Service — Evolution Engine (codequal.dev)

**Effective Date:** 2026-02-20
**Last Updated:** 2026-02-20

---

## 1. Acceptance of Terms

By downloading, installing, accessing, or using Evolution Engine, the codequal.dev website, or any related services (collectively, the "Service"), you agree to be bound by these Terms of Service ("Terms"). If you are using the Service on behalf of an organization, you represent and warrant that you have the authority to bind that organization to these Terms.

If you do not agree to these Terms, do not use the Service.

These Terms constitute a legally binding agreement between you ("you," "your," or "User") and CodeQual ("we," "us," "our," or "Company").

---

## 2. Description of Service

Evolution Engine is a local-first command-line interface (CLI) tool for software development analytics. The Service analyzes development signals across version control, continuous integration, deployment, dependency management, and security data sources to identify patterns and generate actionable advisories.

### 2.1 Local-First Architecture
The core analysis pipeline (Phases 1 through 5) runs entirely on your local machine. **Your source code never leaves your computer.** All pipeline output (events, signals, patterns, advisories, and reports) is stored in local directories on your machine.

### 2.2 Optional Cloud Features
Certain features involve data transmission to external services, but only when you explicitly initiate them:
- **CLI telemetry** (opt-in, anonymous usage statistics)
- **Knowledge Base sync** (opt-in, anonymized pattern sharing)
- **AI investigation and fix** (requires your own API key and explicit command invocation)
- **GitHub Action integration** (posts summaries to your own GitHub PRs)

### 2.3 Website and API
The codequal.dev website provides documentation, subscription management via Stripe, license key retrieval, and an adapter request form.

---

## 3. Account and Subscription Terms

### 3.1 Free Tier
Evolution Engine is available at no cost under the Free tier. The Free tier includes access to the core analysis pipeline (Phases 1 through 5), local pattern detection, report generation, and GitHub Action integration. Certain advanced features may be restricted to the Pro tier.

### 3.2 Pro Tier
The Pro tier is available for **$19 per month** (USD), billed monthly via Stripe. The Pro tier includes access to additional capabilities, including certain AI-powered features, as further described on our website at [https://codequal.dev/#pricing](https://codequal.dev/#pricing).

### 3.3 Payment Processing
All payments are processed by Stripe, Inc. By purchasing a Pro subscription, you agree to Stripe's terms of service. You are responsible for providing accurate and complete payment information. We do not store your payment card details; all payment data is handled directly by Stripe.

### 3.4 Pricing Changes
We reserve the right to change subscription pricing. If we change the price of the Pro tier, we will provide at least 30 days' notice before the new price takes effect. The new price will apply at the start of your next billing cycle after the notice period.

### 3.5 Taxes
Subscription fees are exclusive of taxes unless stated otherwise. You are responsible for any applicable sales tax, VAT, GST, or other taxes imposed by your jurisdiction. Stripe may collect applicable taxes on our behalf.

---

## 4. License Grant

### 4.1 Dual Licensing Structure
Evolution Engine is distributed under a dual-license model:

(a) **MIT License:** The command-line interface wrapper, adapter framework, and plugin interfaces are licensed under the MIT License. The source code for these components is publicly available on GitHub.

(b) **Business Source License 1.1:** The core analysis engine (Phases 2-5) and associated compiled binaries are licensed under the Business Source License 1.1. This license permits non-production use without a commercial license. Production use requires an active Pro subscription.

### 4.2 Pro Tier License
Upon purchasing a Pro subscription, you receive a commercial license to use the core analysis engine in production environments for the duration of your subscription.

### 4.4 Open Source Components
Evolution Engine includes open source software components, which are licensed under their respective open source licenses. Your use of open source components is governed by those licenses, not these Terms.

---

## 5. Restrictions

You agree not to:

### 5.1 Reverse Engineering
- Reverse engineer, decompile, or disassemble any compiled components of the Service, including but not limited to Cython-compiled modules (`.so`, `.pyd`, `.dylib` files), except to the extent expressly permitted by the Business Source License 1.1 or applicable law notwithstanding this restriction
- Circumvent, disable, or interfere with any license verification, authentication, or security mechanisms

### 5.2 License Key Restrictions
- Share, distribute, publish, or transfer your license key to any third party
- Use a single license key on more machines or for more users than permitted by your subscription tier
- Attempt to generate, forge, or tamper with license keys
- Use someone else's license key without their authorization

### 5.3 Commercial Restrictions
- Resell, sublicense, lease, or rent the Service or access to it
- Use the Service to provide a competing product or service to third parties
- Remove, alter, or obscure any proprietary notices, labels, or marks on the Service

### 5.4 Abuse
- Use the Service in any manner that could damage, disable, overburden, or impair our infrastructure
- Attempt to gain unauthorized access to any part of the Service, other accounts, or systems
- Use the Service to violate any applicable law or regulation
- Transmit any malicious code, viruses, or harmful content through the Service
- Manipulate or submit false or misleading data through the adapter request form or any other Service feature

---

## 6. Intellectual Property

### 6.1 Our Intellectual Property
The Service, including its software, algorithms, compiled binaries, documentation, website, branding, and all related intellectual property, is owned by CodeQual and is protected by copyright, trade secret, and other intellectual property laws. These Terms do not grant you any right, title, or interest in our intellectual property except for the limited license described in Section 4.

### 6.2 Your Data
You retain all rights to your data. We do not claim any ownership of your source code, repositories, configuration files, or any data processed by the Service on your local machine. Output generated by the Service (reports, advisories, patterns) from your data belongs to you.

### 6.3 Community Patterns
If you opt in to Knowledge Base sync (privacy level 1 or 2), the anonymized patterns you contribute to the community registry are dedicated to the public domain under the Creative Commons Zero (CC0-1.0) Universal Public Domain Dedication. You acknowledge that contributed patterns cannot be recalled once shared, though you may stop contributing at any time.

### 6.4 Feedback
If you provide feedback, suggestions, or ideas about the Service, you grant us a non-exclusive, worldwide, royalty-free, irrevocable license to use, reproduce, modify, and incorporate that feedback into the Service without obligation to you.

---

## 7. Third-Party Integrations

### 7.1 Adapter Integrations
Evolution Engine integrates with third-party development tools and services through adapters (e.g., GitHub, Jenkins, GitLab, npm, Cargo). These integrations access data from third-party services using credentials and tokens that you provide.

### 7.2 No Endorsement
The availability of third-party integrations does not constitute an endorsement of, affiliation with, or recommendation for any third-party service. We are not responsible for the availability, accuracy, or reliability of third-party services.

### 7.3 Third-Party Terms
Your use of third-party services through Evolution Engine adapters is subject to the terms of service, privacy policies, and usage limits of those third-party services. You are responsible for complying with all applicable third-party terms, including API rate limits and acceptable use policies.

### 7.4 AI Service Providers
If you use the AI investigation or fix features, your data is sent to the AI provider you have configured (e.g., Anthropic). Your use of these AI services is subject to the AI provider's terms of service and privacy policy. We are not responsible for how AI providers process your data.

### 7.5 Stripe
Payment processing is provided by Stripe, Inc. Your use of Stripe's services is subject to Stripe's terms of service.

---

## 8. Disclaimer of Warranties

**THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, WHETHER EXPRESS, IMPLIED, STATUTORY, OR OTHERWISE.**

To the fullest extent permitted by applicable law, we disclaim all warranties, including but not limited to:

- **Implied warranties** of merchantability, fitness for a particular purpose, and non-infringement
- **Warranties regarding accuracy** -- the advisories, patterns, risk assessments, and recommendations generated by the Service are provided for informational purposes only and should not be relied upon as the sole basis for any decision
- **Warranties regarding AI output** -- AI-generated investigation results and fix suggestions may contain errors, inaccuracies, or inappropriate recommendations. You are responsible for reviewing and validating all AI-generated output before taking action
- **Warranties regarding availability** -- we do not guarantee that the Service (including cloud features, the website, or API endpoints) will be available, uninterrupted, secure, or error-free
- **Warranties regarding third-party services** -- we do not warrant the performance, availability, or accuracy of any third-party service accessed through the Service

You acknowledge that software development decisions involve professional judgment and that the Service is a tool to assist, not replace, such judgment.

---

## 9. Limitation of Liability

### 9.1 Exclusion of Consequential Damages
TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL CODEQUAL, ITS OFFICERS, DIRECTORS, EMPLOYEES, AGENTS, OR AFFILIATES BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY, OR PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO:

- Loss of profits, revenue, data, or business opportunities
- Cost of procurement of substitute goods or services
- Interruption of business
- Damages arising from reliance on advisories, patterns, or recommendations generated by the Service
- Damages arising from AI-generated suggestions or automated fixes applied to your codebase

Whether based on warranty, contract, tort (including negligence), strict liability, or any other legal theory, even if we have been advised of the possibility of such damages.

### 9.2 Cap on Liability
TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, OUR TOTAL AGGREGATE LIABILITY FOR ALL CLAIMS ARISING OUT OF OR RELATED TO THESE TERMS OR THE SERVICE SHALL NOT EXCEED THE GREATER OF: (A) THE AMOUNT YOU HAVE PAID US IN THE TWELVE (12) MONTHS PRECEDING THE CLAIM, OR (B) ONE HUNDRED U.S. DOLLARS ($100.00).

### 9.3 Exceptions
The limitations in this section do not apply to liability arising from: (a) our gross negligence or willful misconduct, (b) death or personal injury caused by our negligence, or (c) any liability that cannot be excluded or limited under applicable law.

---

## 10. Refund Policy

### 10.1 30-Day Money-Back Guarantee
If you are not satisfied with the Pro tier, you may request a full refund within 30 days of your initial subscription purchase. To request a refund, contact us at info@codequal.dev with your Stripe customer email address.

### 10.2 Refund After 30 Days
After the initial 30-day period, subscription fees are non-refundable. You may cancel your subscription at any time (see Section 11), but no partial refund will be issued for the remainder of your current billing period.

### 10.3 Refund Processing
Approved refunds will be processed through Stripe to the original payment method. Please allow 5-10 business days for the refund to appear on your statement.

### 10.4 Exceptions
We reserve the right to deny refund requests in cases of abuse, such as repeated subscription and refund cycles, or violations of these Terms.

---

## 11. Cancellation

### 11.1 How to Cancel
You may cancel your Pro subscription at any time by:
- Contacting us at info@codequal.dev
- Managing your subscription through the Stripe customer portal (if available)

### 11.2 Effect of Cancellation
Upon cancellation:
- Your Pro subscription will remain active until the end of your current billing period
- You will not be charged for subsequent billing periods
- After the billing period ends, your account will revert to the Free tier
- Your license key will be automatically revoked (cleared from Stripe metadata)
- All locally stored data (reports, patterns, advisories) remains on your machine and is not deleted

### 11.3 Resubscription
If you cancel and later wish to resubscribe, you may purchase a new Pro subscription at the then-current price. A new license key will be generated.

---

## 12. Termination

### 12.1 Termination by Us
We may suspend or terminate your access to the Service at any time, with or without cause, and with or without notice. Grounds for termination include but are not limited to:
- Violation of these Terms
- Fraudulent, abusive, or illegal activity
- Non-payment of subscription fees
- Conduct that harms other users or the integrity of the Service

### 12.2 Termination by You
You may stop using the Service at any time. To fully terminate your relationship with us, cancel any active subscription and delete the Evolution Engine software and all associated local data from your devices.

### 12.3 Effect of Termination
Upon termination:
- Your license to use the Service (beyond the Free tier, or entirely if termination is for cause) is immediately revoked
- You must cease using any Pro tier features
- Sections 5 (Restrictions), 6 (Intellectual Property), 8 (Disclaimer of Warranties), 9 (Limitation of Liability), 13 (Governing Law), and 14 (Dispute Resolution) survive termination

### 12.4 Data After Termination
We do not have access to or control over your locally stored data. Any data stored on our systems (telemetry logs, Stripe records) will be handled in accordance with our Privacy Policy.

---

## 13. Governing Law

These Terms shall be governed by and construed in accordance with the laws of the State of Delaware, United States, without regard to its conflict of law principles.

---

## 14. Dispute Resolution

### 14.1 Informal Resolution
Before initiating any formal dispute resolution process, you agree to first contact us at info@codequal.dev and attempt to resolve the dispute informally for at least 30 days.

### 14.2 Binding Arbitration
If the dispute cannot be resolved informally, you and CodeQual agree to resolve any dispute, claim, or controversy arising out of or relating to these Terms or the Service through binding arbitration administered by the American Arbitration Association (AAA) under its Commercial Arbitration Rules. The arbitration will be conducted remotely via videoconference unless both parties agree otherwise in writing.

### 14.3 Class Action Waiver
YOU AND CODEQUAL AGREE THAT EACH MAY BRING CLAIMS AGAINST THE OTHER ONLY IN YOUR OR ITS INDIVIDUAL CAPACITY, AND NOT AS A PLAINTIFF OR CLASS MEMBER IN ANY PURPORTED CLASS OR REPRESENTATIVE PROCEEDING.

If you are a resident of the European Union or other jurisdiction where arbitration agreements and class action waivers are prohibited by law, this Section 14 (Dispute Resolution) shall not apply to you.

### 14.4 Exceptions to Arbitration
Notwithstanding the above, either party may: (a) bring an action in small claims court if the claim qualifies, or (b) seek injunctive or other equitable relief in a court of competent jurisdiction to prevent the actual or threatened infringement, misappropriation, or violation of intellectual property rights.

### 14.5 Opt-Out
You may opt out of the arbitration and class action waiver provisions by sending written notice to info@codequal.dev within 30 days of first accepting these Terms. If you opt out, disputes will be resolved in the state or federal courts located in Delaware.

---

## 15. General Provisions

### 15.1 Entire Agreement
These Terms, together with the Privacy Policy and any other policies referenced herein, constitute the entire agreement between you and CodeQual regarding the Service and supersede all prior agreements and understandings.

### 15.2 Severability
If any provision of these Terms is found to be unenforceable or invalid, that provision will be limited or eliminated to the minimum extent necessary, and the remaining provisions will continue in full force and effect.

### 15.3 Waiver
Our failure to enforce any right or provision of these Terms will not be considered a waiver of that right or provision. Any waiver must be in writing and signed by an authorized representative of CodeQual.

### 15.4 Assignment
You may not assign or transfer these Terms or your rights under them without our prior written consent. We may assign these Terms without restriction.

### 15.5 Force Majeure
Neither party shall be liable for any failure or delay in performance due to causes beyond its reasonable control, including but not limited to acts of God, natural disasters, war, terrorism, strikes, government actions, internet or infrastructure failures, or third-party service outages.

### 15.6 Notices
We may provide notices to you via the CLI tool, the codequal.dev website, or the email address associated with your subscription. You may provide notices to us at info@codequal.dev.

### 15.7 No Agency
Nothing in these Terms creates a partnership, joint venture, employment, or agency relationship between you and CodeQual.

---

## 16. Changes to These Terms

We may modify these Terms at any time. When we make material changes, we will:

- Update the "Last Updated" date at the top of this document
- Post the revised Terms on our website at [https://codequal.dev/terms](https://codequal.dev/terms)
- For significant changes, provide at least 30 days' notice before the new Terms take effect
- For changes that materially reduce your rights or increase your obligations, we will make reasonable efforts to notify you via email or the CLI tool

Your continued use of the Service after the revised Terms take effect constitutes your acceptance of the revised Terms. If you do not agree to the revised Terms, you must stop using the Service and cancel any active subscription.

---

## 17. Contact Information

For questions about these Terms of Service, please contact us:

- **Email:** info@codequal.dev
- **Website:** [https://codequal.dev](https://codequal.dev)
- **Mailing Address:** CodeQual LLC, 30 N Gould St Ste R, Sheridan, WY 82801

---

## 18. Acknowledgments

By using the Service, you acknowledge that:

- You have read, understood, and agree to be bound by these Terms
- You have read and understood our Privacy Policy at [https://codequal.dev/privacy](https://codequal.dev/privacy)
- You are at least 16 years of age
- You have the legal capacity and authority to enter into these Terms
- The Service provides informational analysis and recommendations, not professional advice, and you are solely responsible for decisions made based on the Service's output

---

*These Terms of Service apply to Evolution Engine version 0.2.x and the codequal.dev website as of the effective date above.*
