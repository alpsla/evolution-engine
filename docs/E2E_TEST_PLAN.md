# E2E Test Plan: Checkout → Heartbeat Full Flow

**Date**: 2026-03-01
**Scope**: Full license lifecycle on Stripe test mode + staging Vercel deployment
**Prerequisite**: All 1749 unit/integration tests passing

---

## Environment Setup

### Required Accounts & Credentials

| Item | Where |
|------|-------|
| Stripe Dashboard (test mode) | https://dashboard.stripe.com/test |
| Vercel project | codequal.dev (Preview or Production) |
| Upstash Redis console | https://console.upstash.com |
| Axiom dashboard | https://app.axiom.co (dataset: `evo`) |

### Required Environment Variables (Vercel)

Verify all are set in the Vercel project settings (**Project-level**, not team):

```
STRIPE_SECRET_KEY          — sk_test_...
STRIPE_WEBHOOK_SECRET      — whsec_...
STRIPE_PRICE_ID            — price_...
EVO_LICENSE_SIGNING_KEY    — (production HMAC key)
UPSTASH_REDIS_REST_URL     — https://....upstash.io
UPSTASH_REDIS_REST_TOKEN   — AX...
EVO_ACCEPT_SECRET          — (HMAC secret for accept API)
AXIOM_TOKEN                — xaat-...
AXIOM_DATASET              — evo
BASE_URL                   — https://codequal.dev
```

### Local Setup

```bash
pip install evolution-engine        # or: pip install -e ".[dev]"
pip install stripe                  # for Stripe CLI if not installed
```

### Stripe CLI (for webhook forwarding in staging)

```bash
stripe login
stripe listen --forward-to https://codequal.dev/api/webhook
# Note the webhook signing secret (whsec_...) — must match STRIPE_WEBHOOK_SECRET
```

---

## Test Scenarios

### T1: Deployment Smoke Test

**Goal**: Confirm all API endpoints are deployed and responding.

```bash
# T1.1 — license-check endpoint exists (was missing from vercel.json, now fixed)
curl -s -X POST https://codequal.dev/api/license-check \
  -H "Content-Type: application/json" \
  -d '{"key": "invalid"}' | jq .
# Expected: {"valid": false, "error": "..."} or {"error": "Not configured"} — NOT 404

# T1.2 — activate-license endpoint
curl -s -X POST https://codequal.dev/api/activate-license \
  -H "Content-Type: application/json" \
  -d '{"key": "invalid"}' | jq .
# Expected: {"valid": false, "error": "Invalid or expired license key"} — NOT 404

# T1.3 — get-license endpoint
curl -s "https://codequal.dev/api/get-license?session_id=cs_test_fake" | jq .
# Expected: {"license_key": null} — NOT 404

# T1.4 — create-checkout endpoint
curl -s -X POST https://codequal.dev/api/create-checkout \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
# Expected: {"url": "https://checkout.stripe.com/..."} — NOT 404

# T1.5 — webhook endpoint (no signature = rejected)
curl -s -X POST https://codequal.dev/api/webhook \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
# Expected: {"error": "Invalid signature", "v": 2} with HTTP 400

# T1.6 — patterns endpoint
curl -s "https://codequal.dev/api/patterns" | jq '.patterns | length'
# Expected: number >= 0

# T1.7 — accept endpoint (no sig = rejected)
curl -s "https://codequal.dev/api/accept?repo=test/test" | jq .
# Expected: {"error": "Missing or invalid signature"} with HTTP 403
```

**Pass criteria**: All 7 endpoints return JSON (not 404/500).

---

### T2: Checkout Flow (Browser)

**Goal**: Complete a test purchase and receive a license key.

| Step | Action | Expected |
|------|--------|----------|
| T2.1 | Open `https://codequal.dev` in browser | Landing page loads |
| T2.2 | Click "Get Pro" / pricing CTA | POST /api/create-checkout fires, redirects to Stripe Checkout |
| T2.3 | Fill Stripe test card: `4242 4242 4242 4242`, any future exp, any CVC, any email | Payment succeeds |
| T2.4 | Stripe redirects to `/success?session_id=cs_test_...` | Success page loads, shows "Retrieving your license key..." |
| T2.5 | Wait up to 40 seconds (polling every 2s, max 20 attempts) | License key appears in the license box |
| T2.6 | Click "Copy License Key" | Key copied to clipboard |

