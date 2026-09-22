# FinSight anomaly detection rules

This document describes the deterministic anomaly rules used by
`services/business_health_service.py`. Anomalies are review signals, not
audited findings, fraud determinations, ingestion-duplicate decisions, or credit
decisions.

| Finding | Input / grouping | Baseline and threshold | Minimum evidence | Severity | Stable identity / output context |
| --- | --- | --- | --- | --- | --- |
| Unusually large income / expense | Individual accepted transactions, grouped separately by `direction` | Tukey outer fence: Q1/Q3 from the direction-specific amount distribution, IQR = Q3-Q1, flag only when amount > Q3 + 3×IQR | At least 8 transactions in that direction and IQR > 0 | HIGH | Business/account + canonical type + affected transaction + robust-fence context. Context includes sample size, Q1, Q3, IQR and fence. |
| Repeated transaction pattern | Transactions grouped by amount + direction + category + payment mode | Review only when the same pattern occurs at least 4 times across at least 3 distinct dates | 4 occurrences / 3 dates | LOW | Pattern dimensions, occurrence count, first/last date. This is explicitly not proof of duplicate persisted transactions. |
| Sudden monthly expense spike | Latest two monthly aggregate periods | Current expense >= 1.5× prior expense and < 2× prior expense | Two comparable monthly periods with prior expense > 0 | MEDIUM | Month + monthly-growth metric. |
| Expense explosion | Latest two monthly aggregate periods | Current expense >= 2× prior expense | Two comparable monthly periods with prior expense > 0 | CRITICAL | Month + monthly-growth metric. The weaker spike is not emitted for the same event. |
| Sudden income drop | Latest two monthly aggregate periods | Current income > 0 and <= 50% of prior income | Two comparable monthly periods with prior income > 0 | HIGH | Month + signed income change. |
| Income interruption | Latest two monthly aggregate periods | Prior income > 0 and current income == 0 | Two comparable monthly periods | CRITICAL | Month. The generic income-drop finding is not also emitted for the same interruption. |
| High expense ratio | Selected-period totals | Expense-to-income ratio > 1.00 when the ratio is available | Selected-period totals | HIGH | Overall metric and threshold. |
| Cash-flow instability | Available trend periods used by the health model | Fewer than 50% of observed periods have non-negative cash flow | At least one trend period | HIGH | Stability metric and threshold. |
| Inactive period | Consecutive daily activity dates | Gap between observed activity dates > 7 days | Two observed activity dates | LOW | Date after the gap and inactive-day threshold. |
| Negative daily cash flow | Daily aggregate | Daily income - daily expense < 0 | One daily aggregate | LOW | Day + `period_kind=daily`; UI label is “Negative Daily Cash Flow.” |
| Category spike | Expense transactions grouped by category and month | Latest active month for a category >= 1.5× its prior active month | Two active months for the category | MEDIUM below 100% growth; HIGH at >=100% growth | Category, previous/current month, previous/current amounts, growth percentage. |
| Recurring expense growth | Same category/month comparison as category spike | Same >=50% growth condition, expressed as a recurring-category review signal | Two active months for the category | MEDIUM below 100% growth; HIGH at >=100% growth | Same category/month context; distinct canonical type. |
| Unexpected payment mode | Selected-period payment-mode counts | A payment mode appears exactly once while total transaction count is at least 3 | At least 3 transactions | MEDIUM | Payment mode. |
| Very high recurring expense burden | Expense categories observed across at least two months | Deterministic recurring-expense burden > 50% of expenses | Recurring categories and non-zero expense base | HIGH | Overall burden metric and threshold. |

## Identity and idempotency

Each finalized anomaly receives a deterministic SHA-256 `anomaly_id` derived
from business, account, canonical type, date/period, affected transaction,
trigger metric and detection context. An identical finding is emitted once.
Different transactions on the same date remain separate when their affected
transaction/context differs.

Legacy Phase-2 names are retained only as `legacy_type` metadata; they do not
create a second anomaly row.

## Presentation rules

The Streamlit Anomalies page shows a count/severity summary and groups the full
finding set by theme. Transaction-level findings expose human-readable amount,
date, description, category and payment mode when available. Category-level
findings expose the category. Repeated-pattern findings expose occurrence count
and observed date range.

The executive PDF does not re-run detection. It uses the report service's
health-service anomaly set, summarizes counts by severity and type, and shows at
most three material examples while noting that additional findings remain
available in FinSight.
