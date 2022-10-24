from datetime import datetime

from backtrader.feeds import PandasData


class PandasDataFeedDaily(PandasData):
    lines: tuple = (
        "tvl",
        "fees",
        "liquidity",
        "token0_price",
        "token1_price",
        "tick",
        "wei",
        "gwei",
    )

    params: tuple = (
        # Possible values for datetime (must always be present)
        #  None : datetime is the "index" in the Pandas Dataframe
        #  -1 : autodetect position or case-wise equal name
        #  >= 0 : numeric index to the colum in the pandas dataframe
        #  string : column name (as index) in the pandas dataframe
        ("fromdate", datetime(2021, 1, 1)),
        ("dtformat", "%Y-%m-%d"),
        ("datetime", None),
        # Possible values below:
        #  None : column not present
        #  -1 : autodetect position or case-wise equal name
        #  >= 0 : numeric index to the colum in the pandas dataframe
        #  string : column name (as index) in the pandas dataframe
        ("open", "open_token0"),
        ("high", "high_token0"),
        ("low", "low_token0"),
        ("close", "close_token0"),
        ("volume", "volume_in_usd"),
        ("tvl", "tvl_in_usd"),
        ("fees", "fees_in_usd"),
        ("liquidity", "liquidity"),
        ("token0_price", "token0_in_usd"),
        ("token1_price", "token1_in_usd"),
        ("tick", "tick"),
        ("wei", "wei"),
        ("gwei", "gwei"),
    )