**Record**: Save the `session_id` and `license_key` for subsequent tests.

**Verification**:
```bash
# Confirm the session was created in Stripe
stripe checkout sessions list --limit 1
# Should show the session with metadata.product = "evolution-engine-pro"
```

---

### T3: Webhook Processing

**Goal**: Verify `checkout.session.completed` webhook generated the license key and wrote to Redis.

| Step | Action | Expected |
|------|--------|----------|
| T3.1 | Check Stripe webhook logs: Dashboard → Developers → Webhooks → Recent events | `checkout.session.completed` delivered with HTTP 200 |
| T3.2 | Check Vercel function logs for webhook | Log entry: `{"type": "webhook", "event": "license_generated", ...}` |
| T3.3 | Check Stripe Customer metadata | `evo_license_key` field is set on the Customer object |

**Verification** (Stripe CLI):
```bash
# Find the customer ID from the session
SESSION_ID="cs_test_..."  # from T2
CUSTOMER_ID=$(stripe checkout sessions retrieve $SESSION_ID --format json | jq -r '.customer')
echo "Customer: $CUSTOMER_ID"

# Check customer metadata
stripe customers retrieve $CUSTOMER_ID --format json | jq '.metadata'
# Expected: {"evo_license_key": "eyJ..."}
```

**Redis verification**:
```bash
# The webhook should have written to Redis
# Key format: evo:license:<sha256(license_key)[:16]>
# Check via Upstash console or REST API:

LICENSE_KEY="eyJ..."  # from T2.6
KEY_HASH=$(echo -n "$LICENSE_KEY" | shasum -a 256 | cut -c1-16)
echo "Redis key: evo:license:$KEY_HASH"

# Query Upstash REST API:
curl -s "$UPSTASH_REDIS_REST_URL/get/evo:license:$KEY_HASH" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" | jq .
# Expected: {"result": "{\"status\": \"active\", \"updated_at\": \"...\"}"}
```

**Pass criteria**: Customer has `evo_license_key`, Redis has `status: "active"`.

---

### T4: License Retrieval (API)

**Goal**: Confirm GET /api/get-license returns the key.

```bash
SESSION_ID="cs_test_..."  # from T2

curl -s "https://codequal.dev/api/get-license?session_id=$SESSION_ID" | jq .
# Expected: {"license_key": "eyJ..."}
```

**Edge cases**:
```bash
# T4.1 — Invalid session ID
curl -s "https://codequal.dev/api/get-license?session_id=cs_test_nonexistent" | jq .
# Expected: {"license_key": null}

# T4.2 — Missing session_id
curl -s "https://codequal.dev/api/get-license" | jq .
# Expected: {"error": "..."} with HTTP 400

# T4.3 — Malformed session_id (no cs_ prefix)
curl -s "https://codequal.dev/api/get-license?session_id=bad_id" | jq .
# Expected: {"error": "..."} with HTTP 400
```

**Pass criteria**: Valid session returns the key; invalid inputs return errors.

---

### T5: Server-Side Activation

**Goal**: Confirm `/api/activate-license` validates the key correctly.

```bash
LICENSE_KEY="eyJ..."  # from T2.6

# T5.1 — Valid key
curl -s -X POST https://codequal.dev/api/activate-license \
  -H "Content-Type: application/json" \
  -d "{\"key\": \"$LICENSE_KEY\"}" | jq .
# Expected: {"valid": true, "tier": "pro", "email_hash": "...", "issued": "...", "activated_at": "..."}

# T5.2 — Invalid key (tampered)
curl -s -X POST https://codequal.dev/api/activate-license \
  -H "Content-Type: application/json" \
  -d '{"key": "dGFtcGVyZWQ="}' | jq .
# Expected: {"valid": false, "error": "Invalid or expired license key"}

# T5.3 — Missing key field
curl -s -X POST https://codequal.dev/api/activate-license \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
# Expected: error response

# T5.4 — Rate limiting (send 11 requests rapidly)
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code} " -X POST https://codequal.dev/api/activate-license \
    -H "Content-Type: application/json" \
    -d "{\"key\": \"$LICENSE_KEY\"}"
done
echo
# Expected: first 10 return 200, 11th returns 429
```

