# GDPR Data Deletion Runbook

**Internal use only** — Process for handling data subject access and deletion requests.
Privacy policy commits to 30-day response time.

---

## When a request comes in

Requests arrive at **info@codequal.dev** with subject "DSAR Request".

1. Log the request date (30-day clock starts)
2. Verify the requester's identity (match email to Stripe or adapter request records)
3. Process deletions per the sections below
4. Respond to the requester confirming completion

---

## Data locations and deletion steps

### Axiom (telemetry, webhook logs, adapter requests)

- **Dashboard:** https://app.axiom.co
- **Datasets:** `evo-telemetry`, `evo-webhooks`, `evo-adapter-requests`
- **Retention:** 30 days (auto-expiry configured)
- **Manual deletion:** If data must be removed before expiry, use Axiom's dataset query to identify and delete matching records by anonymous ID or email
- **Note:** Telemetry uses anonymous UUID, not email — only adapter requests contain email

### Stripe (payment data)

- **Dashboard:** https://dashboard.stripe.com
- **Steps:**
  1. Search customer by email
  2. Cancel any active subscription
  3. Delete the customer record (Stripe > Customers > select > Delete)
- **Note:** Stripe retains some data for legal/tax compliance per their policy. Inform the requester that residual Stripe retention is governed by Stripe's privacy policy.

### GitHub Issues (adapter requests)

- **Repo:** `alpsla/evolution_monitor`
- **Steps:**
  1. Search issues for the requester's email
  2. Edit or delete the issue content containing personal data
  3. If the requester wants full removal, delete the issue
- **Note:** Adapter requests posted as public issues may have been indexed by search engines. Deletion from GitHub does not guarantee removal from third-party caches.

### License keys (Stripe metadata)

- License keys contain only a truncated SHA-256 hash of the email (irreversible)
- The hash cannot be used to recover the email
- If requested: cancel subscription, clear `license_key` from Stripe customer metadata

### Local data (~/.evo/)

- We have no access to local data on the user's machine
- Inform the requester: "You can delete local data by running `rm -rf ~/.evo/` and removing `.evo/` directories from your repositories"

---

## Response template

> Dear [Name],
>
> We have processed your data deletion request dated [date]. The following actions were taken:
>
> - [Axiom records deleted / will auto-expire within 30 days]
> - [Stripe customer record deleted]
> - [GitHub issue removed]
>
> Please note that data stored locally on your machine (~/.evo/ directories) is under your control and was not transmitted to our servers.
>
> If you have any questions, please contact us at info@codequal.dev.
>
> Privacy Team, CodeQual LLC
