from pathlib import Path

import click
import pandas as pd
from common import DAYS_PER_YEAR, DAYS_PER_MONTH

DAYS_IN_PERIOD_COL = "Days"
COST_PER_DAY_COL = "Cost/day"

def parse_gas_kwh(ods: Path, sheet_name: str):
    # Load the specific sheet named "Gas"
    date_columns = ["Date", "Cost Since"]
    raw = pd.read_excel(ods, sheet_name=sheet_name, engine="odf", parse_dates=date_columns)

    # Filter out negative kWh values
    columns_to_keep = ["Date", "kwh", "Cost Since", 'Cost inc VAT', COST_PER_DAY_COL]
    if DAYS_IN_PERIOD_COL in raw.columns:
        columns_to_keep.append(DAYS_IN_PERIOD_COL)

    data = raw[raw["kwh"] >= 0][columns_to_keep]
    dates = data["Date"]
    effective = data["Cost Since"].fillna(data["Date"].shift(1))

    # Calculate Days in Period based on date differences
    data["Calc Days"] = days_in_period = (dates - effective).dt.days

    # Identify where the calculated days differ from the given values
    if DAYS_IN_PERIOD_COL in data.columns:
        data["Days Diff"] = days_in_period - data[DAYS_IN_PERIOD_COL]
    else:
        data["Days Diff"] = pd.NA

    # Calculate average kWh per day
    data["kwh per day"] = data["kwh"] / days_in_period

    data["Row Cost"] = data[COST_PER_DAY_COL] * days_in_period
    data['Cost Diff'] = data['Cost inc VAT'] - data['Row Cost']
    return data

@click.command()
@click.argument(
    'path',
    type=click.Path(path_type=Path, exists=True, dir_okay=False, resolve_path=True),
)
@click.argument(
    'sheet_name',
    default='Gas'
)
@click.option('--verbose', '-v', is_flag=True)
def main(path: Path, sheet_name:str, verbose: bool):
    data = parse_gas_kwh(path, sheet_name)
    if verbose:
        pd.set_option("display.max_rows", None)  # Ensure all rows are printed
        print(data, '\n')

    # Resample data to show average kWh per month by year
    data["Year"] = data["Date"].dt.year
    data["Month"] = data["Date"].dt.month

    monthly_summary(data, 'Row Cost', label='Monthly Cost')
    monthly_summary(data, 'kwh')

    daily_use = data.mean()['kwh per day']
    daily_cost = data.mean()[COST_PER_DAY_COL]
    print(f'{sheet_name} usage:')
    print(f'£{daily_cost * DAYS_PER_YEAR:,.0f}/year, £{daily_cost * DAYS_PER_MONTH:,.0f}/month')
    print(f'{daily_use * DAYS_PER_YEAR:,.0f} kWh/year, {daily_use * DAYS_PER_MONTH:,.0f} kWh/month')


def monthly_summary(data, field: str, label: str | None = None):
    summary = data.groupby(["Year", "Month"])[field].sum().unstack()
    summary = summary.round(0).map(lambda x: f"{x:,.0f}")
    print(f"\nAverage {label or field} per month by year:")
    print(summary.to_string(), '\n')


if __name__ == "__main__":
    main()