**Pass criteria**: Valid key returns `valid: true, tier: pro`; invalid key rejected; rate limit enforced.

---

### T6: CLI Activation

**Goal**: Activate the license via the `evo` CLI and verify local state.

```bash
# T6.1 — Check current status (should be free)
evo license status
# Expected: "Free" tier

# T6.2 — Activate with the key
LICENSE_KEY="eyJ..."  # from T2.6
evo license activate "$LICENSE_KEY"
# Expected: Success message, Pro tier confirmed

# T6.3 — Verify license file was created
cat ~/.evo/license.json | python3 -m json.tool
# Expected:
# {
#   "key": "eyJ...",
#   "tier": "pro",
#   "email_hash": "...",
#   "issued": "...",
#   "activated_at": "...",
#   "activation_token": "..."  (SHA-256 integrity token)
# }

# T6.4 — Verify status shows Pro
evo license status
# Expected: "Pro" tier

# T6.5 — Verify activation token integrity
# The token should be sha256("key:tier:email_hash:issued:evo-activation-v1")[:32]
python3 -c "
import json, hashlib
with open('$HOME/.evo/license.json') as f:
    d = json.load(f)
raw = f\"{d['key']}:{d['tier']}:{d['email_hash']}:{d['issued']}:evo-activation-v1\"
expected = hashlib.sha256(raw.encode()).hexdigest()[:32]
print(f'Token matches: {d[\"activation_token\"] == expected}')
"
# Expected: Token matches: True
```

**Pass criteria**: `~/.evo/license.json` exists with valid Pro license and correct integrity token.

---

### T7: Heartbeat — Active Subscription

**Goal**: Verify the CLI heartbeat confirms active status.

```bash
# T7.1 — Delete any existing heartbeat cache
rm -f ~/.evo/license_check.json

# T7.2 — Run evo analyze (triggers heartbeat on first run)
cd /tmp && git init heartbeat-test && cd heartbeat-test
git commit --allow-empty -m "init"
evo analyze .
# Expected: Runs as Pro (Tier 2 adapters available), no degradation warning

# T7.3 — Check heartbeat cache was written
cat ~/.evo/license_check.json | python3 -m json.tool
# Expected:
# {
#   "status": "active",
#   "last_checked": "2026-03-01T...",
#   "last_success": "2026-03-01T..."
# }

# T7.4 — Verify heartbeat called the server
# Check Vercel function logs or Axiom for:
#   {"type": "license_check", "event": "heartbeat", "status": "active", ...}

# Clean up
cd / && rm -rf /tmp/heartbeat-test
```

**Pass criteria**: Heartbeat returns active, cache file written, Pro features work.

---

### T8: Heartbeat — Direct API Check

**Goal**: Verify `/api/license-check` returns correct status for the active key.

```bash
LICENSE_KEY="eyJ..."  # from T2.6

# T8.1 — Check active key
curl -s -X POST https://codequal.dev/api/license-check \
  -H "Content-Type: application/json" \
  -d "{\"key\": \"$LICENSE_KEY\"}" | jq .
# Expected: {"valid": true, "status": "active", "tier": "pro", "checked_at": "..."}

# T8.2 — Check with forged key
curl -s -X POST https://codequal.dev/api/license-check \
  -H "Content-Type: application/json" \
  -d '{"key": "dGFtcGVyZWQ="}' | jq .
# Expected: {"valid": false, "error": "..."} — HMAC validation fails

# T8.3 — Check with missing key
curl -s -X POST https://codequal.dev/api/license-check \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
# Expected: error response
```

**Pass criteria**: Active key returns `valid: true, status: active`; forged key rejected.

---

### T9: Payment Failure → Past Due

**Goal**: Simulate failed payment and verify heartbeat degrades after grace period.

