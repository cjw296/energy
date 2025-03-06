from pathlib import Path

import click
import pandas as pd
from common import DAYS_PER_YEAR, DAYS_PER_MONTH

DAYS_IN_PERIOD_COL = "Days"


def parse_gas_kwh(ods: Path, sheet_name: str):
    # Load the specific sheet named "Gas"
    date_columns = ["Date", "Cost Since"]
    raw = pd.read_excel(ods, sheet_name=sheet_name, engine="odf", parse_dates=date_columns)

    # Filter out negative kWh values
    columns_to_keep = ["Date", "kwh", "Cost Since"]
    if DAYS_IN_PERIOD_COL in raw.columns:
        columns_to_keep.append(DAYS_IN_PERIOD_COL)

    data = raw[raw["kwh"] >= 0][columns_to_keep]
    dates = data["Date"]
    effective = data["Cost Since"].fillna(data["Date"].shift(1))

    # Calculate Days in Period based on date differences
    data["Calc Days"] = days_in_period = (dates - effective).dt.days

    # Identify where the calculated days differ from the given values
    if DAYS_IN_PERIOD_COL in data.columns:
        data["Difference in Days"] = days_in_period - data[DAYS_IN_PERIOD_COL]
    else:
        data["Difference in Days"] = pd.NA

    # Calculate average kWh per day
    data["kwh per day"] = data["kwh"] / days_in_period

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
    daily_average = data.mean()['kwh per day']
    annual = daily_average * DAYS_PER_YEAR
    monthly = daily_average * DAYS_PER_MONTH
    print(f'{sheet_name} usage: {annual:,.0f} kWh/year, {monthly:,.0f} kWh/month')


if __name__ == "__main__":
    main()
