from pathlib import Path

import pandas as pd


APP_DATA_DIR = Path(__file__).resolve().parent / "data"


def _data_path(data_folder: str | Path | None) -> Path:
    if data_folder is None or str(data_folder) == "data":
        return APP_DATA_DIR
    return Path(data_folder).expanduser().resolve()


def compute_kpis(data_folder=None):
    data_dir = _data_path(data_folder)
    checking_main = pd.read_csv(data_dir / "checking_account_main.csv")
    checking_main["date"] = pd.to_datetime(checking_main["date"], format="%d-%m-%Y")

    credit_card = pd.read_csv(data_dir / "credit_card_account.csv")
    credit_card["date"] = pd.to_datetime(credit_card["date"], format="%Y-%m-%d")

    payroll = pd.read_csv(data_dir / "gusto_payroll.csv")
    payroll["pay_date"] = pd.to_datetime(payroll["pay_date"], format="%d-%m-%Y")

    revenue = checking_main[checking_main["category"] == "Sales Revenue"]["amount"].sum()
    operating_expense = checking_main[checking_main["category"] == "Operating Expense"]["amount"].sum()
    cogs = checking_main[checking_main["category"] == "COGS"]["amount"].sum()
    card_spend = credit_card[credit_card["category"] != "Payment"]["amount"].sum()
    total_payroll = payroll["amount"].sum()

    total_expenses = operating_expense + cogs + card_spend + total_payroll
    net_profit = revenue - total_expenses
    net_profit_margin = (net_profit / revenue) * 100

    # data covers 2 years -- schemes define limits per YEAR, so this conversion matters
    date_span_days = (checking_main["date"].max() - checking_main["date"].min()).days
    years_covered = max(date_span_days / 365, 1)
    annual_turnover = revenue / years_covered

    return {
        "revenue_total": revenue,
        "operating_expense": operating_expense,
        "cogs": cogs,
        "card_spend": card_spend,
        "payroll": total_payroll,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "net_profit_margin": net_profit_margin,
        "years_covered": years_covered,
        "annual_turnover": annual_turnover,
    }