```bash
# T9.1 — Trigger payment_failed via Stripe CLI
stripe trigger invoice.payment_failed

# Or manually in Stripe Dashboard:
#   → Customers → find test customer → create a test invoice → mark as failed

# T9.2 — Verify Redis status changed
KEY_HASH="..."  # from T3
curl -s "$UPSTASH_REDIS_REST_URL/get/evo:license:$KEY_HASH" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" | jq .
# Expected: {"result": "{\"status\": \"past_due\", ...}"}

# T9.3 — Verify heartbeat returns past_due
curl -s -X POST https://codequal.dev/api/license-check \
  -H "Content-Type: application/json" \
  -d "{\"key\": \"$LICENSE_KEY\"}" | jq .
# Expected: {"valid": true, "status": "past_due", "tier": "pro", ...}
# Note: valid=true because past_due gets a grace period

# T9.4 — Verify Customer metadata
CUSTOMER_ID="cus_..."  # from T3
stripe customers retrieve $CUSTOMER_ID --format json | jq '.metadata'
# Expected: evo_payment_status = "past_due", evo_payment_attempt = "1"

# T9.5 — Verify CLI heartbeat (clear cache to force re-check)
rm -f ~/.evo/license_check.json
cd /tmp && git init pd-test && cd pd-test && git commit --allow-empty -m "init"
evo analyze .
# Expected: Still runs as Pro (within 14-day grace period)

cat ~/.evo/license_check.json | python3 -m json.tool
# Expected: status = "past_due", grace_start is set
cd / && rm -rf /tmp/pd-test
```

**Pass criteria**: Redis shows `past_due`, heartbeat returns `past_due`, CLI operates in grace period.

---

### T10: Subscription Cancellation → Revocation

**Goal**: Cancel the test subscription and verify license is revoked.

```bash
# T10.1 — Cancel the subscription in Stripe Dashboard
#   Dashboard → Customers → find test customer → Subscriptions → Cancel immediately
# Or via CLI:
SUB_ID="sub_..."  # find from customer
stripe subscriptions cancel $SUB_ID

# T10.2 — Verify webhook processed
# Check Stripe webhook logs: customer.subscription.deleted → HTTP 200

# T10.3 — Verify Customer metadata cleared
stripe customers retrieve $CUSTOMER_ID --format json | jq '.metadata.evo_license_key'
# Expected: "" (empty string — key cleared)

# T10.4 — Verify Redis status
curl -s "$UPSTASH_REDIS_REST_URL/get/evo:license:$KEY_HASH" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" | jq .
# Expected: {"result": "{\"status\": \"cancelled\", ...}"}

# T10.5 — Verify heartbeat returns cancelled
curl -s -X POST https://codequal.dev/api/license-check \
  -H "Content-Type: application/json" \
  -d "{\"key\": \"$LICENSE_KEY\"}" | jq .
# Expected: {"valid": false, "status": "cancelled", "tier": "pro", ...}
# Note: valid=false — cancelled keys are NOT valid

# T10.6 — Verify CLI degrades to free tier
rm -f ~/.evo/license_check.json
cd /tmp && git init cancel-test && cd cancel-test && git commit --allow-empty -m "init"
evo analyze .
# Expected: Runs as FREE tier — Tier 2 adapters gated, LLM gated
evo license status
# Expected: Shows free or degraded status

cat ~/.evo/license_check.json | python3 -m json.tool
# Expected: status = "cancelled"
cd / && rm -rf /tmp/cancel-test
```

**Pass criteria**: Key cleared from Stripe, Redis shows `cancelled`, CLI degrades to free.

---

### T11: Subscription Renewal → Re-activation

**Goal**: Verify `invoice.payment_succeeded` regenerates the key and restores Pro.

