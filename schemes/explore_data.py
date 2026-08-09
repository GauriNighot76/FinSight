import pandas as pd

# each file uses a different date format -- this is exactly the kind of
# real-world inconsistency FinSight's validation module (FR-VAL-003) exists to catch
checking_main = pd.read_csv("data/checking_account_main.csv")
checking_main["date"] = pd.to_datetime(checking_main["date"], format="%d-%m-%Y")

credit_card = pd.read_csv("data/credit_card_account.csv")
credit_card["date"] = pd.to_datetime(credit_card["date"], format="%Y-%m-%d")

payroll = pd.read_csv("data/gusto_payroll.csv")
payroll["pay_date"] = pd.to_datetime(payroll["pay_date"], format="%d-%m-%Y")


def explore(name, df, date_col):
    print(f"\n========== {name} ==========")
    print(df.head(3))
    print("\nRows:", len(df))
    print("Date range:", df[date_col].min(), "to", df[date_col].max())
    print("Missing values:\n", df.isnull().sum())
    if "category" in df.columns:
        print("Categories:", df["category"].unique())
    if "type" in df.columns:
        print("Transaction types:", df["type"].unique())


explore("CHECKING - MAIN", checking_main, "date")
explore("CREDIT CARD", credit_card, "date")
explore("PAYROLL", payroll, "pay_date")

print("\n========== QUICK TOTALS (checking main) ==========")
revenue = checking_main[checking_main["type"] == "Credit"]["amount"].sum()
expenses = checking_main[checking_main["type"] == "Debit"]["amount"].sum()
print("Total revenue (checking):", revenue)
print("Total expenses (checking):", expenses)
print("Net (checking only):", revenue - expenses)

print("\n========== QUICK TOTALS (credit card) ==========")
cc_spend = credit_card[credit_card["type"] == "Debit"]["amount"].sum()
cc_payments = credit_card[credit_card["type"] == "Credit"]["amount"].sum()
print("Total card spend:", cc_spend)
print("Total card payments made:", cc_payments)

print("\n========== QUICK TOTALS (payroll) ==========")
total_payroll = payroll["amount"].sum()
print("Total payroll paid out:", total_payroll)
