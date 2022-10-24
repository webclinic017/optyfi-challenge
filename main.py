import argparse
import logging
from datetime import date, timedelta
from typing import Optional
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

from backtesting import BacktestUniswapV3
from cls.uniswap_v3 import UniswapV3
from cls.utils import KnownStrategyNames, logging_setup


def plot_all_lp_ranges(bt_results: dict) -> None:
    # TODO: Redo the structure of bt_results - it should be list of objects instead of this dict structure.
    x_data_lp_range: dict[str, list[float]] = {}
    y_data_cash: dict[str, list[float]] = {}
    for p_key, p_val in bt_results.items():
        for s_key, s_val in p_val.items():
            x_data_lp_range[s_key] = []
            y_data_cash[s_key] = []
    for p_key, p_val in bt_results.items():
        for s_key, s_val in p_val.items():
            x_data_lp_range[s_key].append(int(s_val["lp_range"] * 100.0))
            y_data_cash[s_key].append(s_val["cash"])

    # Plot data.
    for x_key, x_val in x_data_lp_range.items():
        y_key = x_key  # Strategy name.
        y_val = y_data_cash[y_key]  # Values.
        plt.yscale("symlog")
        plt.plot(np.array(x_val), np.array(y_val), label=x_key)
        plt.xlim(xmin=0)
        plt.xlabel("LP range [%]")
        plt.ylabel("Cash [$]")

    # Store as PDF file.
    plt.title("Strategies")
    plt.legend()
    fig_name: str = (
        f"./plots/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_strategies.pdf"
    )
    plt.savefig(fig_name, format="pdf", bbox_inches="tight")


def backtest_uniswap_v3(
    token_ticker: str,
    pool_pairs: list[str],
    lp_range: Optional[list[float]],
    with_all_ranges: bool,
    strategy_names: list[str],
    start_day: Optional[str] = None,
    end_day: Optional[str] = None,
    with_graphs: bool = False,
) -> dict:
    """
    Entrypoint for backtesting Uniswap v3.

    :param token_ticker: Token ticker, e.g.: eth, usdt, etc.
    :param pool_pairs: List of pool pairs, e.g.: eth-usdc, etc.
    :param lp_range: List of 2 values for defining LP range, e.g.: [-0.1, 0,1].
    :param with_all_ranges: Flag for signaling use 1-100% of LP ranges.
    :param strategy_names: Strategy name.
    :param start_day: Start day string in YYYY-MM-DD format.
    :param end_day: End day string in YYYY-MM-DD format.
    :param with_graphs: Flag for enabling or disabling plotting.
    :return: Dictionary - each dictionary contains results/statistics for one strategy.
    """
    logging.info("Sanity check of input parameters ...")

    # Token ticker.
    token_ticker: str = token_ticker.lower()

    # Pool token ticker pairs.
    # NOTE: Only 2 sided pools are considered.
    if len(pool_pairs) == 0:
        logging.error("At least one pool with token ticker pair is required.")
        raise Exception("At least one pool with token ticker pair is required.")
    pool_token_ticker_pairs: list[tuple[str, str]] = []
    for pool_pair in pool_pairs:
        pairs: list[str] = pool_pair.split("-")
        if len(pairs) != 2:
            logging.warning(
                f"Skipping pool with pairs: {pool_pair}. Can not parse pairs."
            )
        else:
            if pairs[0] == "eth":
                pairs[0] = "weth"
            elif pairs[1] == "eth":
                pairs[1] = "weth"
            pool_token_ticker_pairs.append((pairs[0], pairs[1]))

    # LP range.
    if lp_range:
        lp_range: list[float] = [float(r) for r in lp_range]
        # TODO: Range has to be equal because of approach of selecting holding period.
        if abs(lp_range[0]) != abs(lp_range[1]):
            logging.error(f"LP range has to be the same, e.g. +-0.10 equals +-10%.")
            raise Exception(f"LP range has to be the same, e.g. +-0.10 equals +-10%.")

    # Strategies.
    processed_strategy_names: list[str] = []
    if len(strategy_names) == 0:
        logging.error(f"No strategy name was provided.")
        raise Exception(f"No strategy name was provided.")
    else:
        for strategy_name in strategy_names:
            if strategy_name not in KnownStrategyNames:
                logging.warning(
                    f"Skipping strategy with name: {strategy_name}. "
                    f"It is not in known strategies: {[e.value for e in KnownStrategyNames]}"
                )
            else:
                processed_strategy_names.append(strategy_name.lower())

    if len(processed_strategy_names) == 0:
        logging.error(f"No strategy name was provided.")
        raise Exception(f"No strategy name was provided.")
    else:
        strategy_names: list[str] = processed_strategy_names

    # Start day.
    if not start_day:
        # NOTE: Hardcoded start day.
        start_day: str = "2021-06-01"
        logging.warning(f"Start day was set to: {start_day}.")

    # End day.
    if not end_day:
        # NOTE: Set it to yesterday.
        end_day: str = str(date.today() - timedelta(days=1))
        logging.warning(f"End day was set to: {end_day}.")

    # Gather Uniswap v3 data for each pool.
    logging.info("Gathering Uniswap v3 data ...")
    u3s: list[UniswapV3] = []
    for pool_token_ticker_pair in pool_token_ticker_pairs:
        u3: UniswapV3 = UniswapV3(
            pool_token_ticker_pair=pool_token_ticker_pair, token_ticker=token_ticker
        )
        u3.gather_data(start_day=start_day, end_day=end_day)
        u3s.append(u3)

    # Backtests.
    logging.info("Starting backtesting ...")
    bt_results: dict = {}
    if lp_range:
        for u3 in u3s:
            logging.info(
                f"Running backtests for pool {u3.pool_name} with strategies {strategy_names} ..."
            )
            bt_u3: BacktestUniswapV3 = BacktestUniswapV3(
                token_ticker=token_ticker,
                lp_range=lp_range,
                with_all_ranges=with_all_ranges,
                strategy_names=strategy_names,
                start_day=start_day,
                end_day=end_day,
                u3_instance=u3,
                with_graphs=with_graphs,
            )
            bt_results[
                "-".join(u3.pool_token_ticker_pair)
            ] = bt_u3.backtest_strategies()
    elif with_all_ranges:
        for u3 in u3s:
            logging.info(
                f"Running backtests for pool {u3.pool_name} with strategies {strategy_names} ..."
            )
            for lpr in range(1, 101):
                bt_u3: BacktestUniswapV3 = BacktestUniswapV3(
                    token_ticker=token_ticker,
                    lp_range=[-lpr / 100.0, lpr / 100.0],
                    with_all_ranges=with_all_ranges,
                    strategy_names=strategy_names,
                    start_day=start_day,
                    end_day=end_day,
                    u3_instance=u3,
                    with_graphs=with_graphs,
                )
                bt_results[
                    "-".join(u3.pool_token_ticker_pair) + f"-{lpr}"
                ] = bt_u3.backtest_strategies()

        if with_graphs:
            plot_all_lp_ranges(bt_results)
    else:
        logging.error(
            "Bad LP range parameter combination, none of parameters is presented."
        )
        raise Exception(
            "Bad LP range parameter combination, none of parameters is presented."
        )

    return bt_results