```bash
# T11.1 — Create a new checkout (fresh subscription for the same customer or new)
# Repeat T2 flow with the same or new email

# T11.2 — After checkout completes, trigger a renewal
stripe trigger invoice.payment_succeeded

# T11.3 — Verify new key was generated
stripe customers retrieve $CUSTOMER_ID --format json | jq '.metadata'
# Expected:
#   evo_license_key = new key (different from original)
#   evo_payment_status = "active"
#   evo_last_invoice_id = "in_..."

# T11.4 — Verify old key cancelled, new key active in Redis
# Old key:
curl -s "$UPSTASH_REDIS_REST_URL/get/evo:license:$OLD_KEY_HASH" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" | jq .
# Expected: status = "cancelled"

# New key:
NEW_LICENSE_KEY="..."  # from T11.3
NEW_KEY_HASH=$(echo -n "$NEW_LICENSE_KEY" | shasum -a 256 | cut -c1-16)
curl -s "$UPSTASH_REDIS_REST_URL/get/evo:license:$NEW_KEY_HASH" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" | jq .
# Expected: status = "active"

# T11.5 — Activate new key and verify Pro restored
evo license activate "$NEW_LICENSE_KEY"
evo license status
# Expected: Pro tier
```

**Pass criteria**: Old key cancelled, new key active, CLI re-activated as Pro.

---

### T12: Renewal Idempotency

**Goal**: Verify duplicate `invoice.payment_succeeded` doesn't regenerate the key.

```bash
# T12.1 — Note current key
CURRENT_KEY=$(stripe customers retrieve $CUSTOMER_ID --format json | jq -r '.metadata.evo_license_key')

# T12.2 — Trigger the same invoice event again (Stripe retry simulation)
stripe trigger invoice.payment_succeeded

# T12.3 — Verify key unchanged
NEW_KEY=$(stripe customers retrieve $CUSTOMER_ID --format json | jq -r '.metadata.evo_license_key')
echo "Key unchanged: $([ "$CURRENT_KEY" = "$NEW_KEY" ] && echo YES || echo NO)"
# Expected: YES — idempotency via evo_last_invoice_id
```

**Pass criteria**: Key doesn't change on duplicate invoice event.

---

### T13: Refund → Revocation

**Goal**: Verify charge.refunded revokes the license.

```bash
# T13.1 — Refund the last charge
# Stripe Dashboard → Payments → find last payment → Refund
# Or:
CHARGE_ID="ch_..."
stripe refunds create --charge $CHARGE_ID

# T13.2 — Verify webhook processed charge.refunded → license_revoked
# Check Stripe webhook logs

# T13.3 — Verify Redis status
curl -s "$UPSTASH_REDIS_REST_URL/get/evo:license:$KEY_HASH" \
  -H "Authorization: Bearer $UPSTASH_REDIS_REST_TOKEN" | jq .
# Expected: status = "revoked" (not just "cancelled")

# T13.4 — Verify heartbeat rejects revoked key
curl -s -X POST https://codequal.dev/api/license-check \
  -H "Content-Type: application/json" \
  -d "{\"key\": \"$LICENSE_KEY\"}" | jq .
# Expected: {"valid": false, "status": "revoked", ...}

# T13.5 — Verify CLI degrades immediately (no grace period for revoked)
rm -f ~/.evo/license_check.json
evo license status
# Expected: Free tier
```

**Pass criteria**: Refund triggers immediate revocation with no grace period.

---

### T14: Heartbeat — Network Failure Grace Period

**Goal**: Verify CLI doesn't immediately degrade when server is unreachable.

```bash
# T14.1 — Start with a working Pro license
evo license status
# Expected: Pro

# T14.2 — Simulate server unreachable by blocking the domain
# Add to /etc/hosts: 127.0.0.1 codequal.dev
# (requires sudo — revert after test)

# T14.3 — Clear heartbeat cache and set last_success to 5 days ago
python3 -c "
import json
from datetime import datetime, timedelta
cache = {
    'status': 'active',
    'last_checked': (datetime.now() - timedelta(days=8)).isoformat(),
    'last_success': (datetime.now() - timedelta(days=5)).isoformat(),
}
with open('$HOME/.evo/license_check.json', 'w') as f:
    json.dump(cache, f)
"

# T14.4 — Run evo analyze — should still work (within 14-day grace)
cd /tmp && git init grace-test && cd grace-test && git commit --allow-empty -m "init"
evo analyze .
# Expected: Still Pro — last_success was 5 days ago, within 14-day grace

# T14.5 — Set last_success to 15 days ago (expired grace)
python3 -c "
import json
from datetime import datetime, timedelta
cache = {
    'status': 'active',
    'last_checked': (datetime.now() - timedelta(days=16)).isoformat(),
    'last_success': (datetime.now() - timedelta(days=15)).isoformat(),
}
with open('$HOME/.evo/license_check.json', 'w') as f:
    json.dump(cache, f)
"

# T14.6 — Run evo analyze — should degrade to free
evo analyze .
# Expected: Free tier — grace period expired, can't reach server

# T14.7 — Revert /etc/hosts, clear cache
# Remove the 127.0.0.1 codequal.dev line from /etc/hosts
rm -f ~/.evo/license_check.json
cd / && rm -rf /tmp/grace-test
```

