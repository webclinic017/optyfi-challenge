import logging
from datetime import datetime, timedelta
from typing import Optional

import pytz
import requests
from pandas import DataFrame, Timestamp, read_csv, to_datetime
from requests import Response
from gas_estimator import GasEstimator
from erc20 import ERC20
from config import INFURA_URL

from price_data import get_coin_price_history


class UniswapV3:
    """
    UniswapV3 class.
    """

    def __init__(
        self, pool_token_ticker_pair: tuple[str, str], token_ticker: str
    ) -> None:
        """
        Class constructor.

        :param pool_token_ticker_pair: Token ticker pairs for the pool.
        :param token_ticker: Invested token ticker.
        """
        self._pool_token_ticker_pair: tuple[str, str] = pool_token_ticker_pair
        self._pool_name: str = "-".join(self._pool_token_ticker_pair)
        self._token_ticker: str = token_ticker.lower()
        self._uniswap_v3_address: str = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
        self._number_of_pools: int = self._get_number_of_pools()
        self._max_query_size: int = 1_000

        self._pool_address: str = ""
        self._token0_decimals: int = 0
        self._token1_decimals: int = 0
        self._token0_ticker: str = ""
        self._token1_ticker: str = ""
        self._get_pool_data()
        self._usdc_eth_abi: list = ERC20.erc20_from_abi_file(
            infura_url=INFURA_URL,
            erc20_abi_path="./abis/usdc_eth_abi.json"
        ).abi
        # https://docs.uniswap.org/protocol/reference/core/interfaces/pool/IUniswapV3PoolEvents
        self._gas_for_swap_event: int = GasEstimator(
            smart_contract_address=self._pool_address,
            abi=self._usdc_eth_abi,
            max_days=1,
            max_transaction_count=50,
        ).get_average_gas(event_name="Swap")
        self._gas_for_mint_event: int = GasEstimator(
            smart_contract_address=self._pool_address,
            abi=self._usdc_eth_abi,
            max_days=7,
            max_transaction_count=50,
        ).get_average_gas(event_name="Mint")
        self._gas_for_burn_event: int = GasEstimator(
            smart_contract_address=self._pool_address,
            abi=self._usdc_eth_abi,
            max_days=7,
            max_transaction_count=50,
        ).get_average_gas(event_name="Burn")

        # Data.
        self._token_prices: Optional[DataFrame] = None
        self._eth_gas_prices: Optional[DataFrame] = None
        self._pool_data: Optional[DataFrame] = None
        self._combined_data_prices: Optional[DataFrame] = None
        self._pool_fee_tier: Optional[float] = None

    @property
    def pool_token_ticker_pair(self) -> tuple[str, str]:
        return self._pool_token_ticker_pair

    @property
    def pool_name(self) -> str:
        return self._pool_name

    @property
    def token_prices(self) -> DataFrame:
        return self._token_prices

    @property
    def eth_gas_prices(self) -> DataFrame:
        return self._eth_gas_prices

    @property
    def pool_ohlc_prices(self) -> DataFrame:
        return self._pool_data

    @property
    def combined_data_prices(self) -> DataFrame:
        return self._combined_data_prices

    @property
    def pool_fee_tier(self) -> float:
        return self._pool_fee_tier

    @property
    def token0_decimals(self) -> int:
        return self._token0_decimals

    @property
    def token1_decimals(self) -> int:
        return self._token1_decimals

    @property
    def token0_ticker(self) -> str:
        return self._token0_ticker

    @property
    def token1_ticker(self) -> str:
        return self._token1_ticker

    @property
    def gas_for_mint_event(self) -> int:
        return self._gas_for_mint_event

    @property
    def gas_for_swap_event(self) -> int:
        return self._gas_for_swap_event

    @property
    def gas_for_burn_event(self) -> int:
        return self._gas_for_burn_event

    @staticmethod
    def _run_query(query: str) -> dict:
        """
        Run Uniswap v3 graph query.

        :param query: Query.
        :return: Query response.
        """
        # Uniswap v3 graph schema: https://github.com/Uniswap/v3-subgraph/blob/main/schema.graphql
        response: Response = requests.post(
            url="https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3",
            data="",
            json={"query": query},
        )

        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Query failed. return code is {response.status_code}.")
            raise Exception(f"Query failed. return code is {response.status_code}.")

    def _get_number_of_pools(self) -> int:
        """
        Get number of pools in Uniswap v3.

        :return: Number of pools.
        """
        query: str = (
            """
            {
                factory(id: "%s"){
                    poolCount
                }
            }
            """
            % self._uniswap_v3_address
        )

        response: dict = self._run_query(query)
        return int(response["data"]["factory"]["poolCount"])

    def _get_pool_data(self) -> None:

        # Get all pools.
        n_iterations: int = self._number_of_pools // self._max_query_size
        if self._number_of_pools % self._max_query_size:
            n_iterations += 1

        # TODO: Improve with this example.
        # pools(orderBy: feeTier, where: {
        #     token0: "${sortedTokens[0].id}",
        #     token1: "${sortedTokens[1].id}"}) {
        # query: str = """
        #     {
        #         pools(
        #             orderBy: feeTier, where: {
        #                 token0: "%s",
        #                 token1: "%s"
        #             }
        #         )
        #         {
        #             id
        #             tick
        #             sqrtPrice
        #             feeTier
        #             liquidity
        #             token0Price
        #             token1Price
        #         }
        #     }
        #     """ % (
        #     self._max_query_size,
        #     self._max_query_size * it,

        all_pools: list = []
        for it in range(0, n_iterations):

            query: str = """
                {
                    pools(first:%i, skip:%i)
                    {
                        id
                        feeTier
                        token0 {
                            symbol
                            decimals
                        }
                        token1 {
                            symbol
                            decimals
                        }
                    }
                }  
                """ % (
                self._max_query_size,
                self._max_query_size * it,
            )
            next_pools: dict = self._run_query(query)
            if "errors" in next_pools:
                [
                    logging.warning(f"API error: {e['message']}")
                    for e in next_pools["errors"]
                ]
                if len(next_pools) < self._number_of_pools:
                    logging.warning(
                        f"Gathered only {len(all_pools)}/{self._number_of_pools} pools."
                    )
                break
            else:
                all_pools: list[dict] = all_pools + next_pools["data"]["pools"]

        # Find the pool.
        pools: list[dict] = []
        for pool in all_pools:
            if (
                pool["token0"]["symbol"].lower() == self._pool_token_ticker_pair[0]
                and pool["token1"]["symbol"].lower() == self._pool_token_ticker_pair[1]
                or pool["token0"]["symbol"].lower() == self._pool_token_ticker_pair[1]
                and pool["token1"]["symbol"].lower() == self._pool_token_ticker_pair[0]
            ):
                logging.info(
                    f"Found pool with: {pool['token0']['symbol']} and {pool['token1']['symbol']} tokens "
                    f"with address: {pool['id']} (fee tier: {pool['feeTier']})."
                )
                pools.append(
                    {
                        "fee_tier": int(pool["feeTier"]),
                        "address": pool["id"],
                        "token0_decimals": int(pool["token0"]["decimals"]),
                        "token1_decimals": int(pool["token1"]["decimals"]),
                        "token0_symbol": pool["token0"]["symbol"],
                        "token1_symbol": pool["token1"]["symbol"],
                    }
                )

        if not pools:
            logging.error(
                f"Pool with tokens: {self._pool_token_ticker_pair} was not found."
            )
            raise Exception(
                f"Pool with tokens: {self._pool_token_ticker_pair} was not found."
            )
        else:
            # TODO: Decide which pool should be picked when there are multiple pools with different fee tiers.
            selected_pool: dict = min(pools, key=lambda x: x["fee_tier"])
            logging.info(f"Selected pool: {selected_pool}")

        self._pool_address: str = selected_pool["address"]
        self._token0_decimals: int = selected_pool["token0_decimals"]
        self._token1_decimals: int = selected_pool["token1_decimals"]
        self._token0_ticker: str = selected_pool["token0_symbol"].lower()
        self._token1_ticker: str = selected_pool["token0_symbol"].lower()

    def _gather_pool_data(self) -> None:
        # TODO: Load first 1000 days of OHLC prices - it will work because the Uniswap v3 pools are new.
        #   It will work till 2021-05-04 + 1000 days -> find more robust solution.
        query: str = (
            """
            {
                pool(id: "%s") {
                    feeTier
                    poolDayData(first: 1000) {
                        date
                        open
                        high
                        low
                        close
                        tvlUSD
                        feesUSD
                        volumeUSD
                        liquidity
                        tick
                    }
                }
            }
            """
            % self._pool_address
        )
        response: dict = self._run_query(query)

        ohlc_prices: DataFrame = DataFrame(response["data"]["pool"]["poolDayData"])
        ohlc_prices: DataFrame = DataFrame(ohlc_prices)
        ohlc_prices["date"] = [
            str(datetime.fromtimestamp(d, tz=pytz.timezone("UTC")).date())
            for d in ohlc_prices["date"]
        ]
        ohlc_prices.index = [Timestamp(x) for x in ohlc_prices["date"]]
        ohlc_prices: DataFrame = ohlc_prices.drop(columns="date")
        ohlc_prices: DataFrame = ohlc_prices.rename(
            columns={
                "open": "open_token0",
                "high": "high_token0",
                "low": "low_token0",
                "close": "close_token0",
                "tvlUSD": "tvl_in_usd",
                "volumeUSD": "volume_in_usd",
                "feesUSD": "fees_in_usd",
            }
        )

        # Convert data to floats.
        ohlc_prices: DataFrame = ohlc_prices.astype(
            {
                "open_token0": "float",
                "high_token0": "float",
                "low_token0": "float",
                "close_token0": "float",
                "tvl_in_usd": "float",
                "volume_in_usd": "float",
                "fees_in_usd": "float",
                "liquidity": "float",
                "tick": "float",
            }
        )

        # Fixing this bug: https://github.com/Uniswap/v3-subgraph/issues/29
        # Set: close at day D-1 = open at day D
        o_tmp: list = list(ohlc_prices["open_token0"])
        o_tmp.pop(0)
        o_tmp.append(0.0)
        ohlc_prices["close_token0"] = o_tmp

        # Remove 1st day of the pool, it started with open 0 USD.
        ohlc_prices: DataFrame = ohlc_prices.iloc[1:, :]
        # Remove last day - data is not completed.
        ohlc_prices: DataFrame = ohlc_prices.iloc[:-1, :]

        # TODO: Can contain missing data - detect and handle it.
        self._pool_data: DataFrame = ohlc_prices
        self._pool_fee_tier: float = float(response["data"]["pool"]["feeTier"])

    def _gather_token_price_data(self, start_day: str, end_day: str) -> None:
        """
        Gather tokens price data from free Coingecko API.

        :param start_day: Start day in YYYY-MM-DD format.
        :param end_day: End day in YYYY-MM-DD format.
        :return: None.
        """

        # TODO: This logic should be extracted in separate class/function. It is not related to Uniswap.

        # Gather data and create DataFrames.
        prices: list[DataFrame] = []
        for ticker in self._pool_token_ticker_pair:
            price_data: DataFrame = DataFrame.from_dict(
                get_coin_price_history(
                    coin_ticker=ticker,
                    start_timestamp=int(
                        datetime.strptime(start_day, "%Y-%m-%d").timestamp()
                    ),
                    end_timestamp=int(
                        (
                            datetime.strptime(end_day, "%Y-%m-%d") + timedelta(days=1)
                        ).timestamp()
                    ),
                )
            )
            price_data.index = [Timestamp(x) for x in price_data["date"]]
            price_data: DataFrame = price_data.drop(columns="date")
            if ticker.lower() == self._token0_ticker:
                price_data: DataFrame = price_data.rename(
                    columns={"prices": "token0_in_usd"}
                )
            else:
                price_data: DataFrame = price_data.rename(
                    columns={"prices": "token1_in_usd"}
                )
            prices.append(price_data)

        # Merge DataFrames.
        merged_prices: DataFrame = prices[0]
        for i in range(1, len(prices)):
            merged_prices: DataFrame = merged_prices.join(prices[i])

        self._token_prices: DataFrame = merged_prices

    def _gather_eth_gas_price_data(self) -> None:
        """
        Gather ETH gas price data from the hardcoded .csv file.

        :return: None.
        """
        # TODO: Find a source for gathering real-time / live data for gas price. For now, data till 2022-08-31.
        #   for now use the AvgGasPrice.csv file downloaded from: https://etherscan.io/chart/gasprice
        # TODO: This logic should be extracted in separate class/function.
        #  It is not related to Uniswap and should be loaded only once, not for each pool.

        eth_gas_price: DataFrame = read_csv("./data/AvgGasPrice.csv")
        eth_gas_price: DataFrame = eth_gas_price.rename(
            columns={"Value (Wei)": "wei", "Date(UTC)": "date"}
        )
        eth_gas_price["date"] = to_datetime(eth_gas_price["date"])
        eth_gas_price["date"] = [str(d.date()) for d in eth_gas_price["date"]]
        eth_gas_price.index = [Timestamp(x) for x in eth_gas_price["date"]]
        eth_gas_price: DataFrame = eth_gas_price.drop(columns=["date", "UnixTimeStamp"])
        eth_gas_price["gwei"] = eth_gas_price["wei"] / 1e9
        self._eth_gas_prices: DataFrame = eth_gas_price

    def has_data(self) -> bool:
        """
        Check if object has already gathered data.

        :return: True/False.
        """
        return True if self._combined_data_prices else False

    @staticmethod
    def _slice_by_date_range(
        start_day: str, end_day: str, data: DataFrame, data_name: str
    ) -> DataFrame:
        """
        Slice data by data range.

        :param start_day: Start day, e.g.: 2022-01-01.
        :param end_day: End day, e.g.: 2022-01-01.
        :param data: Data in DataFrame format.
        :param data_name: Data name - for logging.
        :return: Sliced data in DataFrame format.
        """
        try:
            start_idx: int = data.index.get_loc(start_day)
        except KeyError:
            logging.error(f"{data_name} data does not contain start day: {start_day}.")
            raise Exception(
                f"{data_name} data does not contain start day: {start_day}."
            )

        try:
            end_idx: int = data.index.get_loc(end_day) + 1
        except KeyError:
            logging.error(f"{data_name} data does not contain end day: {end_day}.")
            raise Exception(f"{data_name} data does not contain end day: {end_day}.")

        return data[start_idx:end_idx]

    def gather_data(self, start_day: str, end_day: str) -> DataFrame:
        """
        Gather all required data from different sources.

        :param start_day: Start day, e.g.: 2022-01-01.
        :param end_day: End day, e.g.: 2022-01-01.
        :return: All combined data prices.
        """
        # Gather data.
        self._gather_token_price_data(start_day=start_day, end_day=end_day)
        self._gather_eth_gas_price_data()
        self._gather_pool_data()

        # Merge data.
        self._combined_data_prices: DataFrame = self._token_prices
        self._combined_data_prices: DataFrame = self._combined_data_prices.join(
            self._eth_gas_prices
        )
        self._combined_data_prices: DataFrame = self._combined_data_prices.join(
            self._pool_data
        )

        # Fill missing data with forward fill.
        self._token_prices.fillna(method="ffill")
        self._eth_gas_prices.fillna(method="ffill")
        self._pool_data.fillna(method="ffill")
        self._combined_data_prices.fillna(method="ffill")

        # Final check if all merged data have required start and end day + slice all data.
        self._token_prices: DataFrame = self._slice_by_date_range(
            start_day=start_day,
            end_day=end_day,
            data=self._token_prices,
            data_name="Token prices",
        )
        self._eth_gas_prices: DataFrame = self._slice_by_date_range(
            start_day=start_day,
            end_day=end_day,
            data=self._eth_gas_prices,
            data_name="ETH gas prices",
        )
        self._pool_data: DataFrame = self._slice_by_date_range(
            start_day=start_day,
            end_day=end_day,
            data=self._pool_data,
            data_name="Pool data and prices",
        )
        self._combined_data_prices: DataFrame = self._slice_by_date_range(
            start_day=start_day,
            end_day=end_day,
            data=self._combined_data_prices,
            data_name="Combined data prices",
        )

        return self._combined_data_prices
