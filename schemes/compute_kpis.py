import pandas as pd

checking_main = pd.read_csv("data/checking_account_main.csv")
checking_main["date"] = pd.to_datetime(checking_main["date"], format="%d-%m-%Y")

credit_card = pd.read_csv("data/credit_card_account.csv")
credit_card["date"] = pd.to_datetime(credit_card["date"], format="%Y-%m-%d")

payroll = pd.read_csv("data/gusto_payroll.csv")
payroll["pay_date"] = pd.to_datetime(payroll["pay_date"], format="%d-%m-%Y")

# secondary account is loaded just to confirm it's pure internal transfer --
# we deliberately do NOT include its numbers in revenue/expense totals
secondary = pd.read_csv("data/checking_account_secondary.csv")


# ---- REVENUE ----
# only real sales count as revenue, nothing from transfers
revenue = checking_main[checking_main["category"] == "Sales Revenue"]["amount"].sum()


# ---- EXPENSES ----
# operating costs + cost of goods, straight from checking main
operating_expense = checking_main[checking_main["category"] == "Operating Expense"]["amount"].sum()
cogs = checking_main[checking_main["category"] == "COGS"]["amount"].sum()

# credit card spending, EXCLUDING "Payment to CC" rows (that's debt repayment, not new spend)
card_spend = credit_card[credit_card["category"] != "Payment"]["amount"].sum()

# real payroll cost, straight from gusto -- NOT from the secondary account's
# "Payroll Funding" rows, which would double-count the same money
total_payroll = payroll["amount"].sum()

total_expenses = operating_expense + cogs + card_spend + total_payroll


# ---- FINAL KPIs ----
net_profit = revenue - total_expenses
net_profit_margin = (net_profit / revenue) * 100

print("=== FINSIGHT KPI SUMMARY (Jan 2022 - Dec 2023) ===")
print(f"Total Revenue:          Rs {revenue:,.0f}")
print(f"  Operating Expense:    Rs {operating_expense:,.0f}")
print(f"  COGS:                 Rs {cogs:,.0f}")
print(f"  Card Spending:        Rs {card_spend:,.0f}")
print(f"  Payroll:              Rs {total_payroll:,.0f}")
print(f"Total Expenses:         Rs {total_expenses:,.0f}")
print(f"Net Profit:             Rs {net_profit:,.0f}")
print(f"Net Profit Margin:      {net_profit_margin:.1f}%")

# sanity check -- confirm secondary account really is just transfers, not new money
print("\n=== SANITY CHECK: secondary account categories ===")
print(secondary["category"].unique())
