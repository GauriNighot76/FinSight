# FinSight data audit — 6 September 2026

## Verdict

The supplied PDF is internally consistent with the supplied SQLite database,
but the database is not a faithful representation of the supplied medical CSV.
The report must therefore not be used as an accurate statement of that CSV.

## Independent CSV totals

| Measure | Correct value |
|---|---:|
| Rows | 1,278 |
| Income rows | 1,139 |
| Expense rows | 139 |
| Total income | INR 5,234,970.00 |
| Total expenses | INR 3,621,200.00 |
| Net cash flow | INR 1,613,770.00 |

For the report's nominal start date of 1 March 2026 through the CSV's actual
last date of 31 July 2026, the source contains 535 rows: INR 2,204,180 income,
INR 1,542,750 expenses, and INR 661,430 net cash flow.

## Why the old report differed

The supplied database contains 3,240 ledger rows across eight ingestion
attempts, including older/demo batches and repeated imports. One import also
discarded legitimate transactions because the earlier identity rule treated
same-date, same-amount rows as duplicates even when they had distinct source
transaction IDs. Optional fields such as category, description, and payment
method were detected but not written to the ledger. These defects also caused
the old anomaly list to be inflated.

## Verification of this build

The current flexible importer automatically mapped all eight columns in the
supplied CSV and normalized all 1,278 rows in two safe batches. It reproduced
the totals above and retained category, description, payment method, and source
transaction ID for every row.

Before comparing a newly generated report, clear the old imported history with
the documented backup-first reset command and import the CSV once. The new
report should use the CSV's actual date range and the totals above.