if __name__ == "__main__":
    """
    Main entry point.
    """
    # Logging setup.
    logging_setup()

    logging.info(f"Starting OptyFi homework (by Lukas Bures).")

    logging.debug("Parsing input parameters ...")
    parser = argparse.ArgumentParser(description="Main parser")
    parser.add_argument(
        "-tt",
        "--token-ticker",
        dest="token_ticker",
        required=True,
        help="Token ticker.",
    )
    parser.add_argument(
        "-p",
        "--pool-pairs",
        nargs="+",
        dest="pool_pairs",
        required=True,
        help="List of pool token ticker pairs.",
    )
    parser.add_argument(
        "-sd",
        "--start-day",
        dest="start_day",
        required=False,
        help="Start day in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "-ed",
        "--end-day",
        dest="end_day",
        required=False,
        help="Start day in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "-wg",
        "--with-graphs",
        dest="with_graphs",
        action="store_true",
        help="Plot graphs.",
    )
    parser.set_defaults(with_graphs=False)
    parser.add_argument(
        "-s",
        "--strategy-names",
        nargs="+",
        dest="strategy_names",
        required=True,
        help="List of strategy names for backtesting.",
    )
    parser.add_argument(
        "-r", "--lp-range", nargs=2, dest="lp_range", required=False, help="LP range."
    )
    parser.add_argument(
        "-ar",
        "--all-ranges",
        dest="with_all_ranges",
        required=False,
        action="store_true",
        help="Flag for all LP ranges.",
    )
    parser.set_defaults(with_all_ranges=False)
    args = parser.parse_args()
    if not (args.lp_range or args.with_all_ranges):
        parser.error("No action requested, add -r (LP range) or -ar (all LP ranges).")

    logging.info(f"Input parameters: {vars(args)}")
    results: dict = backtest_uniswap_v3(**vars(args))

    # Result notes:
    # Sharpe ratio: generally speaking, a Sharpe ratio between 1 and 2 is considered good. A ratio between 2 and 3 is
    # very good, and any result higher than 3 is excellent.
    # Draw down: it refers to how much an investment or trading account is down from the peak before it recovers back
    # to the peak.
    for pool_key, pool_val in results.items():
        for strategy_key, strategy_val in pool_val.items():
            logging.info(
                f"Pool '{pool_key}', strategy '{strategy_key}', result: {strategy_val}"
            )