**Pass criteria**: Pro maintained during 14-day grace; degrades after grace expires.

---

### T15: Axiom Telemetry Verification

**Goal**: Confirm key events are logged to Axiom.

Open Axiom dashboard → dataset `evo` → query:

```kusto
['evo']
| where _time > ago(1h)
| where type in ("checkout", "webhook", "activation", "license_check")
| project _time, type, event, tier, status, country
| sort by _time desc
```

**Expected events** (from T2–T13):

| type | event | count |
|------|-------|-------|
| `checkout` | `checkout_started` | >= 1 |
| `checkout` | `license_retrieved` | >= 1 |
| `webhook` | `license_generated` | >= 1 |
| `activation` | `activation_success` | >= 1 |
| `license_check` | `heartbeat` | >= 1 |
| `webhook` | `payment_failed` | >= 1 (if T9 run) |
| `webhook` | `license_revoked` | >= 1 (if T10/T13 run) |
| `webhook` | `license_renewed` | >= 1 (if T11 run) |

**Pass criteria**: All expected event types present in Axiom with correct fields.

---

### T16: DO_NOT_TRACK Respected

**Goal**: Verify heartbeat is skipped when opt-out is set.

```bash
# T16.1 — Set opt-out
export DO_NOT_TRACK=1

# T16.2 — Clear heartbeat cache
rm -f ~/.evo/license_check.json

# T16.3 — Run evo analyze
cd /tmp && git init dnt-test && cd dnt-test && git commit --allow-empty -m "init"
evo analyze .
# Expected: Pro tier (heartbeat skipped, no degradation)

# T16.4 — Verify no heartbeat cache was written
test -f ~/.evo/license_check.json && echo "FAIL: cache written" || echo "PASS: no cache"
# Expected: PASS

# T16.5 — Verify no heartbeat event in Axiom (no new license_check events)

# Clean up
unset DO_NOT_TRACK
cd / && rm -rf /tmp/dnt-test
```

**Pass criteria**: No heartbeat call made, no cache written, Pro preserved.

---

## Post-Test Cleanup

```bash
# 1. Remove test license
rm -f ~/.evo/license.json
rm -f ~/.evo/license_check.json

# 2. Delete test customers in Stripe Dashboard (optional)
#    Dashboard → Customers → select test customers → Delete

# 3. Clear Redis test keys (optional)
#    Upstash console → CLI → DEL evo:license:<hash>

# 4. Revert /etc/hosts if modified in T14
```

---

## Summary Checklist

| # | Scenario | Result |
|---|----------|--------|
| T1 | Deployment smoke test (7 endpoints) | |
| T2 | Checkout flow (browser) | |
| T3 | Webhook processing + Redis write | |
| T4 | License retrieval (GET /api/get-license) | |
| T5 | Server-side activation (POST /api/activate-license) | |
| T6 | CLI activation (`evo license activate`) | |
| T7 | Heartbeat — active subscription | |
| T8 | Heartbeat — direct API check | |
| T9 | Payment failure → past_due + grace | |
| T10 | Subscription cancellation → revocation | |
| T11 | Subscription renewal → re-activation | |
| T12 | Renewal idempotency | |
| T13 | Refund → immediate revocation | |
| T14 | Network failure grace period (14 days) | |
| T15 | Axiom telemetry verification | |
| T16 | DO_NOT_TRACK opt-out respected | |

**All 16 scenarios must pass before go-live.**
