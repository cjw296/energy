import pandas as pd


def load_octopus(storage, date):
    return pd.read_csv(storage / f'octopus-{date}.csv',
                       index_col='interval_start', parse_dates=['interval_start', 'interval_end'])


def load_tesla(storage, date):
    tesla = pd.read_csv(storage / f'tesla-{date}.csv',
                        index_col='Date time',
                        parse_dates=['Date time'],
                        date_parser=lambda col: pd.to_datetime(col, utc=True))
    # blank out any energy sent back to the grid, octopus is consumption only:
    tesla[tesla['Grid (kW)']<0] = 0
    # Tesla provide power flow every 5 mins, let's assume that represents the continous
    # consumption for the next 5 mins, and then resample to half-hours to match Octopus:
    tesla = (tesla*5/60).resample('30T').sum()
    tesla['consumption'] = tesla['Grid (kW)']
    return tesla
