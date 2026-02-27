# Axiom Dashboard Queries

APL queries for the 5 Axiom dashboards. Copy-paste into Axiom web UI.
Dataset: `evo` | Retention: 30 days

---

## Dashboard 1: Financial / Revenue

### MRR Tracker (cumulative subscribers × $19)
```apl
['evo']
| where event in ("license_generated", "license_revoked")
| extend delta = iff(event == "license_generated", 19, -19)
| summarize mrr = sum(delta) by bin(_time, 1d)
| sort by _time asc
| extend cumulative_mrr = row_cumsum(mrr)
```

### Revenue Events Timeline
```apl
['evo']
| where event in ("license_generated", "license_revoked", "payment_failed")
| summarize count() by event, bin(_time, 1d)
```

### New Subscribers Per Period
```apl
['evo']
| where event == "license_generated"
| summarize new_subs = count() by bin(_time, 7d)
```

### Checkout Conversion Funnel
```apl
['evo']
| where event in ("checkout_started", "license_generated", "license_retrieved")
| summarize count() by event
```

### Revenue at Risk (from failed payments)
```apl
['evo']
| where event == "payment_failed"
| summarize total_at_risk_cents = sum(toint(amount_cents)), failures = count() by bin(_time, 1d)
```

### Subscription Lifespan (from revocations)
```apl
['evo']
| where event == "license_revoked" and subscription_duration_days > 0
| summarize avg_days = avg(todouble(subscription_duration_days)),
            median_days = percentile(todouble(subscription_duration_days), 50)
```

---

## Dashboard 2: Business Overview

### License Funnel (daily)
```apl
['evo']
| where event in ("checkout_started", "license_generated", "license_retrieved", "analyze_complete")
| extend stage = case(
    event == "checkout_started", "1_checkout",
    event == "license_generated", "2_license",
    event == "license_retrieved", "3_retrieved",
    event == "analyze_complete", "4_first_analyze",
    "other")
| summarize count() by stage
```

### Active Users (unique anon_ids, 7d/30d)
```apl
['evo']
| where type == "telemetry" and event == "analyze_complete"
| where _time > ago(7d)
| summarize dcount(anon_id)
```

### Free vs Pro Ratio
```apl
['evo']
| where event == "analyze_complete"
| extend tier = tostring(properties.license_tier)
| summarize count() by tier
```

### Feature Gate Hits
```apl
['evo']
| where event == "analyze_complete"
| where toint(properties.gated_families_count) > 0
| summarize gate_hits = count(), unique_users = dcount(anon_id) by bin(_time, 1d)
```

### User Geography (top 10 countries)
```apl
['evo']
| where type == "telemetry" and isnotempty(country)
| summarize users = dcount(anon_id) by country
| top 10 by users
```

### Subscriber Geography
```apl
['evo']
| where event == "license_generated" and isnotempty(country)
| summarize count() by country
| top 10 by count_
```

---

## Dashboard 3: Usage Analytics

### Commands Per Day
```apl
['evo']
| where type == "telemetry"
| summarize count() by event, bin(_time, 1d)
```

### Analysis Duration (avg, p50, p95)
```apl
['evo']
| where event == "analyze_complete"
| extend dur = todouble(properties.duration_seconds)
| summarize avg_dur = avg(dur),
            p50 = percentile(dur, 50),
            p95 = percentile(dur, 95)
  by bin(_time, 1d)
```

### Adapter Family Detection Frequency
```apl
['evo']
| where event == "adapter_execution"
| summarize count() by tostring(properties.family)
```

### Adapter No-Data Diagnostics (which adapters return 0)
```apl
['evo']
| where event == "adapter_diagnostic"
| summarize count() by tostring(properties.family), tostring(properties.status)
```

### Unconnected Services (community adapter demand)
```apl
['evo']
| where event == "sources"
| mv-expand svc = properties.unconnected_services
| summarize demand = count() by tostring(svc)
| top 20 by demand
```

### AI Agent Usage (investigate + fix)
```apl
['evo']
| where event in ("investigate", "fix")
| summarize count(),
            avg_dur = avg(todouble(properties.duration_seconds))
  by event, bin(_time, 1d)
```

### Accept Workflow
```apl
['evo']
| where event == "accept"
| summarize total_accepted = sum(toint(properties.count)),
            sessions = count()
  by tostring(properties.scope), bin(_time, 7d)
```

### Pattern Sync Activity
```apl
['evo']
| where event == "pattern_sync"
| summarize count() by tostring(properties.action), bin(_time, 1d)
```

---

## Dashboard 4: Service Health

### Request Volume Per Handler
```apl
['evo']
| summarize count() by type, bin(_time, 1h)
```

### CLI Error Rate
```apl
['evo']
| where event == "error"
| summarize errors = count() by tostring(properties.error_type), bin(_time, 1h)
```

### Webhook Error Rate
```apl
['evo']
| where type == "webhook_error"
| summarize count() by tostring(event_type), bin(_time, 1h)
```

### Pattern Registry Health
```apl
['evo']
| where event in ("pattern_push", "pattern_pull")
| extend rejected = toint(rejected)
| summarize pushes = countif(event == "pattern_push"),
            pulls = countif(event == "pattern_pull"),
            total_rejected = sum(rejected)
  by bin(_time, 1d)
```

---

## Dashboard 5: Adapter & Pattern Ecosystem

### Adapter Detection by Family
```apl
['evo']
| where event == "adapter_execution"
| summarize executions = count(),
            avg_events = avg(todouble(properties.event_count)),
            failures = countif(properties.success == false)
  by tostring(properties.family)
```

### Tier 2 Unlock Rate
```apl
['evo']
| where event == "analyze_complete"
| extend tier = tostring(properties.license_tier)
| summarize pro = countif(tier == "pro"),
            free = countif(tier == "free")
  by bin(_time, 7d)
| extend pro_pct = round(100.0 * pro / (pro + free), 1)
```

### Pattern Growth (total patterns in registry over time)
```apl
['evo']
| where event == "pattern_push"
| summarize latest_total = max(toint(total_patterns)) by bin(_time, 1d)
```

### Quorum Tracking
```apl
['evo']
| where event in ("pattern_push", "pattern_pull")
| summarize latest_quorum = max(toint(quorum_met_count)) by bin(_time, 1d)
```

### Community Engagement (unique pushers)
```apl
['evo']
| where event == "pattern_push"
| summarize unique_pushers = dcount(instance_id) by bin(_time, 7d)
```

---

## Alerts (Monitors)

### Webhook Failures (> 3 in 5 min)
```apl
['evo']
| where type == "webhook_error"
| where _time > ago(5m)
| summarize count()
```

### CLI Error Spike (> 10 in 1 hour)
```apl
['evo']
| where event == "error"
| where _time > ago(1h)
| summarize count()
```

### Payment Failure Cluster (> 5 in 1 hour)
```apl
['evo']
| where event == "payment_failed"
| where _time > ago(1h)
| summarize count()
```

### Pattern Rejection Rate (> 50% in 1 hour)
```apl
['evo']
| where event == "pattern_push"
| where _time > ago(1h)
| summarize total_accepted = sum(toint(accepted)),
            total_rejected = sum(toint(rejected))
| extend rate = round(100.0 * total_rejected / (total_accepted + total_rejected), 1)
| where rate > 50
```
