# Axiom Dashboard: Alerts & Failures

> Single pane of glass for everything going wrong. Keep this open on launch day.

Dataset: `evo`
Note: Axiom flattens nested `properties.*` to top-level fields.

---

## 1. Payment Failures (Statistic — Red theme)
```apl
['evo']
| where event == "payment_failed"
| summarize count()
```

## 2. Webhook Errors (Statistic — Red theme)
```apl
['evo']
| where type == "webhook_error"
| summarize count()
```

## 3. CLI Errors (Statistic — Orange theme)
```apl
['evo']
| where event == "error"
| summarize count()
```

## 4. License Generation Failures (Statistic — Red theme)
```apl
['evo']
| where event == "error"
| where error contains "license"
| summarize count()
```

## 5. Checkout Drop-off (Table)
```apl
['evo']
| where event == "checkout_started" or event == "license_generated"
| summarize count() by event
```

## 6. All Errors Timeline (Line chart — group by error type)
```apl
['evo']
| where event == "error" or type == "webhook_error" or event == "payment_failed"
| extend error_category = case(
    event == "payment_failed", "payment",
    type == "webhook_error", "webhook",
    event == "error", tostring(error),
    "unknown")
| summarize count() by error_category, bin_auto(_time)
```

## 7. Adapter Failures (Table)
```apl
['evo']
| where event == "adapter_execution"
| where success == false
| summarize failures = count() by tostring(family)
```

## 8. Pattern Push Rejections (Statistic — Orange theme)
```apl
['evo']
| where event == "pattern_push"
| summarize total_rejected = sum(toint(rejected))
| where total_rejected > 0
```

## 9. Recent Errors (Log table — newest first)
```apl
['evo']
| where event == "error" or type == "webhook_error" or event == "payment_failed"
| project _time, event, type, error, detail
| sort by _time desc
| take 20
```
