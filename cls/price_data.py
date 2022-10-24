import logging
from datetime import datetime

import pytz
from cachetools import LRUCache, cached
from requests import get


@cached(LRUCache(maxsize=1))
def get_coingecko_ids() -> list:
    """
    Returns list with CoinGecko's CoinGecko's data.

    :return: Returns list of dictionaries with CoinGecko's data.
    """
    logging.debug("Fetching coin_ticker symbols from CoinGecko.")
    try:
        response = get("https://api.coingecko.com/api/v3/coins/list")
        response.raise_for_status()
        data: list = response.json()
    except Exception:
        logging.error("Can not retrieve data from CoinGecko's list.")
        raise Exception("Can not retrieve data from CoinGecko's list.")
    else:
        return data


def get_coin_price_history(
    coin_ticker: str, start_timestamp: int, end_timestamp: int
) -> dict:
    """
    Returns history price of a coin in USD.

    :param coin_ticker: Ticker of a coin, e.g. btc, eth, or ltc.
    :param start_timestamp: Starting timestamp.
    :param end_timestamp: Ending timestamp.
    :return: Returns dictionary with dates and prices (in USD) lists.
    """
    coin_ticker: str = coin_ticker.lower()
    ids: list = get_coingecko_ids()
    logging.debug(f"Trying to get USD price of: {coin_ticker}.")
    try:
        coin_id = list(filter(lambda x: x["symbol"] == coin_ticker, ids))[0]["id"]
    except IndexError as error:
        logging.debug(
            f"Unknown coin ticker: {coin_ticker.upper()}, it is not in CoinGecko's list. Error: {error}."
        )
        raise IndexError(
            f"Unknown coin ticker: {coin_ticker.upper()}, it is not in CoinGecko's list. Error: {error}."
        )
    except Exception as error:
        logging.debug(f"Error: {error}.")
        raise Exception(f"Error: {error}.")
    else:
        response = get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range?"
            f"vs_currency=usd&from={start_timestamp}&to={end_timestamp}"
        )
        response.raise_for_status()
        data = response.json()
        dates: list[str] = []
        prices: list[float] = []
        for price in data["prices"]:
            dates.append(
                str(
                    datetime.fromtimestamp(
                        price[0] / 1_000, tz=pytz.timezone("UTC")
                    ).date()
                )
            )
            prices.append(price[1])

        return {"date": dates, "prices": prices}
